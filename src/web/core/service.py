import logging
from typing import Dict, Any, Optional
from pydantic import BaseModel, Field
from fastapi import FastAPI, Request, HTTPException, status
from fastapi.responses import JSONResponse
from fastapi.exceptions import RequestValidationError

logger = logging.getLogger("main." + __name__)

class BoaApiResponse(BaseModel):
    status: str = Field(..., example="success")
    statusCode: int = Field(default=200, example=200)
    message: str = Field(..., example="api call was a success.")
    data: Optional[Dict[str, Any]] = Field(default=None, description="Dynamic key-value payload")


def register_exception_handlers(app: FastAPI) -> None:

    # Handler for uncaugh ValueError
    # return HTTP 400
    @app.exception_handler(ValueError)
    async def value_error_exception_handler(request: Request, exc: ValueError):
        return JSONResponse(
            status_code=status.HTTP_400_BAD_REQUEST,
            content={
                "status": "error",
                "statusCode": status.HTTP_400_BAD_REQUEST,
                "message": str(exc)
            }
        )
    
    @app.exception_handler(HTTPException)
    async def custom_http_exception_handler(request: Request, exc: HTTPException):
        # Ensure detail is string-safe even if a dict or list was passed to detail
        detail_msg = exc.detail if isinstance(exc.detail, (str, dict)) else str(exc.detail)
        
        return JSONResponse(
            status_code=exc.status_code,
            content={
                "status": "error",
                "statusCode": exc.status_code,
                "message": detail_msg
            }
        )

    @app.exception_handler(RequestValidationError)
    async def validation_exception_handler(request: Request, exc: RequestValidationError):
        errors = exc.errors()
        if errors:
            # Format location tuple ('body', 'field') into readable 'body -> field'
            loc_path = " -> ".join(str(loc) for loc in errors[0].get("loc", []))
            error_msg = f"Invalid request payload: {errors[0].get('msg')} at {loc_path}"
        else:
            error_msg = "Invalid request payload."
        
        return JSONResponse(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            content={
                "status": "error",
                "statusCode": status.HTTP_422_UNPROCESSABLE_ENTITY,
                "message": error_msg
            }
        )


    # Handler for unhandled unexpected exceptions -> returns HTTP 500
    @app.exception_handler(Exception)
    async def unhandled_exception_handler(request: Request, exc: Exception):
        logger.exception("Unhandled server error: %s", exc)
        return JSONResponse(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            content={
                "status": "error",
                "statusCode": status.HTTP_500_INTERNAL_SERVER_ERROR,
                "message": "An internal server error occurred."
            }
        )