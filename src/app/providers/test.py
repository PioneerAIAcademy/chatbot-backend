"""
Test provider for predictable responses.

This provider handles specific test prompts with predetermined responses,
useful for frontend testing and development.
"""

import re
from collections.abc import Generator
from typing import Any

from app.custom_logger import get_logger
from app.models.chat import ChatRequest

STREAM_CHUNK_DELAY = 0.2

# Configure logging
logger = get_logger()

# Pattern for matching test prompts
TEST_PROMPT_PATTERN = re.compile(r"^Test prompt (\d+)$")


def is_test_prompt(message: str) -> bool:
    """Check if a message matches the test prompt pattern."""
    return TEST_PROMPT_PATTERN.match(message) is not None


def get_test_prompt_number(message: str) -> str | None:
    """Extract the number from a test prompt message."""
    match = TEST_PROMPT_PATTERN.match(message)
    return match.group(1) if match else None


class TestProvider:
    """Test provider for predictable responses."""

    def format_messages_from_request(self, request: ChatRequest) -> list[dict[str, str]]:
        """
        Format messages from chat request into provider format.

        This method exists for compatibility but is not used by the test provider.
        """
        messages = []
        for message in request.messages:
            role = message.role
            content = " ".join(part.text for part in message.parts if part.type == "text")
            messages.append({"role": role, "content": content})
        return messages

    def get_response(self, system_message: str, user_message: str) -> str:  # noqa ARG002
        """
        Get a non-streaming response for test prompts.

        Used for title generation.
        """
        prompt_number = get_test_prompt_number(user_message)
        if prompt_number:
            title = f"Test title {prompt_number}"
            logger.info(f"Test provider returning title: {title} for prompt: {user_message}")
            return title

        # This shouldn't happen if the provider is used correctly
        logger.error(f"Test provider called with non-test prompt: {user_message}")
        return "Test Provider Error"

    def stream_chat_response(
        self,
        messages: list[dict[str, str]],
        system_message: str | None = None,  # noqa ARG002
    ) -> Generator[str | dict[str, Any], None, None]:
        """
        Stream a chat response with 100ms delays between tokens.
        """
        # Get the last user message
        last_user_message = None
        for msg in reversed(messages):
            if msg["role"] == "user":
                last_user_message = msg["content"]
                break

        if last_user_message:
            prompt_number = get_test_prompt_number(last_user_message)
            if prompt_number:
                tokens = ["Test ", "response ", str(prompt_number)]
                logger.info(f"Test provider streaming response for prompt: {last_user_message}")

                # Stream tokens with delay
                for token in tokens:
                    yield token
                    # Sleep for 100ms (this works because FastAPI handles sync generators)
                    import time

                    time.sleep(STREAM_CHUNK_DELAY)

                # Yield usage data
                yield {"usage": {"promptTokens": 3, "completionTokens": 3}}
            else:
                # This shouldn't happen if the provider is used correctly
                logger.error(f"Test provider called with non-test prompt: {last_user_message}")
                yield "Test Provider Error"
        else:
            logger.error("Test provider called without user message")
            yield "Test Provider Error"


# Create a singleton instance
test_provider = TestProvider()
