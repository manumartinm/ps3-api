import logging
from fastapi.exceptions import RequestValidationError
import uvicorn
from fastapi import FastAPI, Request, status
from fastapi.responses import JSONResponse, RedirectResponse
from fastapi.middleware.cors import CORSMiddleware
from config import dotenv_path
from ps3_api.routes import router
from ps3_api.constants import PS3_BACKEND_CORS_ORIGIN
from dotenv import load_dotenv
from pathlib import Path

load_dotenv(dotenv_path)

HOST, PORT = "127.0.0.1", 8081

def create_app() -> FastAPI:
    app = FastAPI(version="1.0.0", title="PS3 API")
    return app

logger = logging.getLogger('ps3_api')

app = create_app()

@app.exception_handler(RequestValidationError)
async def validation_exception_handler(request: Request, exc: RequestValidationError):
	exc_str = f'{exc}'.replace('\n', ' ').replace('   ', ' ')
	logger.error(f"{request}: {exc_str}")
	content = {'status_code': 10422, 'message': exc_str, 'data': None}
	return JSONResponse(content=content, status_code=status.HTTP_422_UNPROCESSABLE_ENTITY)

app.add_middleware(
    # pyrefly: ignore  # bad-argument-type
    CORSMiddleware,
    allow_origins=PS3_BACKEND_CORS_ORIGIN,
    allow_credentials=True,
    allow_methods=["GET", "POST"],
    allow_headers=["*"],
)

app.include_router(router)

@app.get("/", include_in_schema=False)
async def root():
    return RedirectResponse(url="/docs")

def run():
    uvicorn.run(app, host=HOST, port=PORT, access_log=False)

if __name__ == "__main__":
    run()
