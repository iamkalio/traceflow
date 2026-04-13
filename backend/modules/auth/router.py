"""GitHub OAuth routes.

Flow:
  GET /auth/github              → redirect to GitHub OAuth consent page
  GET /auth/github/callback     → exchange code → upsert User → issue JWT
                                  → redirect to {FRONTEND_URL}/auth/callback?token=<jwt>
  GET /auth/me                  → decode Bearer JWT, return user payload
  POST /auth/logout             → no-op (client clears the token)
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

import httpx
from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import JSONResponse, RedirectResponse

from core import config
from db.models import User
from db.session import SessionLocal

try:
    from jose import JWTError, jwt as jose_jwt
except ImportError as exc:  # pragma: no cover
    raise ImportError("python-jose[cryptography] is required: pip install python-jose[cryptography]") from exc

router = APIRouter(tags=["auth"])

_GITHUB_AUTHORIZE_URL = "https://github.com/login/oauth/authorize"
_GITHUB_TOKEN_URL = "https://github.com/login/oauth/access_token"
_GITHUB_USER_URL = "https://api.github.com/user"
_GITHUB_EMAILS_URL = "https://api.github.com/user/emails"
_JWT_ALGORITHM = "HS256"
_JWT_EXPIRE_DAYS = 30


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_jwt(github_id: int, github_login: str, email: str | None, avatar_url: str | None) -> str:
    tenant_id = str(github_id)
    now = datetime.now(tz=timezone.utc)
    payload = {
        "sub": tenant_id,
        "tenant_id": tenant_id,
        "github_login": github_login,
        "email": email or "",
        "avatar_url": avatar_url or "",
        "iat": int(now.timestamp()),
        "exp": int((now + timedelta(days=_JWT_EXPIRE_DAYS)).timestamp()),
    }
    return jose_jwt.encode(payload, config.jwt_secret(), algorithm=_JWT_ALGORITHM)


def _decode_jwt(token: str) -> dict:
    try:
        return jose_jwt.decode(token, config.jwt_secret(), algorithms=[_JWT_ALGORITHM])
    except JWTError as exc:
        raise HTTPException(status_code=401, detail=f"Invalid or expired token: {exc}") from exc


def _bearer_token(request: Request) -> str:
    auth = request.headers.get("Authorization", "")
    if not auth.startswith("Bearer "):
        raise HTTPException(status_code=401, detail="Missing Authorization: Bearer <token> header.")
    return auth[len("Bearer "):]


def _upsert_user(github_id: int, github_login: str, email: str | None, avatar_url: str | None) -> User:
    session = SessionLocal()
    try:
        user = session.query(User).filter(User.github_id == github_id).first()
        if user:
            user.github_login = github_login
            user.email = email
            user.avatar_url = avatar_url
        else:
            user = User(
                github_id=github_id,
                github_login=github_login,
                email=email,
                avatar_url=avatar_url,
                tenant_id=str(github_id),
            )
            session.add(user)
        session.commit()
        session.refresh(user)
        return user
    finally:
        session.close()


# ---------------------------------------------------------------------------
# Routes
# ---------------------------------------------------------------------------

@router.get("/auth/github")
async def github_login() -> RedirectResponse:
    """Redirect the browser to GitHub's OAuth consent page."""
    client_id = config.github_client_id()
    if not client_id:
        raise HTTPException(
            status_code=500,
            detail="GITHUB_CLIENT_ID is not configured. Set it in your .env file.",
        )
    params = {
        "client_id": client_id,
        "scope": "read:user user:email",
    }
    query = "&".join(f"{k}={v}" for k, v in params.items())
    return RedirectResponse(url=f"{_GITHUB_AUTHORIZE_URL}?{query}", status_code=302)


@router.get("/auth/github/callback")
async def github_callback(code: str | None = None, error: str | None = None) -> RedirectResponse:
    """
    GitHub redirects here after the user authorises.
    Exchange the one-time ``code`` for an access token, fetch the GitHub
    user profile, upsert the User row, mint a JWT, and redirect the browser
    to the frontend callback page with the token in the query string.
    """
    frontend = config.frontend_url().rstrip("/")

    if error or not code:
        reason = error or "missing_code"
        return RedirectResponse(url=f"{frontend}/login?error={reason}", status_code=302)

    client_id = config.github_client_id()
    client_secret = config.github_client_secret()
    if not client_id or not client_secret:
        return RedirectResponse(url=f"{frontend}/login?error=oauth_not_configured", status_code=302)

    async with httpx.AsyncClient(timeout=10) as http:
        # 1. Exchange code for access token
        token_resp = await http.post(
            _GITHUB_TOKEN_URL,
            json={"client_id": client_id, "client_secret": client_secret, "code": code},
            headers={"Accept": "application/json"},
        )
        token_data = token_resp.json()
        access_token = token_data.get("access_token")
        if not access_token:
            return RedirectResponse(url=f"{frontend}/login?error=token_exchange_failed", status_code=302)

        gh_headers = {"Authorization": f"Bearer {access_token}", "Accept": "application/json"}

        # 2. Fetch GitHub user profile
        user_resp = await http.get(_GITHUB_USER_URL, headers=gh_headers)
        if user_resp.status_code != 200:
            return RedirectResponse(url=f"{frontend}/login?error=github_user_fetch_failed", status_code=302)
        gh_user = user_resp.json()
        github_id: int = gh_user["id"]
        github_login: str = gh_user["login"]
        avatar_url: str | None = gh_user.get("avatar_url")

        # 3. Get primary email (may be private, not on user object)
        email: str | None = gh_user.get("email")
        if not email:
            emails_resp = await http.get(_GITHUB_EMAILS_URL, headers=gh_headers)
            if emails_resp.status_code == 200:
                for entry in emails_resp.json():
                    if entry.get("primary") and entry.get("verified"):
                        email = entry["email"]
                        break

    # 4. Upsert user row — tenant_id = str(github_id)
    _upsert_user(github_id, github_login, email, avatar_url)

    # 5. Mint JWT and send to frontend
    token = _make_jwt(github_id, github_login, email, avatar_url)
    return RedirectResponse(
        url=f"{frontend}/auth/callback?token={token}",
        status_code=302,
    )


@router.get("/auth/me")
async def get_me(request: Request) -> JSONResponse:
    """Return the authenticated user's info from their JWT."""
    token = _bearer_token(request)
    payload = _decode_jwt(token)
    return JSONResponse({
        "tenant_id": payload.get("tenant_id"),
        "github_login": payload.get("github_login"),
        "email": payload.get("email"),
        "avatar_url": payload.get("avatar_url"),
    })


@router.post("/auth/logout")
async def logout() -> JSONResponse:
    """Stateless logout — the client drops the token from localStorage."""
    return JSONResponse({"status": "logged_out"})
