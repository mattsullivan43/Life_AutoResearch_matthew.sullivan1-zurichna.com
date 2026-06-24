"""auth.py — Cognito JWT verification.

Enabled when COGNITO_POOL_ID + COGNITO_CLIENT_ID are set (on the deployed box).
Verifies an access/id token's signature against the pool's JWKS, plus issuer,
expiry and client. Local dev (no env) -> disabled, app is open.
"""
import os
import jwt
from jwt import PyJWKClient

REGION = os.environ.get("COGNITO_REGION", "us-east-1")
POOL = os.environ.get("COGNITO_POOL_ID", "")
CLIENT = os.environ.get("COGNITO_CLIENT_ID", "")
ISSUER = f"https://cognito-idp.{REGION}.amazonaws.com/{POOL}" if POOL else ""
_jwk = PyJWKClient(f"{ISSUER}/.well-known/jwks.json") if POOL else None

def enabled():
    return bool(POOL and CLIENT)

def config():
    return {"enabled": enabled(), "region": REGION, "userPoolId": POOL, "clientId": CLIENT}

def verify(token):
    """Return the claims if the token is a valid Cognito token for our client, else None."""
    if not token or not _jwk:
        return None
    try:
        key = _jwk.get_signing_key_from_jwt(token).key
        claims = jwt.decode(token, key, algorithms=["RS256"], issuer=ISSUER,
                            options={"verify_aud": False})
        use = claims.get("token_use")
        if use == "access" and claims.get("client_id") == CLIENT:
            return claims
        if use == "id" and claims.get("aud") == CLIENT:
            return claims
        return None
    except Exception:
        return None
