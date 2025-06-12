"""
Chat routes for the chatbot backend.

This module contains the routes for chat-related endpoints.
"""

import uuid
from collections.abc import AsyncGenerator

from fastapi import APIRouter, HTTPException, Query, Request, status
from fastapi.responses import StreamingResponse
from pydantic import ValidationError

from app.custom_logger import get_logger
from app.db.chat import (
    create_stream_id,
    delete_chat_by_id,
    delete_messages_by_chat_id_after_timestamp,
    get_chat_by_id,
    get_message_by_id,
    get_messages_by_chat_id,
    get_stream_ids_by_chat_id,
    get_votes_by_chat_id,
    save_chat,
    save_messages,
    update_chat_visibility_by_id,
    vote_message,
)
from app.models.chat import (
    Chat,
    ChatRequest,
    CreateChatRequest,
    CreateStreamRequest,
    Message,
    MessagePart,
    SaveMessageRequestMessage,
    SaveMessagesRequest,
    Stream,
    StreamIdsResponse,
    UpdateChatVisibilityRequest,
    Vote,
    VoteMessageRequest,
)
from app.models.common import ErrorResponse
from app.prompts import CHAT_SYSTEM_PROMPT
from app.providers.factory import default_provider
from app.providers.test import is_test_prompt, test_provider
from app.utils import stream_chat_chunks

# Configure logging
logger = get_logger()

# Create a router for the chat endpoints
router = APIRouter()


@router.post(
    "/api/chats/{chat_id}/responses",
    status_code=status.HTTP_200_OK,
    responses={
        401: {"model": ErrorResponse, "description": "Unauthorized"},
        400: {"model": ErrorResponse, "description": "Bad Request"},
        500: {"model": ErrorResponse, "description": "Internal Server Error"},
    },
)
async def handle_chat_data(chat_id: str, request: ChatRequest, req: Request) -> StreamingResponse:
    """
    Chat endpoint that processes messages and returns a streaming response.

    Args:
        chat_id: The ID of the chat (not currently used)
        request: The chat request containing messages and metadata.

    Returns:
        A streaming response with chat completions.
    """
    logger.debug(f"Starting chat response for chat_id: {chat_id}")
    try:
        # Generate message ID immediately before any provider calls
        message_id = str(uuid.uuid4())

        # Check if the last message is a test prompt
        last_message_text = request.messages[-1].parts[0].text if request.messages else None
        provider = test_provider if (last_message_text and is_test_prompt(last_message_text)) else default_provider

        # Format messages for the provider
        provider_messages = provider.format_messages_from_request(request)

        # Create generator for immediate first chunk
        async def immediate_first_chunk() -> AsyncGenerator[bytes, None]:
            yield f'f:{{"messageId":"{message_id}"}}\n'.encode()

        # Create generator for the rest of the chunks
        async def delayed_chunks() -> AsyncGenerator[bytes, None]:
            # Create a generator for the provider response
            async def generate_provider_chunks() -> AsyncGenerator[str | dict, None]:
                try:
                    chunk_count = 0
                    chunk_texts = []
                    logger.debug("Starting generation loop")
                    for chunk in provider.stream_chat_response(provider_messages, system_message=CHAT_SYSTEM_PROMPT):
                        # check if client is disconnected
                        if await req.is_disconnected():
                            logger.debug(f"Client disconnected after {chunk_count} chunks")
                            break
                        # Only count text chunks, not usage information
                        if isinstance(chunk, str):
                            chunk_count += 1
                            chunk_texts.append(chunk)
                            if chunk_count % 100 == 0:  # Log every 10 chunks
                                logger.debug(f"Sent {chunk_count} chunks")
                        yield chunk
                    logger.debug(f"Generation complete - yielded {chunk_count} text chunks")
                    save_messages(
                        request.user_id,
                        [
                            SaveMessageRequestMessage(
                                chat_id=chat_id,
                                role="assistant",
                                parts=[MessagePart(type="text", text="".join(chunk_texts))],
                                attachments=[],
                                message_id=message_id,
                            )
                        ],
                    )
                except Exception as e:
                    logger.error(f"Error generating response: {e}")
                    yield f"Error: {e}"

            # Stream the provider chunks through stream_chat_chunks
            async for chunk in stream_chat_chunks(generate_provider_chunks()):
                yield chunk

        # Combine both generators
        async def combined_stream() -> AsyncGenerator[bytes, None]:
            # First, yield the immediate message ID chunk
            async for chunk in immediate_first_chunk():
                yield chunk
            # Then, yield all the delayed chunks
            async for chunk in delayed_chunks():
                yield chunk

        # Return a streaming response with the combined stream
        response = StreamingResponse(combined_stream(), media_type="text/event-stream")

        # Add required headers
        response.headers["Cache-Control"] = "no-cache"
        response.headers["Connection"] = "keep-alive"
        response.headers["x-vercel-ai-data-stream"] = "v1"

        logger.info("Returning streaming response")
        return response

    except Exception as e:
        # Log the error
        logger.error(f"Error processing chat request: {e}")

        # Raise an HTTPException that FastAPI will handle
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=f"Error processing request: {e}"
        ) from e


# Database endpoints for chats, messages, votes, and streams


@router.get("/api/chats/{chat_id}", response_model=Chat, response_model_exclude_none=True)
async def get_chat(chat_id: str) -> Chat:
    """Get chat by ID."""
    logger.debug(f"Getting chat by ID: {chat_id}")

    try:
        chat = get_chat_by_id(chat_id)
    except Exception as err:
        logger.error("Failed to get chat {}: {}", chat_id, err)
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="Internal server error") from err
    if not chat:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=f"Chat with ID '{chat_id}' not found")
    return chat


@router.post("/api/chats", response_model=Chat, status_code=status.HTTP_201_CREATED, response_model_exclude_none=True)
async def create_chat(request: CreateChatRequest) -> Chat:
    """Create a new chat."""
    logger.debug(f"Creating chat: {request}")
    try:
        return save_chat(request.chat_id, request.user_id, request.title, request.visibility)
    except ValidationError as err:
        logger.error("Validation error creating chat: {}", err)
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail="Invalid chat data") from err
    except Exception as err:
        logger.error("Failed to create chat: {}", err)
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="Internal server error") from err


@router.delete("/api/chats/{chat_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_chat(chat_id: str) -> None:
    """Delete a chat and all its related items."""
    try:
        delete_chat_by_id(chat_id)
    except Exception as err:
        logger.error("Failed to delete chat {}: {}", chat_id, err)
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="Internal server error") from err


@router.patch("/api/chats/{chat_id}/visibility", status_code=status.HTTP_204_NO_CONTENT)
async def update_chat_visibility(chat_id: str, request: UpdateChatVisibilityRequest) -> None:
    """Update chat visibility."""
    try:
        update_chat_visibility_by_id(chat_id, request.visibility)
    except Exception as err:
        logger.error("Failed to update chat visibility {}: {}", chat_id, err)
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="Internal server error") from err


@router.get("/api/chats/{chat_id}/messages", response_model=list[Message], response_model_exclude_none=True)
async def get_chat_messages(chat_id: str) -> list[Message]:
    """Get all messages for a chat."""
    try:
        return get_messages_by_chat_id(chat_id)
    except Exception as err:
        logger.error("Failed to get messages for chat {}: {}", chat_id, err)
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="Internal server error") from err


@router.get("/api/messages/{message_id}", response_model=Message, response_model_exclude_none=True)
async def get_message(message_id: str) -> Message:
    """Get a specific message by ID."""
    try:
        message = get_message_by_id(message_id)
    except Exception as err:
        logger.error("Failed to get message {}: {}", message_id, err)
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="Internal server error") from err
    if not message:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=f"Message with ID '{message_id}' not found")
    return message


@router.post("/api/chats/{chat_id}/messages", status_code=status.HTTP_201_CREATED)
async def save_chat_messages(chat_id: str, request: SaveMessagesRequest) -> None:
    """Save messages to a chat."""
    try:
        save_messages(request.user_id, request.messages)
    except ValidationError as err:
        logger.error("Validation error saving messages: {}s", err)
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail="Invalid message data") from err
    except Exception as err:
        logger.error("Failed to save messages to chat {}: {}", chat_id, err)
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="Internal server error") from err


@router.delete("/api/chats/{chat_id}/messages", status_code=status.HTTP_204_NO_CONTENT)
async def delete_chat_messages_after_timestamp(
    chat_id: str, timestamp: str = Query(description="ISO timestamp to delete messages after")
) -> None:
    """Delete messages after a given timestamp."""
    try:
        # Validate timestamp format but keep as string
        from datetime import datetime

        datetime.fromisoformat(timestamp)  # Just for validation
        delete_messages_by_chat_id_after_timestamp(chat_id, timestamp)
    except ValueError as err:
        logger.error("Invalid timestamp format: {}", err)
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail="Invalid timestamp format. Use ISO format."
        ) from err
    except Exception as err:
        logger.error("Failed to delete messages for chat {}: {}", chat_id, err)
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="Internal server error") from err


@router.post("/api/chats/{chat_id}/messages/{message_id}/vote", status_code=status.HTTP_201_CREATED)
async def vote_on_message(chat_id: str, message_id: str, request: VoteMessageRequest) -> None:
    """Vote on a message."""
    try:
        vote_message(chat_id, message_id, request.vote_type)
    except ValidationError as err:
        logger.error("Validation error voting on message: {}", err)
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail="Invalid vote data") from err
    except Exception as err:
        logger.error("Failed to vote on message {}: {}", message_id, err)
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="Internal server error") from err


@router.get("/api/chats/{chat_id}/votes", response_model=list[Vote], response_model_exclude_none=True)
async def get_chat_votes(chat_id: str) -> list[Vote]:
    """Get all votes for a chat."""
    try:
        return get_votes_by_chat_id(chat_id)
    except Exception as err:
        logger.error("Failed to get votes for chat {}: {}", chat_id, err)
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="Internal server error") from err


@router.post(
    "/api/chats/{chat_id}/streams",
    response_model=Stream,
    status_code=status.HTTP_201_CREATED,
    response_model_exclude_none=True,
)
async def create_stream(chat_id: str, request: CreateStreamRequest) -> Stream:
    """Create a stream ID for a chat."""
    try:
        return create_stream_id(request.stream_id, chat_id)
    except ValidationError as err:
        logger.error("Validation error creating stream: {}", err)
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail="Invalid stream data") from err
    except Exception as err:
        logger.error("Failed to create stream for chat {}: {}", chat_id, err)
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="Internal server error") from err


@router.get("/api/chats/{chat_id}/streams", response_model=StreamIdsResponse, response_model_exclude_none=True)
async def get_chat_streams(chat_id: str) -> StreamIdsResponse:
    """Get all stream IDs for a chat."""
    try:
        stream_ids = get_stream_ids_by_chat_id(chat_id)
        return StreamIdsResponse(stream_ids=stream_ids)
    except Exception as err:
        logger.error("Failed to get streams for chat {}: {}", chat_id, err)
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="Internal server error") from err
