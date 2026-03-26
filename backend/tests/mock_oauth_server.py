"""Mock OAuth Server for OpenAI-like OAuth flow testing.

Runs on port 8099 by default. Mimics OpenAI's OAuth endpoints:
- GET /oauth/authorize — authorization form
- POST /oauth/authorize/accept — issue code and redirect
- POST /oauth/token — exchange code/refresh token for access token
- GET /v1/me — return mock user profile

Usage:
    python -m backend.tests.mock_oauth_server
    # or: uvicorn backend.tests.mock_oauth_server:app --reload --port 8099
"""

import secrets
from typing import Dict

from fastapi import FastAPI, Form, Query, HTTPException
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.security import HTTPBearer, HTTPAuthCredentials

app = FastAPI(title="Mock OpenAI OAuth Server")

# In-memory storage for authorization codes
# Format: {code: {"client_id": str, "redirect_uri": str, "scope": str, "state": str}}
_codes: Dict[str, dict] = {}

# In-memory storage for issued tokens
# Format: {access_token: {"user_id": str, "scope": str}}
_tokens: Dict[str, dict] = {}

security = HTTPBearer()


@app.get("/oauth/authorize", response_class=HTMLResponse)
async def get_authorize(
    client_id: str = Query(...),
    redirect_uri: str = Query(...),
    state: str = Query(...),
    scope: str = Query(default="openai-user"),
    response_type: str = Query(default="code"),
):
    """
    GET /oauth/authorize — Render authorization form.

    Query params:
    - client_id: OAuth client ID
    - redirect_uri: Where to redirect after user authorizes
    - state: CSRF token to return unchanged
    - scope: Requested scopes (default: openai-user)
    - response_type: Should be 'code' (default)
    """
    html = f"""
    <!DOCTYPE html>
    <html>
    <head>
        <title>Mock OpenAI OAuth</title>
        <style>
            body {{ font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif; }}
            .container {{ max-width: 500px; margin: 50px auto; padding: 20px; border: 1px solid #ddd; border-radius: 8px; }}
            h1 {{ color: #333; }}
            .form-group {{ margin: 20px 0; }}
            label {{ display: block; font-weight: bold; margin-bottom: 5px; }}
            input[type="text"] {{ width: 100%; padding: 8px; border: 1px solid #ccc; border-radius: 4px; }}
            button {{ background: #10a37f; color: white; padding: 10px 20px; border: none; border-radius: 4px; cursor: pointer; font-size: 16px; }}
            button:hover {{ background: #0e8c6f; }}
            .info {{ background: #f5f5f5; padding: 10px; border-radius: 4px; font-size: 12px; margin: 10px 0; }}
        </style>
    </head>
    <body>
        <div class="container">
            <h1>Authorize Application</h1>
            <div class="info">
                <strong>Client ID:</strong> {client_id}<br>
                <strong>Requested Scopes:</strong> {scope}<br>
                <strong>Redirect URI:</strong> {redirect_uri}
            </div>
            <form method="post" action="/oauth/authorize/accept">
                <input type="hidden" name="client_id" value="{client_id}" />
                <input type="hidden" name="redirect_uri" value="{redirect_uri}" />
                <input type="hidden" name="state" value="{state}" />
                <input type="hidden" name="scope" value="{scope}" />
                <input type="hidden" name="response_type" value="{response_type}" />

                <div class="form-group">
                    <label for="user_email">Email (for mock profile):</label>
                    <input type="text" id="user_email" name="user_email" value="developer@openai-mock.local" />
                </div>

                <button type="submit">Authorize</button>
            </form>
        </div>
    </body>
    </html>
    """
    return html


@app.post("/oauth/authorize/accept")
async def post_authorize_accept(
    client_id: str = Form(...),
    redirect_uri: str = Form(...),
    state: str = Form(...),
    scope: str = Form(default="openai-user"),
    response_type: str = Form(default="code"),
    user_email: str = Form(default="developer@openai-mock.local"),
):
    """
    POST /oauth/authorize/accept — Issue authorization code and redirect.

    Form params:
    - client_id: OAuth client ID
    - redirect_uri: Where to redirect
    - state: CSRF token to return unchanged
    - scope: Requested scopes
    - response_type: Should be 'code'
    - user_email: Email for mock user profile (optional)
    """
    if response_type != "code":
        raise HTTPException(status_code=400, detail="Invalid response_type")

    # Generate authorization code
    code = secrets.token_hex(32)

    # Store code for later token exchange
    _codes[code] = {
        "client_id": client_id,
        "redirect_uri": redirect_uri,
        "scope": scope,
        "state": state,
        "user_email": user_email,
    }

    # Redirect back to client with code and state
    redirect_url = f"{redirect_uri}?code={code}&state={state}"
    return RedirectResponse(url=redirect_url)


@app.post("/oauth/token")
async def post_token(
    grant_type: str = Form(...),
    code: str = Form(default=None),
    client_id: str = Form(...),
    client_secret: str = Form(...),
    redirect_uri: str = Form(default=None),
    refresh_token: str = Form(default=None),
):
    """
    POST /oauth/token — Exchange authorization code for access token.

    Form params:
    - grant_type: 'authorization_code' or 'refresh_token'
    - code: Authorization code (if grant_type=authorization_code)
    - client_id: OAuth client ID
    - client_secret: OAuth client secret (not validated in mock)
    - redirect_uri: Must match original authorize request
    - refresh_token: Refresh token (if grant_type=refresh_token)
    """
    if grant_type == "authorization_code":
        if not code:
            raise HTTPException(status_code=400, detail="Missing code")
        if code not in _codes:
            raise HTTPException(status_code=400, detail="Invalid code")

        code_data = _codes.pop(code)

        if code_data["client_id"] != client_id:
            raise HTTPException(status_code=400, detail="Client ID mismatch")
        if redirect_uri and code_data["redirect_uri"] != redirect_uri:
            raise HTTPException(status_code=400, detail="Redirect URI mismatch")

        # Generate tokens
        access_token = f"mock-access-{secrets.token_hex(32)}"
        new_refresh_token = f"mock-refresh-{secrets.token_hex(32)}"

        # Store access token
        _tokens[access_token] = {
            "user_id": "mock-openai-user-001",
            "user_email": code_data.get("user_email", "developer@openai-mock.local"),
            "scope": code_data["scope"],
        }

        return {
            "access_token": access_token,
            "token_type": "Bearer",
            "expires_in": 3600,
            "refresh_token": new_refresh_token,
            "scope": code_data["scope"],
        }

    elif grant_type == "refresh_token":
        if not refresh_token:
            raise HTTPException(status_code=400, detail="Missing refresh_token")

        # In a real OAuth server, we'd validate the refresh token
        # For this mock, just issue a new access token
        access_token = f"mock-access-{secrets.token_hex(32)}"

        _tokens[access_token] = {
            "user_id": "mock-openai-user-001",
            "user_email": "developer@openai-mock.local",
            "scope": "openai-user",
        }

        return {
            "access_token": access_token,
            "token_type": "Bearer",
            "expires_in": 3600,
            "refresh_token": refresh_token,
            "scope": "openai-user",
        }

    else:
        raise HTTPException(status_code=400, detail=f"Unsupported grant_type: {grant_type}")


@app.get("/v1/me")
async def get_me(credentials: HTTPAuthCredentials = security):
    """
    GET /v1/me — Return mock user profile.

    Requires: Authorization: Bearer <access_token>
    """
    token = credentials.credentials

    if token not in _tokens:
        raise HTTPException(status_code=401, detail="Invalid token")

    token_data = _tokens[token]

    return {
        "id": token_data.get("user_id", "mock-openai-user-001"),
        "email": token_data.get("user_email", "developer@openai-mock.local"),
        "name": "Mock OpenAI User",
        "object": "organization.user",
    }


if __name__ == "__main__":
    import uvicorn

    print()
    print("=" * 70)
    print("Mock OpenAI OAuth Server")
    print("=" * 70)
    print()
    print("Configuration for your .env.development file:")
    print()
    print("  OPENAI_CLIENT_ID=mock-client-id")
    print("  OPENAI_CLIENT_SECRET=mock-client-secret")
    print("  OPENAI_REDIRECT_URI=http://localhost:3000/auth/callback")
    print("  OPENAI_OAUTH_BASE_URL=http://localhost:8099")
    print()
    print("OAuth Endpoints:")
    print("  - GET  http://localhost:8099/oauth/authorize")
    print("  - POST http://localhost:8099/oauth/authorize/accept")
    print("  - POST http://localhost:8099/oauth/token")
    print("  - GET  http://localhost:8099/v1/me")
    print()
    print("Starting server on port 8099...")
    print("=" * 70)
    print()

    uvicorn.run(
        "backend.tests.mock_oauth_server:app",
        host="127.0.0.1",
        port=8099,
        reload=True,
    )
