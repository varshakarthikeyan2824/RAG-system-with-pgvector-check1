import logging
import secrets
import uuid
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Annotated

import psycopg
from fastapi import Depends, FastAPI, Form, HTTPException, Request, Response
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import HTMLResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from jinja2 import select_autoescape
from pydantic import BaseModel, Field, field_validator
from starlette.datastructures import MutableHeaders
from starlette.exceptions import HTTPException as StarletteHTTPException
from starlette.middleware.sessions import SessionMiddleware
from starlette.responses import JSONResponse

from src.ask import generate_answer_with_citations
from src.auth import require_service_key
from src.config import get_settings
from src.errors import (
    general_exception_handler,
    http_exception_handler,
    validation_exception_handler,
)
from src.logging_config import request_id_var, setup_logging
from src.rate_limit import ask_limiter, login_limiter
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
SECURITY_HEADERS = {
    "Content-Security-Policy": (
        "default-src 'self'; "
        "script-src 'self'; "
        "style-src 'self'; "
        "img-src 'self' data:; "
        "connect-src 'self'; "
        "form-action 'self'; "
        "base-uri 'self'; "
        "frame-ancestors 'none'"
    ),
    "X-Content-Type-Options": "nosniff",
    "Referrer-Policy": "strict-origin-when-cross-origin",
    "Permissions-Policy": "camera=(), microphone=(), geolocation=()",
}

if not is_development:
    # HSTS only makes sense over HTTPS, so keep it out of local development.
    SECURITY_HEADERS["Strict-Transport-Security"] = (
        "max-age=31536000; includeSubDomains"
    )


class SecurityHeadersMiddleware:
    """Adds a request ID and security headers to every HTTP response."""

    def __init__(self, app):
        self.app = app

    async def __call__(self, scope, receive, send):
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return

        request_id = str(uuid.uuid4())
        scope.setdefault("state", {})["request_id"] = request_id
        token = request_id_var.set(request_id)

        async def send_with_headers(message):
            if message["type"] == "http.response.start":
                headers = MutableHeaders(scope=message)
                headers["X-Request-ID"] = request_id
                for name, value in SECURITY_HEADERS.items():
                    headers[name] = value
                logger.info("Request completed: %s", message["status"])
            await send(message)

        try:
            logger.info("Request started: %s %s", scope["method"], scope["path"])
            await self.app(scope, receive, send_with_headers)
        finally:
            request_id_var.reset(token)


MAX_BODY_BYTES = 64 * 1024  # 64 KB


class BodySizeLimitMiddleware:
    """Refuse oversized request bodies before the app reads them."""

    def __init__(self, app, max_bytes: int = MAX_BODY_BYTES):
        self.app = app
        self.max_bytes = max_bytes

    async def __call__(self, scope, receive, send):
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return

        headers = dict(scope["headers"])
        problem = None

        if b"transfer-encoding" in headers:
            problem = (411, "LENGTH_REQUIRED", "Content-Length is required")
        elif b"content-length" in headers:
            try:
                size = int(headers[b"content-length"])
            except ValueError:
                problem = (400, "BAD_REQUEST", "Invalid Content-Length")
            else:
                if size > self.max_bytes:
                    problem = (413, "PAYLOAD_TOO_LARGE", "Request body too large")

        if problem:
            status, code, message = problem
            response = JSONResponse(
                status_code=status,
                content={
                    "error": {"code": code, "message": message},
                    "request_id": scope.get("state", {}).get("request_id"),
                },
            )
            await response(scope, receive, send)
            return

        await self.app(scope, receive, send)


@asynccontextmanager
async def lifespan(_app: FastAPI):
    logging.getLogger(__name__).info("startup complete")
    yield
    # SIGTERM lands here after uvicorn stops accepting new requests and drains
    # running ones. Connections are opened per request and closed by their
    # `with` blocks, so there is nothing else to close.
    logging.getLogger(__name__).info("shutting down cleanly")


app = FastAPI(
    lifespan=lifespan,
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

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins,  # empty by default: no cross-origin access
    allow_credentials=False,  # set True only for a trusted separate front end
    allow_methods=["GET", "POST"],
    allow_headers=["Content-Type", "X-CSRF-Token"],
)

app.add_exception_handler(
    RequestValidationError,
    validation_exception_handler,  # type: ignore[arg-type]  # known FastAPI typing gap
)

app.add_exception_handler(
    StarletteHTTPException,
    http_exception_handler,  # type: ignore[arg-type]  # known FastAPI typing gap
)

app.add_exception_handler(
    Exception,
    general_exception_handler,
)

app.add_middleware(BodySizeLimitMiddleware)
app.add_middleware(SecurityHeadersMiddleware)


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
    """Alive: the process answers. Docker's HEALTHCHECK calls this."""
    return {"status": "healthy"}


@app.get("/health/ready")
def health_ready():
    """Ready: the database answers. Otherwise 503, so a proxy stops sending traffic."""
    try:
        with psycopg.connect(settings.database_url, connect_timeout=3) as conn:
            conn.execute("SELECT 1")
    except psycopg.Error:
        return JSONResponse(status_code=503, content={"status": "database unavailable"})
    return {"status": "ready"}


@app.post("/login", dependencies=[Depends(login_limiter)])
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
        logger.warning("Login rejected: invalid CSRF token")
        raise HTTPException(status_code=403, detail="Invalid CSRF token")

    user = authenticate_user(body.user_id, body.password)

    if user is None:
        logger.warning("Failed login attempt for user_id=%s", body.user_id)
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


@app.post(
    "/knowledge/ask", response_class=HTMLResponse, dependencies=[Depends(ask_limiter)]
)
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


@app.post("/ask", dependencies=[Depends(ask_limiter)])
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
