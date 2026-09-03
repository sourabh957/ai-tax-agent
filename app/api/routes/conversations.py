from __future__ import annotations

from collections.abc import AsyncGenerator
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException, Query, Response, status
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.core.auth import CurrentUser, get_current_user
from app.db.models.conversation import Conversation, Message
from app.db.models.user import User
from app.db.session import get_db

router = APIRouter()


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


def _build_title(first_message: str | None) -> str:
    if not first_message:
        return "New conversation"
    collapsed = " ".join(first_message.split()).strip()
    return (collapsed[:77] + "...") if len(collapsed) > 80 else collapsed


async def _ensure_anonymous_user(session: AsyncSession) -> None:
    anonymous = await session.get(User, "anonymous")
    if anonymous is not None:
        return

    session.add(
        User(
            id="anonymous",
            email="anonymous@local.dev",
            hashed_password="auth-not-configured",
            is_active=True,
            is_verified=False,
        )
    )
    await session.flush()


async def get_conversation_db() -> AsyncGenerator[AsyncSession, None]:
    try:
        async for session in get_db():
            yield session
    except RuntimeError as exc:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=str(exc),
        )


async def _load_conversation_or_404(
    session: AsyncSession,
    conversation_id: str,
    user_id: str,
) -> Conversation:
    stmt = (
        select(Conversation)
        .options(selectinload(Conversation.messages))
        .where(
            Conversation.id == conversation_id,
            Conversation.user_id == user_id,
        )
    )
    conversation = (await session.execute(stmt)).scalar_one_or_none()
    if conversation is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Conversation not found.")
    return conversation


class MessageResponse(BaseModel):
    id: str
    role: str
    content: str
    citations: list[str] = Field(default_factory=list)
    created_at: datetime
    updated_at: datetime


class ConversationSummaryResponse(BaseModel):
    id: str
    financial_year: str
    title: str
    message_count: int
    last_message_at: datetime
    created_at: datetime
    updated_at: datetime


class ConversationDetailResponse(ConversationSummaryResponse):
    messages: list[MessageResponse] = Field(default_factory=list)


class ConversationCreateRequest(BaseModel):
    financial_year: str = Field(..., min_length=4, max_length=10)
    first_message: str | None = Field(default=None, max_length=4_000)


def _to_summary_response(conversation: Conversation) -> ConversationSummaryResponse:
    return ConversationSummaryResponse(
        id=conversation.id,
        financial_year=conversation.financial_year,
        title=conversation.title,
        message_count=conversation.message_count,
        last_message_at=conversation.last_message_at,
        created_at=conversation.created_at,
        updated_at=conversation.updated_at,
    )


def _to_detail_response(conversation: Conversation) -> ConversationDetailResponse:
    return ConversationDetailResponse(
        **_to_summary_response(conversation).model_dump(),
        messages=[
            MessageResponse(
                id=message.id,
                role=message.role,
                content=message.content,
                citations=message.citations or [],
                created_at=message.created_at,
                updated_at=message.updated_at,
            )
            for message in conversation.messages
        ],
    )


@router.get("/conversations", response_model=list[ConversationSummaryResponse])
async def list_conversations(
    financial_year: str | None = Query(default=None),
    current_user: CurrentUser = Depends(get_current_user),
    session: AsyncSession = Depends(get_conversation_db),
) -> list[ConversationSummaryResponse]:
    stmt = select(Conversation).where(Conversation.user_id == current_user.user_id)
    if financial_year:
        stmt = stmt.where(Conversation.financial_year == financial_year)
    stmt = stmt.order_by(Conversation.last_message_at.desc())

    conversations = (await session.execute(stmt)).scalars().all()
    return [_to_summary_response(conversation) for conversation in conversations]


@router.post(
    "/conversations",
    response_model=ConversationDetailResponse,
    status_code=status.HTTP_201_CREATED,
)
async def create_conversation(
    body: ConversationCreateRequest,
    current_user: CurrentUser = Depends(get_current_user),
    session: AsyncSession = Depends(get_conversation_db),
) -> ConversationDetailResponse:
    if current_user.user_id == "anonymous":
        await _ensure_anonymous_user(session)

    now = _utcnow()
    first_message = body.first_message.strip() if body.first_message else None
    conversation = Conversation(
        user_id=current_user.user_id,
        financial_year=body.financial_year,
        title=_build_title(first_message),
        message_count=1 if first_message else 0,
        last_message_at=now,
    )
    session.add(conversation)
    await session.flush()

    if first_message:
        session.add(
            Message(
                conversation_id=conversation.id,
                role="user",
                content=first_message,
                citations=[],
            )
        )

    await session.commit()
    conversation = await _load_conversation_or_404(session, conversation.id, current_user.user_id)
    return _to_detail_response(conversation)


@router.get("/conversations/{conversation_id}", response_model=ConversationDetailResponse)
async def get_conversation(
    conversation_id: str,
    current_user: CurrentUser = Depends(get_current_user),
    session: AsyncSession = Depends(get_conversation_db),
) -> ConversationDetailResponse:
    conversation = await _load_conversation_or_404(
        session, conversation_id, current_user.user_id
    )
    return _to_detail_response(conversation)


@router.delete("/conversations/{conversation_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_conversation(
    conversation_id: str,
    current_user: CurrentUser = Depends(get_current_user),
    session: AsyncSession = Depends(get_conversation_db),
) -> Response:
    conversation = await _load_conversation_or_404(
        session, conversation_id, current_user.user_id
    )
    await session.delete(conversation)
    await session.commit()
    return Response(status_code=status.HTTP_204_NO_CONTENT)
