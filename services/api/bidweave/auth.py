# SPDX-FileCopyrightText: 2026 BidWeave contributors
# SPDX-License-Identifier: Apache-2.0
# Apache-2.0 licensed authentication; no warranty.
from dataclasses import dataclass
from functools import lru_cache
import time
import httpx
import jwt
from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from .config import get_settings

bearer = HTTPBearer(auto_error=False)


@dataclass(frozen=True)
class Principal:
    id: str
    username: str
    tenant_id: str
    roles: tuple[str, ...]
    token: str


_jwks_cache: tuple[float, dict] | None = None


def _jwks() -> dict:
    global _jwks_cache
    settings = get_settings()
    issuer = settings.keycloak_issuer
    if settings.keycloak_jwks_url is None:
        url = issuer.rstrip("/") + "/protocol/openid-connect/certs"
    else:
        url = settings.keycloak_jwks_url
    if _jwks_cache and _jwks_cache[0] > time.time():
        return _jwks_cache[1]
    try:
        response = httpx.get(url, timeout=5)
        response.raise_for_status()
        value = response.json()
        _jwks_cache = (time.time() + 300, value)
        return value
    except Exception as exc:
        raise HTTPException(
            status_code=503, detail="identity provider unavailable"
        ) from exc


def current_user(
    credentials: HTTPAuthorizationCredentials | None = Depends(bearer),
) -> Principal:
    if credentials is None or credentials.scheme.lower() != "bearer":
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED, detail="authentication required"
        )
    settings = get_settings()
    token = credentials.credentials
    try:
        header = jwt.get_unverified_header(token)
        jwks = _jwks()
        key = next(
            (k for k in jwks.get("keys", []) if k.get("kid") == header.get("kid")), None
        )
        if key is None:
            raise ValueError("unknown signing key")
        signing_key = jwt.PyJWK.from_dict(key).key
        claims = jwt.decode(
            token,
            signing_key,
            algorithms=["RS256"],
            audience=settings.keycloak_audience,
            issuer=settings.keycloak_issuer,
            options={"require": ["exp", "iss", "aud", "sub"]},
        )
    except HTTPException:
        raise
    except Exception as exc:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="invalid authentication token",
        ) from exc
    tenant = claims.get("tenant_id")
    subject = claims.get("sub")
    if not tenant or not subject:
        raise HTTPException(status_code=401, detail="token lacks tenant identity")
    realm_roles = claims.get("realm_access", {}).get("roles", [])
    roles = tuple(sorted(set(str(x) for x in realm_roles)))
    return Principal(
        id=str(subject),
        username=str(claims.get("preferred_username", subject)),
        tenant_id=str(tenant),
        roles=roles,
        token=token,
    )


def require_role(*allowed: str):
    def dependency(user: Principal = Depends(current_user)) -> Principal:
        if not any(role in user.roles for role in allowed):
            raise HTTPException(status_code=403, detail="insufficient role")
        return user

    return dependency
