import logging 
from contextlib import asynccontextmanager
from fastapi import FastAPI
from fastapi import APIRouter
from core.service import register_exception_handlers


# Boa SDK
from config import AppConfig
from config import get_logger_config
from .routers.llm import llm_router
from .routers.game import game_router
from .routers.hello import hello_router


# noinspection PyUnusedLocal
@asynccontextmanager
async def lifespan(boa_app: FastAPI):
    logger = logging.getLogger("boa.fastapi.main." + __name__)
    AppConfig.load()
    log_config = get_logger_config("global")
    log_file_name = log_config.log_file
    AppConfig.init_logging(log_file=log_file_name, log_level=log_config.log_level)
    logger.info(f"fastapi main app started...")
    yield
    # shutdown events


app = FastAPI(lifespan=lifespan)

# Register global exception handlers
register_exception_handlers(app)

main_router = APIRouter(prefix="/boa/v1")
main_router.include_router(hello_router)
main_router.include_router(llm_router)
main_router.include_router(game_router)
app.include_router(main_router)
