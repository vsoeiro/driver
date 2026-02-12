"""Authentication routes.

This module provides endpoints for Microsoft OAuth2 authentication flow.
"""

import logging

from fastapi import APIRouter, HTTPException, Query, Request, Response, status
from fastapi.responses import HTMLResponse, RedirectResponse
from sqlalchemy import select
from backend.api.dependencies import DBSession
from backend.core.config import get_settings
from backend.core.security import encrypt_token
from backend.db.models import LinkedAccount
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
        path="/",
    )
    logger.info("Set oauth_flow cookie with path=/")
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
    
    logger.info("Callback received. Cookies: %s", request.cookies.keys())
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

    query = select(LinkedAccount).where(
        LinkedAccount.provider_account_id == ms_account_id
    )
    result = await db.execute(query)
    linked_account = result.scalar_one_or_none()

    if linked_account:
        linked_account.access_token_encrypted = encrypt_token(token_result.access_token)
        if token_result.refresh_token:
            linked_account.refresh_token_encrypted = encrypt_token(
                token_result.refresh_token
            )
        linked_account.token_expires_at = token_result.expires_at
        linked_account.is_active = True
        
        # Update display name/email if changed
        linked_account.display_name = name
        linked_account.email = email
    else:
        linked_account = LinkedAccount(
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

    logger.info("Account %s linked successfully", email)
    
    html_content = f"""
    <!DOCTYPE html>
    <html>
        <head>
            <title>Account Linked Successful</title>
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



