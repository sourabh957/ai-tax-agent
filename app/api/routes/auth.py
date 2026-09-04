"""
Authentication routes — email/password login and registration.

POST /api/v1/auth/register  — create new user account
POST /api/v1/auth/login     — authenticate, return JWT
GET  /api/v1/auth/me        — return current user info
"""

from __future__ import annotations

import logging
from datetime import datetime, timedelta, timezone

from fastapi import APIRouter, Depends, HTTPException, status
from jose import jwt
from passlib.context import CryptContext
from pydantic import BaseModel, EmailStr, Field
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.auth import CurrentUser, get_current_user
from app.core.config import get_settings
from app.db.models.user import User
from app.db.session import get_db

logger = logging.getLogger(__name__)
router = APIRouter()

_pwd_ctx = CryptContext(schemes=["bcrypt"], deprecated="auto")


def _hash_password(plain: str) -> str:
    return _pwd_ctx.hash(plain)


def _verify_password(plain: str, hashed: str) -> bool:
    return _pwd_ctx.verify(plain, hashed)


def _create_access_token(user: User, secret: str, expire_minutes: int = 60 * 24 * 7) -> str:
    now = datetime.now(timezone.utc)
    claims = {
        "sub": user.id,
        "email": user.email,
        "iat": now,
        "exp": now + timedelta(minutes=expire_minutes),
    }
    return jwt.encode(claims, secret, algorithm="HS256")


class RegisterRequest(BaseModel):
    email: EmailStr
    password: str = Field(min_length=8, max_length=128)
    name: str = Field(default="", max_length=100)


class LoginRequest(BaseModel):
    email: EmailStr
    password: str


class AuthResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"
    user_id: str
    email: str
    name: str


class UserResponse(BaseModel):
    user_id: str
    email: str
    name: str


async def _get_db_session():
    try:
        async for session in get_db():
            yield session
    except RuntimeError as exc:
        raise HTTPException(status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail=str(exc))


@router.post(
    "/auth/register",
    response_model=AuthResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Register a new user account",
)
async def register(
    body: RegisterRequest,
    session: AsyncSession = Depends(_get_db_session),
) -> AuthResponse:
    settings = get_settings()
    if not settings.jwt_secret_key_value:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Authentication is not configured (JWT_SECRET_KEY missing).",
        )

    # Check duplicate email
    existing = (
        await session.execute(select(User).where(User.email == body.email))
    ).scalar_one_or_none()
    if existing:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="An account with this email already exists.",
        )

    user = User(
        email=body.email,
        hashed_password=_hash_password(body.password),
        is_active=True,
        is_verified=False,
    )
    session.add(user)
    await session.commit()
    await session.refresh(user)

    token = _create_access_token(user, settings.jwt_secret_key_value)
    logger.info("New user registered [id=%s email=%s]", user.id, user.email)

    return AuthResponse(
        access_token=token,
        user_id=user.id,
        email=user.email,
        name=body.name or user.email.split("@")[0],
    )


@router.post(
    "/auth/login",
    response_model=AuthResponse,
    summary="Login with email and password",
)
async def login(
    body: LoginRequest,
    session: AsyncSession = Depends(_get_db_session),
) -> AuthResponse:
    settings = get_settings()
    if not settings.jwt_secret_key_value:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Authentication is not configured (JWT_SECRET_KEY missing).",
        )

    user = (
        await session.execute(select(User).where(User.email == body.email))
    ).scalar_one_or_none()

    if not user or not _verify_password(body.password, user.hashed_password):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Incorrect email or password.",
        )

    if not user.is_active:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Your account has been deactivated.",
        )

    token = _create_access_token(user, settings.jwt_secret_key_value)
    logger.info("User logged in [id=%s]", user.id)

    return AuthResponse(
        access_token=token,
        user_id=user.id,
        email=user.email,
        name=user.email.split("@")[0],
    )


@router.get(
    "/auth/me",
    response_model=UserResponse,
    summary="Get current authenticated user",
)
async def me(
    current_user: CurrentUser = Depends(get_current_user),
) -> UserResponse:
    return UserResponse(
        user_id=current_user.user_id,
        email=current_user.email,
        name=current_user.name or current_user.email.split("@")[0] if current_user.email else "User",
    )
