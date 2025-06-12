"""
Logging middleware for the chatbot backend.

This module provides middleware for logging request and response information.
"""

from collections.abc import Awaitable, Callable

from fastapi import Request, Response

from app.custom_logger import get_logger

# Configure logging
logger = get_logger()


async def log_requests(request: Request, call_next: Callable[[Request], Awaitable[Response]]) -> Response:
    """
    Log basic information about requests and responses.

    Args:
        request: The FastAPI request object.
        call_next: The next middleware or route handler in the chain.

    Returns:
        The response from the next middleware or route handler.
    """
    # Store the original body content
    body_bytes = await request.body()

    # Convert to string for logging (with truncation if needed)
    try:
        body_str = body_bytes.decode("utf-8") if body_bytes else ""
        body_log = body_str[:1000] + ("..." if len(body_str) > 1000 else "")
    except UnicodeDecodeError:
        # If we can't decode as UTF-8, just log that it's binary data
        body_log = f"<Binary data of length {len(body_bytes)}>"

    # Log request details including headers
    headers_dict = dict(request.headers)
    logger.info("request", path=request.url.path, method=request.method, body=body_log, headers=headers_dict)

    # Create a custom receive function that properly returns the expected message format
    original_receive = request.scope.get("receive", None)

    # Define a simpler receive function with less strict typing
    async def receive() -> dict:  # type: ignore
        if original_receive is None:
            return {"type": "http.request", "body": body_bytes, "more_body": False}

        message = await original_receive()  # type: ignore

        # If this is a body message and we have stored the body, replace it
        if message["type"] == "http.request" and "body" in message:
            message["body"] = body_bytes
            # Mark as not having more body data
            message["more_body"] = False

        return message

    # Replace the receive function in the scope
    request.scope["receive"] = receive

    # Process the request
    response = await call_next(request)

    return response
