from uuid import UUID
from fastapi import APIRouter, HTTPException, status
from pydantic import BaseModel, Field
from typing import List
from typing import Dict, Any, Optional
from core.user import start_web_session, update_word_tracker
from core.user import save_game_state, get_game_state, reset_game_level



game_router = APIRouter(
    prefix="/game",
    tags=["GAME"],
    responses={404: {"description": "game router not found"}},
)


class StartSessionRequest(BaseModel):
    login_name: str = Field(..., min_length=1, description="Unique login name of the user")


class StartSessionResponse(BaseModel):
    session_uuid: UUID

class NextWordsRequest(BaseModel):
    session_uuid: UUID
    game_name: str = Field(..., min_length=1, description="Name of the active mini-game")
    game_level: int = Field(..., ge=0, description="Difficulty level, must be 0 or higher")
    batch_size: int = Field(..., gt=0, description="Number of unique words to fetch (> 0)")


class NextWordsResponse(BaseModel):
    tokens: List[str]

class SaveGameStateRequest(BaseModel):
    session_uuid: UUID
    game_name: str = Field(..., max_length=64)
    game_data: Dict[str, Any]

class SaveGameStateResponse(BaseModel):
    session_uuid: UUID
    game_name: str

class GetGameStateRequest(BaseModel):
    session_uuid: UUID
    game_name: str = Field(..., max_length=64)


class GetGameStateResponse(BaseModel):
    session_uuid: UUID
    game_name: str
    game_data: Dict[str, Any]

class ResetLevelRequest(BaseModel):
    session_uuid: UUID = Field(..., description="Unique UUID for the user session")
    game_name: str = Field(..., example="MONSTER", description="Name of the game module")
    game_level: int = Field(..., example=1, description="Level number to reset progress for")

class ResetLevelResponse(BaseModel):
    status: str = "success"
    message: str
    deleted_count: int

@game_router.post(
    "/session/start",
    response_model=StartSessionResponse,
    status_code=status.HTTP_200_OK,
    summary="Start or retrieve a game session",
)
def start_session(payload: StartSessionRequest):
    """
    Starts a new web session for the given login_name.
    If a session already exists for the user, returns the existing session_uuid.
    """
    try:
        session_uuid = start_web_session(payload.login_name)
        return StartSessionResponse(session_uuid=session_uuid)

    except ValueError as e:
        # Maps validation/user non-existence errors to 400 Bad Request
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(e),
        )


@game_router.post(
    "/words/next",
    response_model=NextWordsResponse,
    status_code=status.HTTP_200_OK,
    summary="Fetch the next batch of untracked Hindi word tokens for a session",
)
def get_next_words(payload: NextWordsRequest):
    """
    Retrieves a random batch of untracked Hindi tokens for the given 
    session_uuid and level, and updates the word tracker in a single 
    transaction.
    """
    try:
        tokens = update_word_tracker(
            session_uuid=payload.session_uuid,
            game_name=payload.game_name,
            w_level=payload.game_level,
            batch_size=payload.batch_size,
        )
        
        return NextWordsResponse(tokens=tokens)

    except ValueError as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(e),
        )
    

@game_router.post(
    "/state/save",
    response_model=SaveGameStateResponse,
    status_code=status.HTTP_200_OK,
    summary="Save or update game state",
)
def save_state(payload: SaveGameStateRequest):
    """
    Saves or updates the JSONB game state for a given session and game name.
    """
    try:
        save_game_state(
            session_uuid=payload.session_uuid,
            game_name=payload.game_name,
            game_data=payload.game_data
        )
        return SaveGameStateResponse(
            session_uuid=payload.session_uuid,
            game_name=payload.game_name
        )

    except ValueError as e:
        # Maps non-existent session errors to 400 Bad Request
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(e),
        )


@game_router.post(
    "/state/get",
    response_model=GetGameStateResponse,
    status_code=status.HTTP_200_OK,
    summary="Retrieve saved game state",
)
def get_game_state_endpoint(payload: GetGameStateRequest):
    """
    Retrieves the saved game state for a given session and game name.
    """
    try:
        state_record = get_game_state(
            session_uuid=payload.session_uuid, 
            game_name=payload.game_name
        )
        if not state_record:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"No game state found for session '{payload.session_uuid}' and game '{payload.game_name}'.",
            )
        return GetGameStateResponse(**state_record)

    except ValueError as e:
        # Treats session non-existence as 404
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=str(e),
        )
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="An error occurred while retrieving the game state.",
        )



@game_router.post(
    "/level/reset",
    response_model=ResetLevelResponse,
    status_code=status.HTTP_200_OK,
    summary="Reset word tracker progress for a specific game level",
)
def reset_level_progress_endpoint(payload: ResetLevelRequest):
    """
    Clears all tracked words for the specified session, game, and level.
    """
    try:
        deleted_count = reset_game_level(
            session_uuid=payload.session_uuid,
            game_name=payload.game_name,
            game_level=payload.game_level,
        )
        return ResetLevelResponse(
            status="success",
            message=f"Successfully reset level {payload.game_level} progress.",
            deleted_count=deleted_count,
        )

    except ValueError as e:
        # Treats non-existent session as 404
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=str(e),
        )
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="An error occurred while resetting the level progress.",
        )