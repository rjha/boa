from uuid import UUID
from fastapi import APIRouter, HTTPException, status
from pydantic import BaseModel, Field
from core.user import start_web_session


game_router = APIRouter(
    prefix="/game",
    tags=["GAME"],
    responses={404: {"description": "game router not found"}},
)


class StartSessionRequest(BaseModel):
    login_name: str = Field(..., min_length=1, description="Unique login name of the user")


class StartSessionResponse(BaseModel):
    session_uuid: UUID


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
