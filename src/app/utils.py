"""
Utility functions for the chatbot backend.
"""

import json
from collections.abc import AsyncGenerator

from fastapi import Request, status
from fastapi.responses import JSONResponse, StreamingResponse

from app.config import API_PREFIX, get_api_secret
from app.custom_logger import get_logger

# Configure logging
logger = get_logger()


async def verify_api_key(request: Request) -> bool:
    """
    Verify the API key in the Authorization header.

    Args:
        request: The FastAPI request object.

    Returns:
        True if the API key is valid, False otherwise.
    """
    auth_header = request.headers.get("Authorization")

    if not auth_header:
        return False

    # Check for Bearer format
    parts = auth_header.split()
    if len(parts) != 2 or parts[0].lower() != "bearer":
        return False

    token = parts[1]
    api_secret = get_api_secret()

    return token == api_secret


def is_api_route(path: str) -> bool:
    """
    Check if a path is an API route that requires authentication.

    Args:
        path: The request path.

    Returns:
        True if the path is an API route, False otherwise.
    """
    return path.startswith(API_PREFIX)


async def format_error_stream(message: str) -> AsyncGenerator[bytes, None]:
    """
    Format an error message as a streaming response.

    Args:
        message: The error message.

    Yields:
        Formatted error message bytes.
    """
    # Format according to the specification:
    # e:error\n
    # d:{"message":"error description"}\n\n
    yield b"e:error\n"
    yield f"d:{json.dumps({'message': message})}\n\n".encode()


async def stream_chat_chunks(chunks: AsyncGenerator[str | dict, None]) -> AsyncGenerator[bytes, None]:
    """
    Format chat chunks as a streaming response.

    Args:
        chunks: An async generator of text chunks or usage information.
               Text chunks are strings.
               Usage information is a dictionary with the format:
               {"usage": {"promptTokens": int, "completionTokens": int}}

    Yields:
        Formatted chat chunks with the format:
        - f:{"messageId":"<uuid>"}\n  for first chunk with message ID (already sent)
        - 0:[json-encoded-text]\n  for normal text chunks
        - 3:[json-encoded-error-message]\n  for error message chunks
        - e:{"finishReason":"stop","usage":{"promptTokens":X,"completionTokens":Y},"isContinued":false}\n
            for step finish chunk
        - d:{"finishReason":"stop","usage":{"promptTokens":X,"completionTokens":Y}}\n  for finish chunk
    """
    try:
        # Store usage information if found
        usage_info = None

        # Stream each chunk with the proper format
        async for chunk in chunks:
            # If the chunk is a dictionary, it contains usage information
            if isinstance(chunk, dict) and "usage" in chunk:
                # Store the usage information for the final chunk
                usage_info = chunk["usage"]
                continue

            # Handle error chunks with code 3
            elif isinstance(chunk, str) and chunk.startswith("Error:"):
                error_message = chunk.replace("Error:", "").strip()
                yield f"3:{json.dumps(error_message)}\n".encode()

            # Handle normal text chunks with code 0
            elif chunk:
                yield f"0:{json.dumps(chunk)}\n".encode()

        # Send the finish message when complete with the new format
        # Include usage information if available
        if usage_info:
            step_finish_data = {"finishReason": "stop", "usage": usage_info, "isContinued": False}
            yield f"e:{json.dumps(step_finish_data)}\n".encode()
            finish_data = {"finishReason": "stop", "usage": usage_info}
            yield f"d:{json.dumps(finish_data)}\n".encode()
        else:
            # Fallback if no usage information was provided
            yield b'e:{"finishReason":"stop","isContinued":false}\n'
            yield b'd:{"finishReason":"stop"}\n'

    except Exception as e:
        # Handle any errors during streaming
        logger.error(f"Error streaming chat: {e}")
        error_message = f"Error streaming chat: {e}"
        yield f"3:{json.dumps(error_message)}\n".encode()


def create_streaming_response(chunks: AsyncGenerator[str | dict, None]) -> StreamingResponse:
    """
    Create a StreamingResponse with the correct headers.

    Args:
        chunks: An async generator of text chunks or usage information.
               Text chunks are strings.
               Usage information is a dictionary with usage data.

    Returns:
        A StreamingResponse object.
    """
    response = StreamingResponse(stream_chat_chunks(chunks), media_type="text/event-stream")

    # Add required headers
    response.headers["Cache-Control"] = "no-cache"
    response.headers["Connection"] = "keep-alive"
    response.headers["x-vercel-ai-data-stream"] = "v1"

    return response


def create_error_response(status_code: int, message: str) -> JSONResponse:
    """
    Create a standardized error response.

    Args:
        status_code: HTTP status code.
        message: Error message.

    Returns:
        A JSONResponse with the error details.
    """
    return JSONResponse(status_code=status_code, content={"message": message})


def handle_auth_error() -> JSONResponse:
    """
    Handle authentication error.

    Returns:
        A 401 Unauthorized response.
    """
    return create_error_response(status_code=status.HTTP_401_UNAUTHORIZED, message="Invalid or missing API key")
