"""
Chat-related data models.

This module contains models for chat messages and requests.
"""

from typing import Any, Literal

from pydantic import Field

from app.models.common import SnakeOrAliasModel


class MessagePart(SnakeOrAliasModel):
    """Part of a message with type and content."""

    type: Literal["text"] = Field(alias="type")
    text: str = Field(alias="text")


class Chat(SnakeOrAliasModel):
    """Chat model representing a chat entity in the database."""

    chat_id: str = Field(alias="id", min_length=1)
    user_id: str = Field(alias="userId", min_length=1)
    chat_created_at: str = Field(alias="createdAt", min_length=1)
    title: str = Field(alias="title", min_length=1)
    visibility: str = Field(alias="visibility", min_length=1)


class SaveMessageRequestMessage(SnakeOrAliasModel):
    """Message model representing a save message request."""

    chat_id: str = Field(alias="chatId", min_length=1)
    role: Literal["user", "assistant"] = Field(alias="role")
    parts: list[MessagePart] = Field(alias="parts")
    attachments: list[Any] = Field(alias="attachments")
    message_id: str = Field(alias="id", min_length=1)


class Message(SaveMessageRequestMessage):
    """Message model representing a message entity in the database."""

    created_at: str = Field(alias="createdAt", min_length=1)


class Vote(SnakeOrAliasModel):
    """Vote model representing a vote entity in the database."""

    chat_id: str = Field(alias="chatId", min_length=1)
    message_id: str = Field(alias="messageId", min_length=1)
    is_upvoted: bool = Field(alias="isUpvoted")


class Stream(SnakeOrAliasModel):
    """Stream model representing a stream entity in the database."""

    chat_id: str = Field(alias="chatId", min_length=1)
    stream_id: str = Field(alias="id", min_length=1)
    created_at: str = Field(alias="createdAt", min_length=1)


#
# Request and response models for API endpoints
#


class WireMessage(SnakeOrAliasModel):
    """Wire message model for the chat request format."""

    role: Literal["user", "assistant", "system"] = Field(alias="role")  # TODO: remove system
    parts: list[MessagePart] = Field(alias="parts")
    id: str | None = Field(default=None, alias="id")
    created_at: str | None = Field(default=None, alias="createdAt")


class ChatRequest(SnakeOrAliasModel):
    """Request model for the chat endpoint."""

    messages: list[WireMessage] = Field(alias="messages")
    user_id: str = Field(alias="userId", min_length=1)


class CreateChatRequest(SnakeOrAliasModel):
    """Request model for creating a new chat."""

    chat_id: str = Field(alias="id", min_length=1)
    user_id: str = Field(alias="userId", min_length=1)
    title: str = Field(alias="title", min_length=1)
    visibility: str = Field(alias="visibility", min_length=1)


class SaveMessagesRequest(SnakeOrAliasModel):
    """Request model for saving messages to a chat."""

    user_id: str = Field(alias="userId", min_length=1)
    messages: list[SaveMessageRequestMessage] = Field(alias="messages")


class VoteMessageRequest(SnakeOrAliasModel):
    """Request model for voting on a message."""

    vote_type: Literal["up", "down"] = Field(alias="voteType")


class CreateStreamRequest(SnakeOrAliasModel):
    """Request model for creating a stream ID."""

    stream_id: str = Field(alias="id", min_length=1)


class UpdateChatVisibilityRequest(SnakeOrAliasModel):
    """Request model for updating chat visibility."""

    visibility: str = Field(alias="visibility", min_length=1)


class StreamIdsResponse(SnakeOrAliasModel):
    """Response model for stream IDs list."""

    stream_ids: list[str] = Field(default_factory=list, alias="ids")


class ChatListResponse(SnakeOrAliasModel):
    """Response model for paginated chat list."""

    chats: list[Chat] = Field(alias="chats")
    has_more: bool = Field(default=False, alias="hasMore")


class MessageCountResponse(SnakeOrAliasModel):
    """Response model for message count."""

    count: int = Field(alias="count")
