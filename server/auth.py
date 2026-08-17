"""A shared-password gate for judges, not a user system.

Why this exists: the chat endpoint calls Anthropic's API on every message,
so leaving a publicly-reachable deployment open to anyone who finds the URL
means anyone's token usage lands on your bill, not just judges'. This isn't
trying to be a real auth system — there are no accounts, no per-user
anything — it's one shared password, checked server-side, backing a signed
session cookie so judges don't have to re-enter it on every page load.

The signing key is derived from JUDGE_ACCESS_PASSWORD itself (HMAC-SHA256),
not a separate secret — which means rotating the password by changing that
one env var and redeploying automatically invalidates every existing
session, with no extra secret to manage.

Set JUDGE_ACCESS_PASSWORD to enable the gate. Leave it unset and the whole
thing is a no-op — every check passes — which is what local development and
`make dev` want by default.
"""

import hashlib
import hmac
import logging
import os
import time

from fastapi import APIRouter, HTTPException, Request, Response
from pydantic import BaseModel

logger = logging.getLogger(__name__)

COOKIE_NAME = "mma_judge_session"
SESSION_TTL_SECONDS = int(os.getenv("JUDGE_SESSION_TTL_HOURS", "168")) * 3600  # 7 days

# Paths that stay reachable with no session — the login flow itself, and a
# bare health probe for infra/uptime checks.
OPEN_PATH_PREFIXES = ("/api/auth/", "/api/health")


def auth_enabled() -> bool:
    return bool(os.getenv("JUDGE_ACCESS_PASSWORD"))


def _secret() -> bytes:
    password = os.getenv("JUDGE_ACCESS_PASSWORD", "")
    return hashlib.sha256(password.encode()).digest()


def _sign(payload: str) -> str:
    sig = hmac.new(_secret(), payload.encode(), hashlib.sha256).hexdigest()
    return f"{payload}.{sig}"


def _verify(token: str) -> bool:
    try:
        payload, sig = token.rsplit(".", 1)
        expected_sig = hmac.new(_secret(), payload.encode(), hashlib.sha256).hexdigest()
        if not hmac.compare_digest(sig, expected_sig):
            return False
        _, _, exp_str = payload.partition(":")
        return time.time() < int(exp_str)
    except (ValueError, IndexError):
        return False


def is_path_open(path: str) -> bool:
    return not path.startswith("/api/") or any(path.startswith(p) for p in OPEN_PATH_PREFIXES)


def request_is_authenticated(request: Request) -> bool:
    if not auth_enabled():
        return True
    token = request.cookies.get(COOKIE_NAME)
    return bool(token and _verify(token))


router = APIRouter(prefix="/api/auth", tags=["auth"])


class LoginRequest(BaseModel):
    password: str


@router.get("/status")
def status():
    """Lets the frontend decide whether to show the login screen at all."""
    return {"auth_required": auth_enabled()}


@router.get("/check")
def check(request: Request):
    return {"authenticated": request_is_authenticated(request)}


@router.post("/login")
def login(body: LoginRequest, response: Response):
    expected = os.getenv("JUDGE_ACCESS_PASSWORD")
    if not expected:
        return {"ok": True}

    # Compare as bytes, not str: hmac.compare_digest refuses to compare str
    # objects containing any non-ASCII character (raises TypeError), which a
    # generated judge password can easily contain.
    if not hmac.compare_digest(body.password.encode("utf-8"), expected.encode("utf-8")):
        logger.warning("Judge login: incorrect password attempt")
        raise HTTPException(status_code=401, detail="Incorrect password")

    exp = int(time.time()) + SESSION_TTL_SECONDS
    token = _sign(f"exp:{exp}")
    response.set_cookie(
        COOKIE_NAME,
        token,
        max_age=SESSION_TTL_SECONDS,
        httponly=True,
        samesite="lax",
        secure=os.getenv("COOKIE_SECURE", "true").lower() == "true",
    )
    return {"ok": True}


@router.post("/logout")
def logout(response: Response):
    response.delete_cookie(COOKIE_NAME)
    return {"ok": True}
