"""The LangGraph agent behind our own FastAPI app (day 18, part 3).

  GET  /health          alive: the process answers
  GET  /health/ready    ready: the model settings are present and the graph builds
  POST /chat            {"question": "..."}                    -> {"thread_id", "status", ...}
  POST /approve         {"thread_id": "...", "approved": bool} -> carries on after the human's decision

State is kept in memory (InMemorySaver): a restart forgets paused runs. Production needs a durable
checkpointer (for example PostgreSQL).
"""

import logging
import os
import threading
import uuid

import httpx
from fastapi import FastAPI, HTTPException
from langgraph.errors import GraphRecursionError
from pydantic import BaseModel, Field, field_validator

from agent_graph import build_graph, resume, start
from llm import ChatModel, OpenAICompatibleChat

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s %(message)s")
log = logging.getLogger("agent-api")

app = FastAPI(title="LangGraph agent service")

_graph = None  # built on first use (tests reset it)
_lock = threading.Lock()
_pending: set[str] = set()  # thread IDs waiting for a human decision
_known: set[str] = set()  # every thread ID we have issued

REQUIRED_ENV = ("LLM_BASE_URL", "LLM_MODEL", "LLM_API_KEY")


def get_model() -> ChatModel:
    """Create the real model client from the environment. Tests replace this function."""
    return OpenAICompatibleChat()


def get_graph():
    """Build the graph once and reuse it."""
    global _graph
    with _lock:
        if _graph is None:
            _graph = build_graph(get_model())
        return _graph


class ChatRequest(BaseModel):
    question: str = Field(min_length=1, max_length=2000)

    @field_validator("question")
    @classmethod
    def not_blank(cls, value: str) -> str:
        if not value.strip():
            raise ValueError("Question cannot be empty")
        return value.strip()


class ApproveRequest(BaseModel):
    thread_id: str = Field(min_length=1, max_length=64)
    approved: bool


def _run(call, *args) -> dict:
    """Run a graph step and turn expected failures into clean HTTP errors."""
    try:
        return call(get_graph(), *args)
    except GraphRecursionError:
        raise HTTPException(status_code=422, detail="The agent hit its step limit.") from None
    except httpx.HTTPError as exc:
        log.warning("model call failed: %s", type(exc).__name__)
        raise HTTPException(status_code=502, detail="The model service is not available.") from None


@app.get("/health")
def health() -> dict[str, str]:
    """Alive check. Docker's HEALTHCHECK calls this."""
    return {"status": "ok"}


@app.get("/health/ready")
def ready() -> dict[str, str]:
    """Ready check: can this service do its job? (No call to the paid model.)"""
    missing = [name for name in REQUIRED_ENV if not os.environ.get(name)]
    if missing:
        raise HTTPException(status_code=503, detail=f"Missing settings: {', '.join(missing)}")
    try:
        get_graph()
    except Exception:  # noqa: BLE001
        log.exception("graph failed to build")
        raise HTTPException(status_code=503, detail="Graph not ready") from None
    return {"status": "ready"}


@app.post("/chat")
def chat(body: ChatRequest) -> dict:
    thread_id = str(uuid.uuid4())
    _known.add(thread_id)
    result = _run(start, body.question, thread_id)
    if result["status"] == "needs_approval":
        _pending.add(thread_id)
    log.info("chat thread=%s status=%s", thread_id, result["status"])
    return {"thread_id": thread_id, **result}


@app.post("/approve")
def approve(body: ApproveRequest) -> dict:
    if body.thread_id not in _known:
        raise HTTPException(status_code=404, detail="Unknown thread ID.")
    if body.thread_id not in _pending:
        raise HTTPException(status_code=409, detail="This thread is not waiting for approval.")
    _pending.discard(body.thread_id)
    result = _run(resume, body.thread_id, body.approved)
    if result["status"] == "needs_approval":
        _pending.add(body.thread_id)
    log.info("approve thread=%s approved=%s status=%s", body.thread_id, body.approved, result["status"])
    return {"thread_id": body.thread_id, **result}
