from fastapi import APIRouter, status
from pydantic import BaseModel, Field
from typing import List
from typing import Dict, Any
from core.user import start_web_session, update_word_tracker
from core.user import save_game_state, get_game_state, reset_game_level
from core.service import BoaApiResponse


game_router = APIRouter(
    prefix="/game",
    tags=["GAME"],
    responses={404: {"description": "game router not found"}},
)


class StartSessionRequest(BaseModel):
    login_name: str = Field(..., min_length=1, description="Unique login name of the user")

class SaveGameStateRequest(BaseModel):
    session_uuid: str
    game_name: str = Field(..., max_length=64)
    game_data: Dict[str, Any]

class GetGameStateRequest(BaseModel):
    session_uuid: str
    game_name: str = Field(..., max_length=64)

class ResetLevelRequest(BaseModel):
    session_uuid: str = Field(..., description="Unique UUID for the user session")
    game_name: str = Field(..., example="MONSTER", description="Name of the game module")
    game_level: int = Field(..., example=1, description="Level number to reset progress for")


class NextWordsRequest(BaseModel):
    session_uuid: str
    game_name: str = Field(..., min_length=1, description="Name of the active mini-game")
    game_level: int = Field(..., ge=0, description="Difficulty level, must be 0 or higher")
    batch_size: int = Field(..., gt=0, description="Number of unique words to fetch (> 0)")



@game_router.post(
    "/session/start",
    response_model=BoaApiResponse,
    status_code=status.HTTP_200_OK,
    responses={
        400: {"model": BoaApiResponse, "description": "Bad Request, user not found or invalid"}
    },
    summary="Start or retrieve a game session",
)
def start_session(payload: StartSessionRequest):
    """
    Starts a new web session for the given login_name.
    If a session already exists for the user, returns the existing session_uuid.
    """
    session_uuid = start_web_session(payload.login_name)
    return BoaApiResponse(
        status="success",
        message="Session started successfully",
        data={"session_uuid": session_uuid}
    )


@game_router.post(
    "/words/next",
    response_model=BoaApiResponse,
    status_code=status.HTTP_200_OK,
    responses={
        400: {"model": BoaApiResponse, "description": "Bad Request, invalid session or game level"}
    },
    summary="Fetch the next batch of untracked Hindi word tokens for a session",
)
def get_next_words(payload: NextWordsRequest):
    """
    Retrieves a random batch of untracked Hindi tokens for the given 
    session_uuid and level, and updates the word tracker in a single 
    transaction.
    """
    tokens = update_word_tracker(
        session_uuid=payload.session_uuid,
        game_name=payload.game_name,
        w_level=payload.game_level,
        batch_size=payload.batch_size,
    )
    
    return BoaApiResponse(
        status="success",
        message=f"Fetched {len(tokens)} word tokens successfully",
        data={"tokens": tokens}
    )


@game_router.post(
    "/state/save",
    response_model=BoaApiResponse,
    status_code=status.HTTP_200_OK,
    responses={
        400: {"model": BoaApiResponse, "description": "Bad Request, invalid session or game data"}
    },
    summary="Save or update game state",
)
def save_state(payload: SaveGameStateRequest):
    """
    Saves or updates the JSONB game state for a given session and game name.
    """
    save_game_state(
        session_uuid=payload.session_uuid,
        game_name=payload.game_name,
        game_data=payload.game_data
    )
    return BoaApiResponse(
        status="success",
        message="Game state saved successfully",
        data={
            "session_uuid": payload.session_uuid,
            "game_name": payload.game_name
        }
    )


@game_router.post(
    "/state/get",
    response_model=BoaApiResponse,
    status_code=status.HTTP_200_OK,
    responses={
        400: {"model": BoaApiResponse, "description": "Bad Request, game state or session not found"}
    },
    summary="Retrieve saved game state",
)
def get_game_state_endpoint(payload: GetGameStateRequest):
    """
    Retrieves the saved game state for a given session and game name.
    """
    state_record = get_game_state(
        session_uuid=payload.session_uuid, 
        game_name=payload.game_name
    )
    if not state_record:
        raise ValueError(f"No game state found for session '{payload.session_uuid}' and game '{payload.game_name}'.")

    return BoaApiResponse(
        status="success",
        message="Game state retrieved successfully",
        data=state_record
    )
    

@game_router.post(
    "/level/reset",
    response_model=BoaApiResponse,
    status_code=status.HTTP_200_OK,
    responses={
            400: {"model": BoaApiResponse, "description": "Bad Request, session not found"}
    },
    summary="Reset word tracker progress for a specific game level",
)
def reset_level_progress_endpoint(payload: ResetLevelRequest):
    """
    Clears all tracked words for the specified session, game, and level.
    """
    deleted_count = reset_game_level(
        session_uuid=payload.session_uuid,
        game_name=payload.game_name,
        game_level=payload.game_level,
    )

    return BoaApiResponse(
        status="success",
        message=f"Successfully reset level {payload.game_level}",
        data={
            "delete_count": deleted_count
        }
    )