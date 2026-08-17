import logging 
import httpx
import time 
from fastapi import Request, Response
from fastapi import APIRouter
from fastapi.responses import StreamingResponse


"""
# code needed in main app 

# noinspection PyUnusedLocal
@asynccontextmanager
async def lifespan(boa_app: FastAPI):
    logger = logging.getLogger("boa.fastapi.main." + __name__)
    async_client = httpx.AsyncClient()
    boa_app.state.async_client = async_client
    
    AppConfig.load()
    # logging setup
    log_config = get_logger_config("global")
    log_file_name = log_config.log_file
    AppConfig.init_logging(log_file=log_file_name, log_level=log_config.log_level)
    # httpx should only log warnings and errors
    logging.getLogger("httpx").setLevel(logging.WARNING)
    logger.info(f"fastapi main app started...")

    yield
    # shutdown events
    # Close the pool cleanly when FastAPI shuts down
    await async_client.aclose()

    
"""

tunnel_router = APIRouter(
    prefix="/tunnel",
    tags=["tunnel"],
    responses={404: {"description": "tunnel router to act as api shim"}},
)

logger = logging.getLogger("boa.fastapi.main.tunnel")


@tunnel_router.api_route("/{path:path}", methods=["GET", "POST"])
async def dynamic_tunnel(path: str, request: Request):

    async_client = request.app.state.async_client
    # 1. Capture metadata for the access log
    # Extracts the actual browser client IP passed down by Nginx headers
    client_ip = request.headers.get("x-real-ip") or request.client.host
    method = request.method
    
    api_machine_url = f"http://localhost:9000/{path}"
    incoming_body = await request.body()
    query_params = request.query_params
    
    headers = dict(request.headers)
    headers.pop("host", None)

    # Start timing the request performance
    start_time = time.perf_counter()


    try:
        timeout = httpx.Timeout(5.0, read=30.0)
        req = async_client.build_request(
            method=method,
            url=api_machine_url,
            headers=headers,
            params=query_params,
            content=incoming_body,
            timeout=timeout
        )
        response_b = await async_client.send(req, stream=True)

        # Calculate exact duration
        duration_ms = (time.perf_counter() - start_time) * 1000

        # 2. Log successful request execution to your file
        logger.info(
            f'Access Log - IP: {client_ip} | Method: {method} | Path: /{path} | '
            f'Status: {response_b.status_code} | Duration: {duration_ms:.2f}ms'
        )

        return StreamingResponse(
            response_b.aiter_raw(),
            status_code=response_b.status_code,
            headers=dict(response_b.headers)
        )

    except httpx.TimeoutException:
        duration_ms = (time.perf_counter() - start_time) * 1000
        logger.error(
            f'Access Log ERROR - IP: {client_ip} | Method: {method} | Path: /{path} | '
            f'Status: 504 Timeout | Duration: {duration_ms:.2f}ms'
        )
        return Response(
            content='{"error": "Machine B took too long to respond"}',
            status_code=504,
            media_type="application/json"
        )
        
    except httpx.RequestError as exc:
        duration_ms = (time.perf_counter() - start_time) * 1000
        logger.error(
            f'Access Log ERROR - IP: {client_ip} | Method: {method} | Path: /{path} | '
            f'Details: {exc} | Duration: {duration_ms:.2f}ms'
        )
        return Response(
            content=f'{{"error": "Tunnel connection failed", "details": "{exc}"}}',
            status_code=502,
            media_type="application/json"
        )
