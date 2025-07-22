import hashlib
import logging
import os
import time
from collections import defaultdict
from functools import wraps
from typing import Callable

from fastapi import APIRouter, HTTPException, Depends, UploadFile
from fastapi.responses import JSONResponse
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials

from ps3_api.constants import API_KEY

router = APIRouter()
security = HTTPBearer()
logger = logging.getLogger("app")

rate_limit_storage = defaultdict(list)


def rate_limit(max_requests: int = 100, window_seconds: int = 3600) -> Callable:
    def decorator(func):
        @wraps(func)
        async def wrapper(*args, **kwargs):
            request = kwargs.get("request") or args[0]
            client_ip = request.client.host

            current_time = time.time()

            rate_limit_storage[client_ip] = [
                req_time
                for req_time in rate_limit_storage[client_ip]
                if current_time - req_time < window_seconds
            ]

            if len(rate_limit_storage[client_ip]) >= max_requests:
                raise HTTPException(
                    status_code=429, detail="Rate limit exceeded. Try again later."
                )

            rate_limit_storage[client_ip].append(current_time)
            return await func(*args, **kwargs)

        return wrapper

    return decorator


async def verify_token(
    credentials: HTTPAuthorizationCredentials = Depends(security),
) -> str:
    token = credentials.credentials

    if not token or token != API_KEY:
        raise HTTPException(
            status_code=401, detail="Invalid or missing authentication token"
        )

    return token


async def validate_pdf(file: UploadFile) -> UploadFile:
    if file.content_type != "application/pdf":
        raise HTTPException(status_code=400, detail="El archivo debe ser un PDF.")

    return file


def generate_secure_random_hash(length: int = 32) -> str:
    random_bytes = os.urandom(32)  # 32 bytes = 256 bits of randomness

    # Hash the random bytes using SHA256
    sha256_hash = hashlib.sha256(random_bytes).hexdigest()

    # Return a portion of the hash to match the desired length
    return sha256_hash[:length]


@router.post("/get-pdf-data", response_model=list)
# @rate_limit(max_requests=50, window_seconds=3600)  # 50 requests por hora
async def get_pdf_data(
    validated_pdf: UploadFile = Depends(validate_pdf),
    token: str = Depends(verify_token),
):
    pass


@router.get("/health")
async def health_check():
    data = {"status": "healthy", "timestamp": time.time()}

    return JSONResponse(
        content=data,
        headers={
            "X-Content-Type-Options": "nosniff",
            "X-Frame-Options": "DENY",
            "X-XSS-Protection": "1; mode=block",
        },
    )
