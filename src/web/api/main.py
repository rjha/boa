import os
import logging 
from contextlib import asynccontextmanager
from fastapi import FastAPI
from config import AppConfig
from config import get_logger_config
from .routers.llm import llm_router


# noinspection PyUnusedLocal
@asynccontextmanager
async def lifespan(myapp: FastAPI):

    logger = logging.getLogger("boa.fastapi.main." + __name__)
    AppConfig.load()
    log_config = get_logger_config("global")
    log_file_name = log_config.log_file
    AppConfig.init_logging(log_file=log_file_name, log_level=log_config.log_level)
    logger.info(f"fastapi main app started...")
    yield
    # shutdown events

app = FastAPI(lifespan=lifespan)
app.include_router(llm_router)

@app.get("/hello")
def write_hello_world():
    return {"Hello": "World"}


@app.get("/debug")
def get_debug_info():
    log_config = get_logger_config("global")
    return {
        "log_file": log_config.log_file,
        "log_level": log_config.log_level
    }