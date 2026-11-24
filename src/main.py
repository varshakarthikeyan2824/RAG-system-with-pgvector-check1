import logging
import secrets
import uuid
from pathlib import Path
from typing import Annotated

from fastapi import Depends, FastAPI, Form, HTTPException, Request, Response
from fastapi.exceptions import RequestValidationError
from fastapi.responses import HTMLResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from jinja2 import select_autoescape
from pydantic import BaseModel, Field, field_validator
from starlette.exceptions import HTTPException as StarletteHTTPException
from starlette.middleware.sessions import SessionMiddleware

from src.ask import generate_answer_with_citations
from src.auth import require_service_key
from src.config import get_settings
from src.errors import (
    general_exception_handler,
    http_exception_handler,
    validation_exception_handler,
)
from src.logging_config import request_id_var, setup_logging
from src.retrieval import lookup_user
from src.session import (
    authenticate_user,
    create_session,
    get_session_user,
    revoke_session,
)

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
    question: str = Field(max_length=2000)
    user_id: str

    @field_validator("question")
    @classmethod
    def validate_question(cls, value):
        if not value.strip():
            raise ValueError("Question cannot be empty")

        return value.strip()


class LoginRequest(BaseModel):
    user_id: str
    password: str = Field(min_length=1, max_length=128)


@app.get("/health")
def health():
    return {"status": "healthy"}


@app.post("/login")
def login(
    body: LoginRequest,
    request: Request,
    response: Response,
):
    session_token = request.session.get("csrf_token", "")
    submitted_token = request.headers.get("X-CSRF-Token", "")

    if (
        not session_token
        or not submitted_token
        or not secrets.compare_digest(session_token, submitted_token)
    ):
        raise HTTPException(status_code=403, detail="Invalid CSRF token")

    user = authenticate_user(body.user_id, body.password)

    if user is None:
        raise HTTPException(
            status_code=401,
            detail="Invalid user ID or password",
        )

    token = create_session(user.user_id)

    response.set_cookie(
        key="auth_session",
        value=token,
        httponly=True,
        secure=not is_development,
        samesite="lax",
        max_age=12 * 60 * 60,
        path="/",
    )

    return {"message": "Login successful"}


@app.get("/me")
def get_current_user(request: Request):
    token = request.cookies.get("auth_session", "")
    user = get_session_user(token)

    if user is None:
        raise HTTPException(status_code=401, detail="Not authenticated")

    return {
        "user_id": user.user_id,
        "tenant_id": user.tenant_id,
        "role": user.role,
    }


@app.post("/logout")
def logout(request: Request, response: Response):
    token = request.cookies.get("auth_session", "")
    session_token = request.session.get("csrf_token", "")
    submitted_token = request.headers.get("X-CSRF-Token", "")

    if (
        not session_token
        or not submitted_token
        or not secrets.compare_digest(session_token, submitted_token)
    ):
        raise HTTPException(status_code=403, detail="Invalid CSRF token")

    if not token or not revoke_session(token):
        raise HTTPException(status_code=401, detail="Not authenticated")

    response.delete_cookie(
        key="auth_session",
        httponly=True,
        secure=not is_development,
        samesite="lax",
        path="/",
    )

    return {"message": "Logout successful"}


@app.get("/knowledge", response_class=HTMLResponse)
def knowledge_page(request: Request):
    csrf_token = secrets.token_urlsafe(32)
    request.session["csrf_token"] = csrf_token

    token = request.cookies.get("auth_session", "")
    user = get_session_user(token)

    if user is None:
        return templates.TemplateResponse(
            request=request,
            name="login.html",
            context={"csrf_token": csrf_token},
            status_code=401,
        )

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

    auth_token = request.cookies.get("auth_session", "")
    user = get_session_user(auth_token)

    if user is None:
        return HTMLResponse(
            "<p role='alert'>Your session has expired. Please log in again.</p>",
            status_code=401,
        )

    result = generate_answer_with_citations(
        question=question.strip(),
        tenant_id=user.tenant_id,
        user_role=user.role,
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
def ask(
    body: AskRequest,
    _: Annotated[None, Depends(require_service_key)],
):
    user = lookup_user(body.user_id)
    if user is None:
        raise HTTPException(status_code=403, detail="Unknown user")
    return generate_answer_with_citations(
        question=body.question.strip(), tenant_id=user.tenant_id, user_role=user.role
    )
