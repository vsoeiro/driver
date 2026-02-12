"""Authentication routes.

This module provides endpoints for Microsoft OAuth2 authentication flow.
"""

import logging

from fastapi import APIRouter, HTTPException, Query, Request, Response, status
from fastapi.responses import HTMLResponse, RedirectResponse
from sqlalchemy import select
from sqlalchemy.orm import selectinload

from backend.api.dependencies import CurrentUser, DBSession
from backend.core.config import get_settings
from backend.core.security import create_jwt_token, encrypt_token
from backend.db.models import LinkedAccount, User
from backend.schemas.auth import UserInfo
from backend.services.microsoft_auth import get_microsoft_auth_service

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/auth", tags=["Authentication"])


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
    from backend.core.security import encrypt_token
    import json
    
    flow_json = json.dumps(flow)
    encrypted_flow = encrypt_token(flow_json)

    # Store state in cookie for stateless auth
    response.set_cookie(
        key="oauth_flow",
        value=encrypted_flow,
        httponly=True,
        secure=False, # Set to True in production with HTTPS
        samesite="lax",
        max_age=600,  # 10 minutes
    )
    return response


@router.get("/microsoft/callback")
async def microsoft_callback(
    request: Request,
    response: Response,
    db: DBSession,
    code: str = Query(..., description="Authorization code from Microsoft"),
    state: str = Query(..., description="State parameter for CSRF validation"),
) -> Response:
    """Handle Microsoft OAuth2 callback.

    Exchanges the authorization code for tokens.
    """
    auth_service = get_microsoft_auth_service()
    
    encrypted_flow = request.cookies.get("oauth_flow")
    if not encrypted_flow:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Session expired or invalid. Please try logging in again.",
        )
        
    try:
        from backend.core.security import decrypt_token
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

    # Remove the cookie now that we've consumed it
    response.delete_cookie("oauth_flow")

    token_result = auth_service.exchange_code_for_tokens(flow, dict(request.query_params))
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

    query = select(LinkedAccount).options(
        selectinload(LinkedAccount.user)
    ).where(
        LinkedAccount.provider_account_id == ms_account_id
    )
    result = await db.execute(query)
    linked_account = result.scalar_one_or_none()

    if linked_account:
        user = linked_account.user
        linked_account.access_token_encrypted = encrypt_token(token_result.access_token)
        if token_result.refresh_token:
            linked_account.refresh_token_encrypted = encrypt_token(
                token_result.refresh_token
            )
        linked_account.token_expires_at = token_result.expires_at
        linked_account.is_active = True
    else:
        # Check if user is already logged in via session cookie
        existing_user = None
        session_token = request.cookies.get("session_token")
        if session_token:
            try:
                from backend.core.security import decode_jwt_token
                payload = decode_jwt_token(session_token)
                if payload:
                    user_id = payload.get("sub")
                    if user_id:
                        user_query = select(User).where(User.id == user_id)
                        user_result = await db.execute(user_query)
                        existing_user = user_result.scalar_one_or_none()
            except Exception:
                pass

        if existing_user:
            # Link new account to existing logged-in user
            user = existing_user
        else:
            # Find or create user by email
            user_query = select(User).where(User.email == email)
            user_result = await db.execute(user_query)
            user = user_result.scalar_one_or_none()

            if not user:
                user = User(email=email, name=name)
                db.add(user)
                await db.flush()

        linked_account = LinkedAccount(
            user_id=user.id,
            provider="microsoft",
            provider_account_id=ms_account_id,
            email=email,
            display_name=name,
            access_token_encrypted=encrypt_token(token_result.access_token),
            refresh_token_encrypted=(
                encrypt_token(token_result.refresh_token)
                if token_result.refresh_token
                else None
            ),
            token_expires_at=token_result.expires_at,
        )
        db.add(linked_account)

    await db.commit()

    jwt_token = create_jwt_token(str(user.id))

    logger.info("User %s authenticated successfully", user.email)
    
    html_content = f"""
    <!DOCTYPE html>
    <html>
        <head>
            <title>Authentication Successful</title>
            <style>
                body {{
                    font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, Oxygen, Ubuntu, Cantarell, 'Open Sans', 'Helvetica Neue', sans-serif;
                    display: flex;
                    flex-direction: column;
                    align-items: center;
                    justify-content: center;
                    height: 100vh;
                    margin: 0;
                    background-color: #f0f2f5;
                }}
                .container {{
                    background: white;
                    padding: 2rem;
                    border-radius: 8px;
                    box-shadow: 0 4px 6px rgba(0, 0, 0, 0.1);
                    text-align: center;
                    max-width: 600px;
                    width: 90%;
                }}
                h1 {{ color: #2ecc71; margin-bottom: 1rem; }}
                p {{ color: #555; margin-bottom: 1.5rem; }}
                .token-box {{
                    background: #f8f9fa;
                    padding: 1rem;
                    border: 1px solid #ddd;
                    border-radius: 4px;
                    word-break: break-all;
                    margin-bottom: 1.5rem;
                    font-family: monospace;
                    font-size: 0.9rem;
                    max-height: 100px;
                    overflow-y: auto;
                }}
                .actions {{ margin-top: 1rem; }}
                .btn {{
                    display: inline-block;
                    padding: 0.8rem 1.5rem;
                    background-color: #3498db;
                    color: white;
                    text-decoration: none;
                    border-radius: 4px;
                    font-weight: bold;
                    transition: background-color 0.2s;
                }}
                .btn:hover {{ background-color: #2980b9; }}
                .copy-btn {{
                    background-color: #95a5a6;
                    margin-right: 1rem;
                    border: none;
                    cursor: pointer;
                    font-size: 1rem;
                }}
                .copy-btn:hover {{ background-color: #7f8c8d; }}
            </style>
        </head>
        <body>
            <div class="container">
                <h1>Authentication Successful!</h1>
                <p>Your session token has been generated. Copy it below to use in Swagger UI.</p>
                
                <div class="token-box" id="token">{jwt_token}</div>
                
                <div class="actions">
                    <button class="btn copy-btn" onclick="copyToken()">Copy Token</button>
                    <a href="/docs" class="btn">Go to Swagger UI</a>
                </div>
            </div>

            <script>
                function copyToken() {{
                    var tokenText = document.getElementById("token").innerText;
                    navigator.clipboard.writeText(tokenText).then(function() {{
                        alert("Token copied to clipboard!");
                    }}, function(err) {{
                        console.error('Async: Could not copy text: ', err);
                    }});
                }}
            </script>
        </body>
    </html>
    """
    
    response = HTMLResponse(content=html_content, status_code=200)
    response.set_cookie(
        key="session_token",
        value=jwt_token,
        httponly=True,
        secure=False,
        samesite="lax",
        max_age=86400,
    )
    return response


@router.post("/logout")
async def logout(response: Response) -> dict:
    """Logout the current user by clearing the session cookie.

    Parameters
    ----------
    response : Response
        FastAPI response object.

    Returns
    -------
    dict
        Logout confirmation message.
    """
    response.delete_cookie("session_token")
    return {"message": "Logged out successfully"}


@router.get("/me", response_model=UserInfo)
async def get_current_user_info(current_user: CurrentUser) -> UserInfo:
    """Get the current authenticated user's information.

    Parameters
    ----------
    current_user : User
        The authenticated user.

    Returns
    -------
    UserInfo
        User information.
    """
    return UserInfo(
        id=str(current_user.id),
        email=current_user.email,
        name=current_user.name,
    )
