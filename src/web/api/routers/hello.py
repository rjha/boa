from fastapi import APIRouter
from config import get_logger_config

hello_router = APIRouter(
    prefix="/hello",
    tags=["HELLO"],
    responses={404: {"description": "Hello router not found"}},
)


@hello_router.get("/world")
def write_hello_world():
    return {"Hello": "World"}


@hello_router.get("/debug")
def get_debug_info():
    log_config = get_logger_config("global")
    return {
        "log_file": log_config.log_file,
        "log_level": log_config.log_level
    }

