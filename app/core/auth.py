from __future__ import annotations

import logging
from collections.abc import Mapping
from typing import Any

import httpx
from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from jose import JWTError, jwt
from pydantic import BaseModel

from app.core.config import Settings, get_settings

logger = logging.getLogger(__name__)
_bearer_scheme = HTTPBearer(auto_error=False)
_oidc_metadata_cache: dict[str, dict[str, Any]] = {}
_jwks_cache: dict[str, dict[str, Any]] = {}


class CurrentUser(BaseModel):
    user_id: str
    email: str = ""
    name: str = ""


def _unauthorized(detail: str = "Unauthorized") -> HTTPException:
    return HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail=detail,
        headers={"WWW-Authenticate": "Bearer"},
    )


def _is_oidc_configured(settings: Settings) -> bool:
    return bool(settings.oidc_issuer_url and (settings.oidc_audience or settings.oidc_client_id))


def _allow_development_bypass(settings: Settings) -> bool:
    return settings.app_env == "development"


def _build_current_user(claims: Mapping[str, Any]) -> CurrentUser:
    user_id = (
        str(claims.get("sub") or claims.get("user_id") or claims.get("preferred_username") or "")
        .strip()
    )
    if not user_id:
        raise _unauthorized("Token payload is missing subject information.")

    email = str(claims.get("email") or "").strip()
    name = str(
        claims.get("name")
        or claims.get("preferred_username")
        or claims.get("given_name")
        or email
        or user_id
    ).strip()
    return CurrentUser(user_id=user_id, email=email, name=name)


def _anonymous_user() -> CurrentUser:
    return CurrentUser(user_id="anonymous", email="", name="Anonymous")


async def _fetch_json(url: str) -> dict[str, Any]:
    async with httpx.AsyncClient(timeout=5.0, follow_redirects=True) as client:
        response = await client.get(url)
        response.raise_for_status()
        payload = response.json()
        if not isinstance(payload, dict):
            raise _unauthorized("Invalid identity provider response.")
        return payload


async def _get_oidc_metadata(settings: Settings) -> dict[str, Any]:
    issuer_url = settings.oidc_issuer_url.rstrip("/")
    cached = _oidc_metadata_cache.get(issuer_url)
    if cached is not None:
        return cached

    discovery_url = f"{issuer_url}/.well-known/openid-configuration"
    metadata = await _fetch_json(discovery_url)
    _oidc_metadata_cache[issuer_url] = metadata
    return metadata


async def _get_jwks(jwks_uri: str) -> dict[str, Any]:
    cached = _jwks_cache.get(jwks_uri)
    if cached is not None:
        return cached

    jwks = await _fetch_json(jwks_uri)
    _jwks_cache[jwks_uri] = jwks
    return jwks


def _get_signing_key(jwks: Mapping[str, Any], token: str) -> dict[str, Any]:
    header = jwt.get_unverified_header(token)
    kid = header.get("kid")
    keys = jwks.get("keys")
    if not isinstance(keys, list) or not keys:
        raise _unauthorized("Identity provider did not return signing keys.")

    for key in keys:
        if isinstance(key, dict) and key.get("kid") == kid:
            return key

    if len(keys) == 1 and isinstance(keys[0], dict):
        return keys[0]

    raise _unauthorized("No matching signing key found for token.")


async def _validate_oidc_token(token: str, settings: Settings) -> CurrentUser:
    try:
        _ = settings.oidc_client_secret_value
        metadata = await _get_oidc_metadata(settings)
        jwks_uri = str(metadata.get("jwks_uri") or "").strip()
        if not jwks_uri:
            raise _unauthorized("OIDC discovery document is missing jwks_uri.")

        signing_key = _get_signing_key(await _get_jwks(jwks_uri), token)
        audience = settings.oidc_audience or settings.oidc_client_id
        issuer = str(metadata.get("issuer") or settings.oidc_issuer_url).rstrip("/")
        claims = jwt.decode(
            token,
            signing_key,
            algorithms=["RS256", "RS384", "RS512", "ES256", "ES384", "ES512"],
            audience=audience or None,
            issuer=issuer or None,
            options={"verify_aud": bool(audience)},
        )
        return _build_current_user(claims)
    except HTTPException:
        raise
    except httpx.HTTPError as exc:
        logger.warning("OIDC discovery failed: %s", exc)
        raise _unauthorized("Unable to verify identity token.")
    except JWTError as exc:
        logger.warning("OIDC token validation failed: %s", exc)
        raise _unauthorized("Invalid or expired bearer token.")


def _validate_development_jwt(token: str, settings: Settings) -> CurrentUser:
    secret = settings.jwt_secret_key_value
    if not secret:
        raise _unauthorized("Authentication is not configured.")

    try:
        claims = jwt.decode(
            token,
            secret,
            algorithms=["HS256"],
            audience=settings.oidc_audience or None,
            options={"verify_aud": bool(settings.oidc_audience)},
        )
        return _build_current_user(claims)
    except JWTError as exc:
        logger.warning("Development JWT validation failed: %s", exc)
        raise _unauthorized("Invalid or expired bearer token.")


async def get_current_user(
    credentials: HTTPAuthorizationCredentials | None = Depends(_bearer_scheme),
) -> CurrentUser:
    settings = get_settings()

    if credentials is None:
        if _allow_development_bypass(settings):
            return _anonymous_user()
        raise _unauthorized("Missing bearer token.")

    token = credentials.credentials.strip()
    if not token:
        raise _unauthorized("Missing bearer token.")

    if _is_oidc_configured(settings):
        return await _validate_oidc_token(token, settings)

    if _allow_development_bypass(settings) and settings.jwt_secret_key_value:
        return _validate_development_jwt(token, settings)

    if _allow_development_bypass(settings):
        return _anonymous_user()

    raise _unauthorized("Authentication is not configured.")
