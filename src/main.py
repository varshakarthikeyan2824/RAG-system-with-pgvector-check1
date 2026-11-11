import logging
import uuid

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from pydantic import BaseModel, field_validator
from starlette.exceptions import HTTPException as StarletteHTTPException

from ask import generate_answer
from config import get_settings
from errors import (
    general_exception_handler,
    http_exception_handler,
    validation_exception_handler,
)
from logging_config import request_id_var, setup_logging

setup_logging()

logger = logging.getLogger(__name__)

settings = get_settings()
is_development = settings.app_env == "development"

app = FastAPI(
    title="Water Utility RAG API",
    description="API for answering water utility questions",
    version="1.0.0",
    docs_url="/docs" if is_development else None,
    redoc_url="/redoc" if is_development else None,
    openapi_url="/openapi.json" if is_development else None,
)

app.add_exception_handler(
    RequestValidationError,
    validation_exception_handler,
)

app.add_exception_handler(
    StarletteHTTPException,
    http_exception_handler,
)

app.add_exception_handler(
    Exception,
    general_exception_handler,
)


@app.middleware("http")
async def request_id_middleware(request: Request, call_next):
    request_id = str(uuid.uuid4())
    request.state.request_id = request_id

    token = request_id_var.set(request_id)

    try:
        logger.info(
            "Request started: %s %s",
            request.method,
            request.url.path,
        )

        response = await call_next(request)

        response.headers["X-Request-ID"] = request_id

        logger.info("Request completed: %s", response.status_code)

        return response

    finally:
        request_id_var.reset(token)


class AskRequest(BaseModel):
    question: str
    tenant_id: str
    user_role: str

    @field_validator("question")
    @classmethod
    def validate_question(cls, value):
        if not value.strip():
            raise ValueError("Question cannot be empty")

        return value.strip()


@app.get("/health")
def health():
    return {"status": "healthy"}


@app.post("/ask")
def ask(request: AskRequest):
    answer = generate_answer(
        question=request.question,
        tenant_id=request.tenant_id,
        user_role=request.user_role,
    )

    return {"answer": answer}
