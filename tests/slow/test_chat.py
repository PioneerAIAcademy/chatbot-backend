"""
Tests for chat operations.

This module tests chat CRUD operations, visibility updates, and related error scenarios.
"""

import json
import os
import uuid

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


@pytest.fixture
def chat_request_data():
    """Get chat request data."""
    return {
        "messages": [
            {"role": "user", "parts": [{"type": "text", "text": "Hello, how are you today?"}], "id": str(uuid.uuid4())}
        ],
        "userId": "test-user",
    }


@pytest.fixture
def chat_id():
    """Get a test chat ID."""
    return str(uuid.uuid4())


def test_chat_endpoint_no_auth(test_client, chat_request_data, chat_id):
    """Test chat endpoint without authentication."""
    response = test_client.post(f"/api/chats/{chat_id}/responses", json=chat_request_data)
    assert response.status_code == 401
    assert "message" in response.json()
    assert "Invalid or missing API key" in response.json()["message"]


def test_chat_endpoint_success(test_client, auth_headers, chat_request_data, chat_id):
    """Test chat endpoint with successful response (slow test - makes API call)."""
    response = test_client.post(f"/api/chats/{chat_id}/responses", headers=auth_headers, json=chat_request_data)

    assert response.status_code == 200
    assert "text/event-stream" in response.headers["content-type"]

    # Read the response content to verify format
    content = response.content.decode("utf-8")

    # Check the streaming format
    chunks = content.split("\n")

    # Check for the first chunk with message ID
    first_chunk = chunks[0]
    assert first_chunk.startswith('f:{"messageId":"')
    assert first_chunk.endswith('"}')

    # Verify messageId format (should be UUID)
    message_id_data = json.loads(first_chunk.replace("f:", ""))
    assert "messageId" in message_id_data
    assert len(message_id_data["messageId"]) == 36  # UUID length

    # Check that normal chunks are properly formatted
    # Start from index 1 to skip the first message ID chunk
    for chunk in chunks[1:-3]:  # Exclude the first chunk, last 2 chunks and the empty chunk after split
        assert chunk.startswith('0:"')

    # check the step finish chunk
    step_finish_chunk = chunks[-3]
    assert step_finish_chunk.startswith("e:")
    step_finish_data = json.loads(step_finish_chunk.replace("e:", ""))
    assert "finishReason" in step_finish_data
    assert "usage" in step_finish_data
    assert "isContinued" in step_finish_data

    # Check for the completion message with usage information
    finish_chunk = chunks[-2]
    assert "finishReason" in finish_chunk

    # Check for usage information in the completion message
    # The actual usage information may vary, but tokens should be meaningful
    assert "usage" in finish_chunk

    # Convert JSON string to dict to check token values
    finish_data = json.loads(finish_chunk.replace("d:", ""))

    # Check that token counts are present and have reasonable values
    assert "promptTokens" in finish_data["usage"]
    assert "completionTokens" in finish_data["usage"]

    # Ensure token counts are greater than 10
    prompt_tokens = finish_data["usage"]["promptTokens"]
    assert prompt_tokens > 10, f"Expected promptTokens > 10, got: {prompt_tokens}"
    completion_tokens = finish_data["usage"]["completionTokens"]
    assert completion_tokens > 10, f"Expected completionTokens > 10, got: {completion_tokens}"


def test_chat_endpoint_invalid_request(test_client, auth_headers, chat_id):
    """Test chat endpoint with invalid request."""
    # Missing required fields
    invalid_data = {"messages": []}

    response = test_client.post(f"/api/chats/{chat_id}/responses", headers=auth_headers, json=invalid_data)

    assert response.status_code == 422  # Validation error


def test_create_and_delete_chat(test_client, auth_headers):
    """Test creating a chat and then deleting it, verifying it's gone."""
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
    chat_title = "Test Chat to Delete"

    chat_response = test_client.post(
        "/api/chats",
        json={"id": chat_id, "userId": user_id, "title": chat_title, "visibility": "public"},
        headers=auth_headers,
    )
    assert chat_response.status_code == 201
    created_chat = chat_response.json()
    assert created_chat["id"] == chat_id

    # Verify chat exists via GET /api/chats/{chat_id}
    get_chat_response = test_client.get(f"/api/chats/{chat_id}", headers=auth_headers)
    assert get_chat_response.status_code == 200

    # Verify chat appears in user's chat list
    user_chats_response = test_client.get(f"/api/users/{user_id}/chats", headers=auth_headers)
    assert user_chats_response.status_code == 200
    user_chats = user_chats_response.json()
    assert len(user_chats["chats"]) == 1
    assert user_chats["chats"][0]["id"] == chat_id

    # Delete the chat via DELETE /api/chats/{chat_id}
    delete_response = test_client.delete(f"/api/chats/{chat_id}", headers=auth_headers)
    assert delete_response.status_code == 204

    # Verify chat no longer exists via GET /api/chats/{chat_id} - expect 404
    get_deleted_chat_response = test_client.get(f"/api/chats/{chat_id}", headers=auth_headers)
    assert get_deleted_chat_response.status_code == 404

    # Verify chat no longer appears in user's chat list
    final_user_chats_response = test_client.get(f"/api/users/{user_id}/chats", headers=auth_headers)
    assert final_user_chats_response.status_code == 200
    final_user_chats = final_user_chats_response.json()
    assert len(final_user_chats["chats"]) == 0


def test_update_chat_visibility(test_client, auth_headers):
    """Test creating a chat and updating its visibility."""
    # First, create a user
    email = f"test-{uuid.uuid4()}@example.com"
    password_hash = "test-password-hash"

    user_response = test_client.post(
        "/api/users", json={"email": email, "passwordHash": password_hash}, headers=auth_headers
    )
    assert user_response.status_code == 201
    user = user_response.json()
    user_id = user["id"]

    # Create a chat with initial visibility "private"
    chat_id = str(uuid.uuid4())
    chat_title = "Test Chat Visibility"

    chat_response = test_client.post(
        "/api/chats",
        json={"id": chat_id, "userId": user_id, "title": chat_title, "visibility": "private"},
        headers=auth_headers,
    )
    assert chat_response.status_code == 201
    created_chat = chat_response.json()
    assert created_chat["visibility"] == "private"

    # Update visibility to "public" via PATCH /api/chats/{chat_id}/visibility
    update_response = test_client.patch(
        f"/api/chats/{chat_id}/visibility",
        json={"visibility": "public"},
        headers=auth_headers,
    )
    assert update_response.status_code == 204

    # Verify visibility changed via GET /api/chats/{chat_id}
    get_chat_response = test_client.get(f"/api/chats/{chat_id}", headers=auth_headers)
    assert get_chat_response.status_code == 200
    updated_chat = get_chat_response.json()
    assert updated_chat["visibility"] == "public"
    assert updated_chat["id"] == chat_id
    assert updated_chat["title"] == chat_title


# Error handling tests for chat operations


def test_invalid_data_create_chat(test_client, auth_headers):
    """Test creating chat with invalid data."""
    # Missing required fields
    response = test_client.post(
        "/api/chats",
        json={},
        headers=auth_headers,
    )
    assert response.status_code == 422  # Unprocessable Entity

    # Invalid field types
    response = test_client.post(
        "/api/chats",
        json={
            "id": 123,  # Should be string
            "userId": "valid-user-id",
            "title": "Test Chat",
            "visibility": "public",
        },
        headers=auth_headers,
    )
    assert response.status_code == 422


def test_missing_chat_404(test_client, auth_headers):
    """Test 404 responses for missing chat resources."""
    non_existent_chat_id = str(uuid.uuid4())

    # Get non-existent chat
    response = test_client.get(f"/api/chats/{non_existent_chat_id}", headers=auth_headers)
    assert response.status_code == 404
    assert "not found" in response.json()["detail"].lower()


def test_chat_constraint_scenarios(test_client, auth_headers):
    """Test database constraint violations for chats."""
    # Create a valid chat first
    chat_id = str(uuid.uuid4())
    user_id = str(uuid.uuid4())

    create_chat_response = test_client.post(
        "/api/chats",
        json={"id": chat_id, "userId": user_id, "title": "Test Chat", "visibility": "public"},
        headers=auth_headers,
    )
    assert create_chat_response.status_code == 201

    # Test extremely long strings
    very_long_title = "x" * 10000
    response = test_client.post(
        "/api/chats",
        json={"id": str(uuid.uuid4()), "userId": user_id, "title": very_long_title, "visibility": "public"},
        headers=auth_headers,
    )
    assert response.status_code == 201

    # Test empty strings where they shouldn't be allowed
    response = test_client.post(
        "/api/chats",
        json={
            "id": "",  # Empty string
            "userId": user_id,
            "title": "Test Chat",
            "visibility": "public",
        },
        headers=auth_headers,
    )
    # Should fail validation
    assert response.status_code == 422

    # Test null/None values
    response = test_client.post(
        "/api/chats",
        json={"id": None, "userId": user_id, "title": "Test Chat", "visibility": "public"},
        headers=auth_headers,
    )
    assert response.status_code == 422
