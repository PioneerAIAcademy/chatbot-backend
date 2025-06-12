"""
Tests for message operations.

This module tests message CRUD operations, deletion by timestamp,
and related error scenarios.
"""

import os
import time
import uuid
from datetime import UTC, datetime

import pytest
from fastapi.testclient import TestClient

from app.main import app


@pytest.fixture
def test_client():
    """Test client fixture."""
    return TestClient(app)


@pytest.fixture
def auth_headers():
    """Get the auth headers."""
    api_secret = os.environ.get("API_SECRET", "secret_key")
    return {"Authorization": f"Bearer {api_secret}"}


def test_create_message_and_verify_in_chat_and_count(test_client, auth_headers):
    """Test creating a message and verifying it appears in chat messages and user message count."""
    # First, create a user
    email = f"test-{uuid.uuid4()}@example.com"
    password_hash = "test-password-hash"

    user_response = test_client.post(
        "/api/users", json={"email": email, "passwordHash": password_hash}, headers=auth_headers
    )
    assert user_response.status_code == 201
    user = user_response.json()
    user_id = user["id"]

    # Create a chat for this user
    chat_id = str(uuid.uuid4())
    chat_title = "Test Chat for Messages"

    chat_response = test_client.post(
        "/api/chats",
        json={"id": chat_id, "userId": user_id, "title": chat_title, "visibility": "private"},
        headers=auth_headers,
    )
    assert chat_response.status_code == 201

    # Check initial message count (should be 0)
    initial_count_response = test_client.get(f"/api/users/{user_id}/message-count", headers=auth_headers)
    assert initial_count_response.status_code == 200
    initial_count = initial_count_response.json()["count"]

    # Create messages to save to the chat
    message_id = str(uuid.uuid4())
    created_at = datetime.now(UTC).isoformat()

    messages_data = [
        {
            "chatId": chat_id,
            "createdAt": created_at,
            "role": "user",
            "parts": [{"type": "text", "text": "Hello, this is a test message"}],
            "attachments": [],
            "id": message_id,
        }
    ]

    # Save messages via POST /api/chats/{chat_id}/messages
    save_messages_response = test_client.post(
        f"/api/chats/{chat_id}/messages",
        json={"userId": user_id, "messages": messages_data},
        headers=auth_headers,
    )
    assert save_messages_response.status_code == 201

    # Retrieve the specific message via GET /api/messages/{message_id}
    message_response = test_client.get(f"/api/messages/{message_id}", headers=auth_headers)
    assert message_response.status_code == 200
    retrieved_message = message_response.json()
    assert retrieved_message["id"] == message_id
    assert retrieved_message["chatId"] == chat_id
    assert retrieved_message["role"] == "user"
    assert retrieved_message["parts"] == [{"type": "text", "text": "Hello, this is a test message"}]
    assert retrieved_message["attachments"] == []

    # Verify message appears in chat messages via GET /api/chats/{chat_id}/messages
    chat_messages_response = test_client.get(f"/api/chats/{chat_id}/messages", headers=auth_headers)
    assert chat_messages_response.status_code == 200
    chat_messages = chat_messages_response.json()
    assert len(chat_messages) == 1
    assert chat_messages[0]["id"] == message_id
    assert chat_messages[0]["role"] == "user"
    assert chat_messages[0]["parts"] == [{"type": "text", "text": "Hello, this is a test message"}]

    # Verify user message count increased via GET /api/users/{user_id}/message-count
    final_count_response = test_client.get(f"/api/users/{user_id}/message-count", headers=auth_headers)
    assert final_count_response.status_code == 200
    final_count = final_count_response.json()["count"]
    assert final_count == initial_count + 1


def test_delete_messages_after_timestamp(test_client, auth_headers):
    """Test creating messages at different times and deleting messages after a specific timestamp."""
    # First, create a user
    email = f"test-{uuid.uuid4()}@example.com"
    password_hash = "test-password-hash"

    user_response = test_client.post(
        "/api/users", json={"email": email, "passwordHash": password_hash}, headers=auth_headers
    )
    assert user_response.status_code == 201
    user = user_response.json()
    user_id = user["id"]

    # Create a chat for this user
    chat_id = str(uuid.uuid4())
    chat_title = "Test Chat for Message Deletion"

    chat_response = test_client.post(
        "/api/chats",
        json={"id": chat_id, "userId": user_id, "title": chat_title, "visibility": "private"},
        headers=auth_headers,
    )
    assert chat_response.status_code == 201

    # Create messages at different times
    early_message_id = str(uuid.uuid4())
    middle_message_id = str(uuid.uuid4())
    late_message_id = str(uuid.uuid4())

    messages_data = [
        {
            "chatId": chat_id,
            "role": "user",
            "parts": [{"type": "text", "text": "Early message"}],
            "attachments": [],
            "id": early_message_id,
        },
        {
            "chatId": chat_id,
            "role": "assistant",
            "parts": [{"type": "text", "text": "Middle message"}],
            "attachments": [],
            "id": middle_message_id,
        },
        {
            "chatId": chat_id,
            "role": "user",
            "parts": [{"type": "text", "text": "Late message"}],
            "attachments": [],
            "id": late_message_id,
        },
    ]

    # Save all messages
    for message in messages_data:
        save_messages_response = test_client.post(
            f"/api/chats/{chat_id}/messages",
            json={"userId": user_id, "messages": [message]},
            headers=auth_headers,
        )
        assert save_messages_response.status_code == 201
        time.sleep(0.1)

    # Verify all 3 messages exist
    initial_messages_response = test_client.get(f"/api/chats/{chat_id}/messages", headers=auth_headers)
    assert initial_messages_response.status_code == 200
    initial_messages = initial_messages_response.json()
    assert len(initial_messages) == 3

    # Delete messages after the middle timestamp
    # This should delete the middle and late messages, keeping only the early one
    cutoff_timestamp = initial_messages[1]["createdAt"]

    delete_response = test_client.delete(
        f"/api/chats/{chat_id}/messages",
        params={"timestamp": cutoff_timestamp},
        headers=auth_headers,
    )
    assert delete_response.status_code == 204

    # Verify only the early message remains
    final_messages_response = test_client.get(f"/api/chats/{chat_id}/messages", headers=auth_headers)
    assert final_messages_response.status_code == 200
    final_messages = final_messages_response.json()
    assert len(final_messages) == 1

    # Verify the remaining message is the early one
    remaining_message = final_messages[0]
    assert remaining_message["id"] == early_message_id
    assert remaining_message["parts"] == [{"type": "text", "text": "Early message"}]


# Error handling tests for message operations


def test_invalid_data_save_messages(test_client, auth_headers):
    """Test saving messages with invalid data."""
    chat_id = str(uuid.uuid4())

    # Invalid message format
    response = test_client.post(
        f"/api/chats/{chat_id}/messages",
        json={
            "id": "valid-user-id",
            "messages": [
                {
                    "role": "invalid_role",  # Should be user or assistant
                    "parts": [{"type": "text", "text": "Test message"}],
                    "attachments": [],
                }
            ],
        },
        headers=auth_headers,
    )
    assert response.status_code == 422

    # Missing required fields
    response = test_client.post(
        f"/api/chats/{chat_id}/messages",
        json={
            "id": "valid-user-id",
            "messages": [
                {
                    "role": "user",
                    # Missing parts field
                    "attachments": [],
                }
            ],
        },
        headers=auth_headers,
    )
    assert response.status_code == 422


def test_invalid_timestamp_format(test_client, auth_headers):
    """Test invalid timestamp format for message deletion."""
    chat_id = str(uuid.uuid4())

    # Invalid timestamp format
    response = test_client.delete(
        f"/api/chats/{chat_id}/messages?timestamp=invalid-timestamp",
        headers=auth_headers,
    )
    assert response.status_code == 422

    # Missing timestamp
    response = test_client.delete(
        f"/api/chats/{chat_id}/messages",
        headers=auth_headers,
    )
    assert response.status_code == 422


def test_missing_message_404(test_client, auth_headers):
    """Test 404 responses for missing message resources."""
    non_existent_message_id = str(uuid.uuid4())

    # Get non-existent message
    response = test_client.get(f"/api/messages/{non_existent_message_id}", headers=auth_headers)
    assert response.status_code == 404
    assert "not found" in response.json()["detail"].lower()


def test_message_operations_with_nonexistent_chat(test_client, auth_headers):
    """Test message operations with non-existent chat."""
    non_existent_chat_id = str(uuid.uuid4())

    # Get messages for non-existent chat
    response = test_client.get(f"/api/chats/{non_existent_chat_id}/messages", headers=auth_headers)
    assert response.status_code == 200  # Returns empty list, not 404
    assert response.json() == []
