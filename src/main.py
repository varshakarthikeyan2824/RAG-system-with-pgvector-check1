import logging
import secrets
import uuid
from pathlib import Path

from fastapi import FastAPI, Form, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import HTMLResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from jinja2 import select_autoescape
from pydantic import BaseModel, field_validator
from starlette.exceptions import HTTPException as StarletteHTTPException
from starlette.middleware.sessions import SessionMiddleware

from src.ask import generate_answer, generate_answer_with_citations
from src.config import get_settings
from src.errors import (
    general_exception_handler,
    http_exception_handler,
    validation_exception_handler,
)
from src.logging_config import request_id_var, setup_logging

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

BASE_DIR = Path(__file__).resolve().parent.parent

templates = Jinja2Templates(directory=str(BASE_DIR / "templates"))

templates.env.autoescape = select_autoescape(
    enabled_extensions=("html", "htm", "xml"),
    default_for_string=True,
)

app.mount(
    "/static",
    StaticFiles(directory=str(BASE_DIR / "static")),
    name="static",
)

app.add_middleware(
    SessionMiddleware,
    secret_key=settings.session_secret_key.get_secret_value(),
    same_site="lax",
    https_only=not is_development,
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
        response.headers["Content-Security-Policy"] = (
            "default-src 'self'; "
            "script-src 'self'; "
            "style-src 'self'; "
            "img-src 'self' data:; "
            "connect-src 'self'; "
            "form-action 'self'; "
            "base-uri 'self'; "
            "frame-ancestors 'none'"
        )
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


@app.get("/knowledge", response_class=HTMLResponse)
def knowledge_page(request: Request):
    csrf_token = secrets.token_urlsafe(32)
    request.session["csrf_token"] = csrf_token

    return templates.TemplateResponse(
        request=request,
        name="knowledge.html",
        context={"csrf_token": csrf_token},
    )


@app.post("/knowledge/ask", response_class=HTMLResponse)
def knowledge_ask(
    request: Request,
    question: str = Form(...),
    csrf_token: str = Form(...),
):
    session_token = request.session.get("csrf_token", "")

    if not session_token or not secrets.compare_digest(session_token, csrf_token):
        return HTMLResponse(
            "<p role='alert'>Your session has expired. "
            "Refresh the page and try again.</p>",
            status_code=403,
        )

    if not question.strip():
        return HTMLResponse(
            "<p role='alert'>Please enter a question before submitting.</p>",
            status_code=400,
        )

    result = generate_answer_with_citations(
        question=question.strip(),
        tenant_id="water_company_A",
        user_role="customer",
    )

    context = {
        "answer": result["answer"],
        "citations": result["citations"],
    }

    if request.headers.get("HX-Request") == "true":
        return templates.TemplateResponse(
            request=request,
            name="partials/answer.html",
            context=context,
        )

    return templates.TemplateResponse(
        request=request,
        name="knowledge.html",
        context={
            **context,
            "csrf_token": session_token,
        },
    )


@app.post("/ask")
def ask(request: AskRequest):
    answer = generate_answer(
        question=request.question,
        tenant_id=request.tenant_id,
        user_role=request.user_role,
    )

    return {"answer": answer}
