"""
OpenAI provider implementation for the chatbot backend.

This module provides the OpenAI implementation of the LLM provider interface
and all OpenAI-specific configuration.
"""

import os
from collections.abc import Iterator
from functools import lru_cache
from typing import Any

from openai import OpenAI

from app.custom_logger import get_logger

# OpenAI-specific configuration
DEFAULT_MODEL = "gpt-4o-mini"

# Configure logging
logger = get_logger()


@lru_cache
def get_openai_api_key() -> str:
    """
    Get the OpenAI API key from environment variables.

    Returns:
        The OpenAI API key.
    """
    return os.environ.get("OPENAI_API_KEY", "")


class OpenAIProvider:
    """OpenAI implementation of the LLM provider interface."""

    def get_client(self) -> OpenAI:
        """
        Get an OpenAI client instance.

        Returns:
            An OpenAI client configured with the API key.
        """
        return OpenAI(
            api_key=get_openai_api_key(),
        )

    def format_messages_from_request(self, request: Any) -> list[dict[str, Any]]:
        """
        Format messages from the request for the OpenAI API.

        Args:
            request: The request object containing messages and other data.

        Returns:
            A list of formatted messages compatible with the OpenAI API.
        """
        formatted_messages = []

        # Add the messages from the request
        for message in request.messages:
            # Combine all text parts into a single content string
            content = "".join(part.text for part in message.parts if part.type == "text")
            formatted_messages.append({"role": message.role, "content": content})

        return formatted_messages

    def stream_chat_response(
        self,
        messages: list[dict],
        system_message: str | None = None,
        model: str | None = None,
        tool_definitions: list[dict[str, Any]] | None = None,
    ) -> Iterator[str | dict]:
        """
        Stream a chat response from OpenAI.

        Args:
            messages: The formatted messages.
            system_message: Optional system message to prepend.
            model: Optional model to use, defaults to DEFAULT_MODEL.
            tool_definitions: Optional tool definitions.

        Yields:
            Text chunks or usage information from the OpenAI response.
            Text chunks are returned as strings.
            Usage information is returned as a dictionary with the following format:
            {"usage": {"promptTokens": int, "completionTokens": int, "totalTokens": int}}
        """
        # Get a client instance
        client = self.get_client()

        if not tool_definitions:
            tool_definitions = []
        if model is None:
            model = DEFAULT_MODEL

        # Prepend system message if provided
        if system_message:
            # Check if there's already a system message at the beginning
            has_system_message = False
            if messages and messages[0].get("role") == "system":
                has_system_message = True

            # Only add system message if there isn't one already
            if not has_system_message:
                system_msg = {"role": "system", "content": system_message}
                messages = [system_msg, *messages]

        # Create a streaming response using the responses endpoint
        # Note: We use Any for types with the OpenAI API to keep code simple
        stream = client.responses.create(
            input=messages,  # type: ignore # For the responses API, we pass messages as 'input'
            model=model,
            stream=True,
            tools=tool_definitions if tool_definitions else None,  # type: ignore
            store=False,
        )

        # Process each chunk in the stream
        for event in stream:
            # Text delta events - yield the text content
            if hasattr(event, "type") and event.type == "response.output_text.delta":
                yield event.delta

            # Usage events - yield a dictionary with usage information
            # Response usage events - yield a dictionary with usage information
            elif hasattr(event, "response") and hasattr(event.response, "usage") and event.response.usage is not None:
                # Convert to camelCase for consistency with the frontend
                usage_info = {
                    "usage": {
                        "promptTokens": event.response.usage.input_tokens,
                        "completionTokens": event.response.usage.output_tokens,
                    }
                }
                yield usage_info

    def get_response(
        self,
        system_message: str,
        user_message: str,
        model: str | None = None,
    ) -> str:
        """
        Get a complete response from OpenAI for a single message.

        Args:
            system_message: The system message providing context.
            user_message: The user message to respond to.
            model: Optional model to use, defaults to DEFAULT_MODEL.

        Returns:
            The complete response text.
        """
        client = self.get_client()
        if model is None:
            model = DEFAULT_MODEL

        messages = [
            {"role": "system", "content": system_message},
            {"role": "user", "content": user_message},
        ]

        # Create a response using the responses endpoint
        response = client.responses.create(
            model=model,
            input=messages,  # type: ignore
            store=False,
        )

        # Extract and return the response content
        return response.output_text
