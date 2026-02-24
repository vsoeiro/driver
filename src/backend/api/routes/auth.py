"""Authentication routes for supported OAuth providers."""

import logging
import secrets

import httpx
from fastapi import APIRouter, HTTPException, Query, Request, Response, status
from fastapi.responses import HTMLResponse, RedirectResponse
from sqlalchemy import select

from backend.api.dependencies import DBSession
from backend.core.config import get_settings
from backend.core.security import decrypt_token, encrypt_token
from backend.db.models import LinkedAccount
from backend.services.dropbox.auth import get_dropbox_auth_service
from backend.services.google.auth import get_google_auth_service
from backend.services.microsoft.auth import get_microsoft_auth_service

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/auth", tags=["Authentication"])


@router.get("/google/login")
async def google_login() -> RedirectResponse:
    """Initiate Google OAuth2 login flow."""
    settings = get_settings()
    auth_service = get_google_auth_service()

    if not settings.google_client_id or not settings.google_client_secret:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Google OAuth is not configured.",
        )

    state = secrets.token_urlsafe(32)
    auth_url = auth_service.get_auth_url(settings.google_redirect_uri, state)
    response = RedirectResponse(url=auth_url, status_code=status.HTTP_302_FOUND)

    response.set_cookie(
        key="oauth_google_state",
        value=encrypt_token(state),
        httponly=True,
        secure=False,
        samesite="lax",
        max_age=600,
        path="/",
    )
    return response


@router.get("/dropbox/login")
async def dropbox_login() -> RedirectResponse:
    """Initiate Dropbox OAuth2 login flow."""
    settings = get_settings()
    auth_service = get_dropbox_auth_service()

    if not settings.dropbox_client_id or not settings.dropbox_client_secret:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Dropbox OAuth is not configured.",
        )

    state = secrets.token_urlsafe(32)
    auth_url = auth_service.get_auth_url(settings.dropbox_redirect_uri, state)
    response = RedirectResponse(url=auth_url, status_code=status.HTTP_302_FOUND)

    response.set_cookie(
        key="oauth_dropbox_state",
        value=encrypt_token(state),
        httponly=True,
        secure=False,
        samesite="lax",
        max_age=600,
        path="/",
    )
    return response


@router.get("/google/callback")
async def google_callback(
    request: Request,
    db: DBSession,
    code: str = Query(..., description="Authorization code from Google"),
    state: str = Query(..., description="State parameter for CSRF validation"),
) -> Response:
    """Handle Google OAuth2 callback and persist linked account."""
    auth_service = get_google_auth_service()
    settings = get_settings()

    encrypted_state = request.cookies.get("oauth_google_state")
    if not encrypted_state:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Session expired or invalid. Please try logging in again.",
        )

    try:
        stored_state = decrypt_token(encrypted_state)
        if not stored_state or stored_state != state:
            raise ValueError("Invalid state")
    except Exception:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid session state.",
        )

    token_result = auth_service.exchange_code_for_tokens(
        code, settings.google_redirect_uri
    )
    if not token_result:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Failed to authenticate with Google",
        )

    claims = token_result.id_token_claims
    google_account_id = claims.get("sub")
    email = claims.get("email", "")
    name = claims.get("name") or email.split("@")[0] or "Google User"

    if not google_account_id:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Could not determine Google account ID",
        )

    await _upsert_linked_account(
        db=db,
        provider="google",
        provider_account_id=google_account_id,
        email=email,
        name=name,
        access_token=token_result.access_token,
        refresh_token=token_result.refresh_token,
        expires_at=token_result.expires_at,
    )

    success_response = _success_html_response()
    success_response.delete_cookie("oauth_google_state", path="/")
    return success_response


@router.get("/dropbox/callback")
async def dropbox_callback(
    request: Request,
    db: DBSession,
    code: str = Query(..., description="Authorization code from Dropbox"),
    state: str = Query(..., description="State parameter for CSRF validation"),
) -> Response:
    """Handle Dropbox OAuth2 callback and persist linked account."""
    auth_service = get_dropbox_auth_service()
    settings = get_settings()

    encrypted_state = request.cookies.get("oauth_dropbox_state")
    if not encrypted_state:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Session expired or invalid. Please try logging in again.",
        )

    try:
        stored_state = decrypt_token(encrypted_state)
        if not stored_state or stored_state != state:
            raise ValueError("Invalid state")
    except Exception:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid session state.",
        )

    token_result = auth_service.exchange_code_for_tokens(
        code, settings.dropbox_redirect_uri
    )
    if not token_result:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Failed to authenticate with Dropbox",
        )

    profile = await _fetch_dropbox_profile(token_result.access_token)
    dropbox_account_id = profile.get("account_id") or token_result.id_token_claims.get("account_id")
    email = profile.get("email", "")
    name = (
        ((profile.get("name") or {}).get("display_name") if isinstance(profile.get("name"), dict) else None)
        or (email.split("@")[0] if email else None)
        or "Dropbox User"
    )

    if not dropbox_account_id:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Could not determine Dropbox account ID",
        )

    await _upsert_linked_account(
        db=db,
        provider="dropbox",
        provider_account_id=dropbox_account_id,
        email=email,
        name=name,
        access_token=token_result.access_token,
        refresh_token=token_result.refresh_token,
        expires_at=token_result.expires_at,
    )

    success_response = _success_html_response()
    success_response.delete_cookie("oauth_dropbox_state", path="/")
    return success_response


@router.get("/microsoft/login", response_class=RedirectResponse)
async def microsoft_login(request: Request) -> RedirectResponse:
    """Initiate Microsoft OAuth2 login flow.

    Redirects the user directly to Microsoft login page.
    """
    auth_service = get_microsoft_auth_service()
    settings = get_settings()

    flow = auth_service.get_auth_flow(settings.redirect_uri)
    auth_url = flow.get("auth_uri")

    if not auth_url:
        raise HTTPException(status_code=500, detail="Failed to generate auth URL")

    logger.info("Redirecting to Microsoft OAuth")

    response = RedirectResponse(url=auth_url, status_code=status.HTTP_302_FOUND)

    # Store the entire flow in a secure, encrypted cookie
    # In a real production app, we might want to sign this or store just an ID pointing to a DB record
    # But for "no external services", we can store the state in the cookie if it's small enough.
    # However, 'flow' contains the code_verifier which is sensitive.
    # Ideally we encrypt this. Since we have Fernet, let's use it.
    import json

    from backend.core.security import encrypt_token

    flow_json = json.dumps(flow)
    encrypted_flow = encrypt_token(flow_json)

    # Store state in cookie for stateless auth
    response.set_cookie(
        key="oauth_flow",
        value=encrypted_flow,
        httponly=True,
        secure=False,  # Set to True in production with HTTPS
        samesite="lax",
        max_age=600,  # 10 minutes
        path="/",
    )
    logger.info("Set oauth_flow cookie with path=/")
    return response


@router.get("/microsoft/callback")
async def microsoft_callback(
    request: Request,
    db: DBSession,
    code: str = Query(..., description="Authorization code from Microsoft"),
    state: str = Query(..., description="State parameter for CSRF validation"),
) -> Response:
    """Handle Microsoft OAuth2 callback.

    Exchanges the authorization code for tokens.
    """
    auth_service = get_microsoft_auth_service()

    logger.info("Callback received. Cookies: %s", request.cookies.keys())
    encrypted_flow = request.cookies.get("oauth_flow")
    if not encrypted_flow:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Session expired or invalid. Please try logging in again.",
        )

    try:
        import json

        flow_json = decrypt_token(encrypted_flow)
        if not flow_json:
            raise ValueError("Decryption failed")

        flow = json.loads(flow_json)
    except Exception:
        logger.error("Failed to decrypt oauth flow cookie")
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid session state.",
        )

    token_result = auth_service.exchange_code_for_tokens(
        flow, dict(request.query_params)
    )
    if not token_result:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Failed to authenticate with Microsoft",
        )

    claims = token_result.id_token_claims
    ms_account_id = claims.get("oid") or claims.get("sub")
    email = claims.get("preferred_username") or claims.get("email", "")
    name = claims.get("name", email.split("@")[0])

    if not ms_account_id:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Could not determine Microsoft account ID",
        )

    await _upsert_linked_account(
        db=db,
        provider="microsoft",
        provider_account_id=ms_account_id,
        email=email,
        name=name,
        access_token=token_result.access_token,
        refresh_token=token_result.refresh_token,
        expires_at=token_result.expires_at,
    )

    success_response = _success_html_response()
    success_response.delete_cookie("oauth_flow", path="/")
    return success_response


async def _upsert_linked_account(
    db: DBSession,
    provider: str,
    provider_account_id: str,
    email: str,
    name: str,
    access_token: str,
    refresh_token: str | None,
    expires_at,
) -> None:
    query = select(LinkedAccount).where(
        LinkedAccount.provider == provider,
        LinkedAccount.provider_account_id == provider_account_id,
    )
    result = await db.execute(query)
    linked_account = result.scalar_one_or_none()

    if linked_account:
        linked_account.access_token_encrypted = encrypt_token(access_token)
        if refresh_token:
            linked_account.refresh_token_encrypted = encrypt_token(refresh_token)
        linked_account.token_expires_at = expires_at
        linked_account.is_active = True
        linked_account.display_name = name
        linked_account.email = email
    else:
        db.add(
            LinkedAccount(
                provider=provider,
                provider_account_id=provider_account_id,
                email=email,
                display_name=name,
                access_token_encrypted=encrypt_token(access_token),
                refresh_token_encrypted=(
                    encrypt_token(refresh_token) if refresh_token else None
                ),
                token_expires_at=expires_at,
            )
        )

    await db.commit()
    logger.info("Account %s (%s) linked successfully", email, provider)


async def _fetch_dropbox_profile(access_token: str) -> dict:
    try:
        async with httpx.AsyncClient(timeout=httpx.Timeout(20.0, connect=10.0)) as client:
            response = await client.post(
                "https://api.dropboxapi.com/2/users/get_current_account",
                headers={
                    "Authorization": f"Bearer {access_token}",
                    "Content-Type": "application/json",
                },
                json={},
            )
            response.raise_for_status()
            return response.json()
    except httpx.HTTPError as exc:
        logger.warning("Failed to fetch Dropbox profile during callback: %s", exc)
        return {}


def _success_html_response() -> HTMLResponse:
    html_content = """
    <!DOCTYPE html>
    <html>
        <head>
            <title>Account Linked Successful</title>
            <style>
                body {
                    font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, Oxygen, Ubuntu, Cantarell, 'Open Sans', 'Helvetica Neue', sans-serif;
                    display: flex;
                    flex-direction: column;
                    align-items: center;
                    justify-content: center;
                    height: 100vh;
                    margin: 0;
                    background-color: #f0f2f5;
                }
                .container {
                    background: white;
                    padding: 2rem;
                    border-radius: 8px;
                    box-shadow: 0 4px 6px rgba(0, 0, 0, 0.1);
                    text-align: center;
                    max-width: 600px;
                    width: 90%;
                }
                h1 { color: #2ecc71; margin-bottom: 1rem; }
                p { color: #555; margin-bottom: 1.5rem; }
                .btn {
                    display: inline-block;
                    padding: 0.8rem 1.5rem;
                    background-color: #3498db;
                    color: white;
                    text-decoration: none;
                    border-radius: 4px;
                    font-weight: bold;
                    transition: background-color 0.2s;
                }
                .btn:hover { background-color: #2980b9; }
            </style>
        </head>
        <body>
            <div class="container">
                <h1>Account Linked Successfully!</h1>
                <p>Use the account list API to get your Account ID.</p>
                <div class="actions">
                    <a href="/docs" class="btn">Go to Swagger UI</a>
                </div>
            </div>
        </body>
    </html>
    """
    return HTMLResponse(content=html_content, status_code=200)
