from dataclasses import dataclass
from typing import Optional
from uuid import UUID
import psycopg
from uuid import UUID
from typing import List
import logging
from config import get_postgres_conn_string



@dataclass(frozen=True)
class WebUser:
    name: str
    login_name: str
    user_uuid: Optional[UUID] = None

@dataclass(frozen=True)
class WebSession:
    user_uuid: UUID
    session_uuid: Optional[UUID] = None


def _store_web_user(conn: psycopg.Connection, user: WebUser) -> UUID:
    """Private database method to insert a new web user into PostgreSQL."""
    insert_query = """
        INSERT INTO web_user (name, login_name)
        VALUES (%s, %s)
        RETURNING user_uuid;
    """
    with conn.cursor() as cur:
        cur.execute(insert_query, (user.name, user.login_name))
        user_uuid = cur.fetchone()[0]
    
    return user_uuid


def _get_user_uuid(conn: psycopg.Connection, login_name: str) -> Optional[UUID]:
    select_query = """
        SELECT user_uuid 
        FROM web_user 
        WHERE login_name = %s;
    """
    with conn.cursor() as cur:
        cur.execute(select_query, (login_name,))
        row = cur.fetchone()
        return row[0] if row else None


def _get_web_session(conn: psycopg.Connection, user_uuid: UUID) -> Optional[UUID]:
    """ check if an existing session exists for user_uuid."""
    select_query = """
        SELECT session_uuid 
        FROM web_session 
        WHERE user_uuid = %s;
    """
    with conn.cursor() as cur:
        cur.execute(select_query, (user_uuid,))
        row = cur.fetchone()
        return row[0] if row else None


def _store_web_session(conn: psycopg.Connection, user_uuid: UUID) -> UUID:
    """insert a new session and return the generated session_uuid."""
    insert_query = """
        INSERT INTO web_session (user_uuid)
        VALUES (%s)
        RETURNING session_uuid;
    """
    with conn.cursor() as cur:
        cur.execute(insert_query, (user_uuid,))
        session_uuid = cur.fetchone()[0]

    return session_uuid


def _store_word_tracker_batch(
    conn: psycopg.Connection,
    session_uuid: UUID,
    game_name: str,
    w_level: int,
    batch_size: int,
) -> List[str]:
    """
    Private DB helper that fetches batch_size unassigned tokens for the session/level
    and inserts them into word_tracker within the same transaction.
    """
    # 1. Fetch tokens from hindi_master that haven't been tracked for this session_uuid
    select_query = """
        SELECT hm.token
        FROM hindi_master hm
        WHERE hm.w_level = %s
          AND NOT EXISTS (
              SELECT 1
              FROM word_tracker wt
              WHERE wt.session_uuid = %s
                AND wt.token = hm.token
          )
        ORDER BY RANDOM()
        LIMIT %s;
    """

    # 2. Bulk insert fetched tokens into word_tracker
    insert_query = """
        INSERT INTO word_tracker (session_uuid, game_name, w_level, token)
        VALUES (%s, %s, %s, %s);
    """

    with conn.cursor() as cur:
        cur.execute(select_query, (w_level, session_uuid, batch_size))
        rows = cur.fetchall()
        
        tokens = [row[0] for row in rows]

        if tokens:
            # Prepare tuples for executemany batch insertion
            records_to_insert = [
                (session_uuid, game_name, w_level, token) for token in tokens
            ]
            cur.executemany(insert_query, records_to_insert)

        return tokens
    
def _delete_web_session(conn: psycopg.Connection, session_uuid: UUID) -> bool:
    """
    Private DB helper to delete a session by session_uuid.
    Returns True if a row was deleted, False otherwise.
    """
    delete_query = """
        DELETE FROM web_session
        WHERE session_uuid = %s;
    """
    with conn.cursor() as cur:
        cur.execute(delete_query, (session_uuid,))
        return cur.rowcount > 0

def _delete_web_sessions_by_login_name(conn: psycopg.Connection, login_name: str) -> int:
    """
    Private DB helper to delete all sessions associated with a login_name via join.
    Returns the count of deleted sessions.
    """
    delete_query = """
        DELETE FROM web_session
        WHERE user_uuid = (
            SELECT user_uuid 
            FROM web_user 
            WHERE login_name = %s
        );
    """
    with conn.cursor() as cur:
        cur.execute(delete_query, (login_name,))
        return cur.rowcount
    
    
"""
# #################################
#
# PUBLIC METHODS 
# 
###################################
"""

def create_web_user(user: WebUser) -> UUID:
    """Business logic method to validate and create a web user."""
    logger = logging.getLogger("main." + __name__)
    
    # Validation logic
    if not user.name or not user.name.strip():
        logger.error("Failed to create web user: 'name' is empty.")
        raise ValueError("User name cannot be empty.")
        
    if not user.login_name or not user.login_name.strip():
        logger.error("Failed to create web user: 'login_name' is empty.")
        raise ValueError("Login name cannot be empty.")

    db_conn_string = get_postgres_conn_string()
    user_uuid = None 
    with psycopg.connect(db_conn_string) as conn:
        try:
            user_uuid = _store_web_user(conn, user)
            conn.commit()
        except Exception as e:
            conn.rollback()
            logger.exception(f"database errors during web use create")
            raise e 

    return user_uuid


def start_web_session(login_name: str) -> UUID:
    
    logger = logging.getLogger("main." + __name__)
    db_conn_string = get_postgres_conn_string()
    session_uuid = None

    with psycopg.connect(db_conn_string) as conn:
        try:
            # 1. fetch user_uuid on login_name 
            user_uuid = _get_user_uuid(conn, login_name)
            if not user_uuid:
                logger.error("User with login_name '%s' not found.", login_name)
                raise ValueError(f"User with login_name '{login_name}' does not exist.")
            
            # 2. Check if a session already exists for this user
            existing_session_uuid = _get_web_session(conn, user_uuid)
            if existing_session_uuid:
                logger.info("Existing session found for user_uuid %s: %s", user_uuid, existing_session_uuid)
                return existing_session_uuid

            # 3. Otherwise create a new session
            session_uuid = _store_web_session(conn, user_uuid)
            conn.commit()
            logger.info("Created new web session %s for user_uuid %s", session_uuid, user_uuid)

        except Exception as e:
            conn.rollback()
            logger.exception("Database error during session start for login_name: %s", login_name)
            raise e

    return session_uuid



def update_word_tracker(
        session_uuid: UUID, 
        game_name: str, 
        w_level: int, 
        batch_size: int) -> List[str]:
    """
    Business logic method to retrieve non-repeating Hindi 
    tokens for a game session and record them in word_tracker.
    """
    logger = logging.getLogger("main." + __name__)

    # Validation logic
    if not game_name or not game_name.strip():
        logger.error("Failed to update word tracker: 'game_name' is empty.")
        raise ValueError("Game name cannot be empty.")

    if batch_size <= 0:
        logger.error("Failed to update word tracker: invalid batch_size %s", batch_size)
        raise ValueError("Batch size must be greater than zero.")

    db_conn_string = get_postgres_conn_string()
    fetched_tokens: List[str] = []

    with psycopg.connect(db_conn_string) as conn:
        try:
            fetched_tokens = _store_word_tracker_batch(
                conn, session_uuid, game_name, w_level, batch_size
            )
            conn.commit()
            logger.info(
                "Fetched and tracked %d new tokens for session_uuid %s (level=%d)",
                len(fetched_tokens),
                session_uuid,
                w_level,
            )
        except Exception as e:
            conn.rollback()
            logger.exception(
                "Database error updating word_tracker for session_uuid %s", session_uuid
            )
            raise e

    return fetched_tokens


def clear_session(login_name: str) -> int:
    """
    Business logic method to clear all web sessions for a given login_name.
    Cascade deletion in PostgreSQL automatically removes linked word_tracker entries.
    Returns the number of sessions deleted.
    """
    logger = logging.getLogger("main." + __name__)

    if not login_name or not login_name.strip():
        logger.error("Failed to clear session: 'login_name' is empty.")
        raise ValueError("Login name cannot be empty.")

    db_conn_string = get_postgres_conn_string()
    with psycopg.connect(db_conn_string) as conn:
        try:
            deleted_count = _delete_web_sessions_by_login_name(conn, login_name)
            conn.commit()
            logger.info("Cleared %d session(s) for login_name: %s", deleted_count, login_name)
            return deleted_count
        
        except Exception as e:
            conn.rollback()
            logger.exception("Database error while clearing sessions for login_name: %s", login_name)
            raise e