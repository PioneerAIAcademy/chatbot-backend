"""
User management routes for the chatbot backend.

This module provides API endpoints for user operations including creation,
retrieval, and OAuth user management.
"""

from fastapi import APIRouter, HTTPException, Query, status
from pydantic import ValidationError

from app.custom_logger import get_logger
from app.db.chat import get_chats_by_user_id, get_message_count_by_user_id
from app.db.user import create_guest_user, create_user, get_or_create_user_from_oauth, get_user
from app.models.chat import ChatListResponse, MessageCountResponse
from app.models.user import (
    CreateEmailUserRequest,
    CreateOAuthUserRequest,
    User,
)

# Configure logging
logger = get_logger()

# Create a router for user endpoints
router = APIRouter(prefix="/api")


@router.get("/users/{email}", response_model=User, response_model_exclude_none=True)
async def get_user_by_email(email: str) -> User:
    """Get user by email address."""
    try:
        user = get_user(email)
    except Exception as err:
        logger.error("Failed to get user by email {}: {}", email, err)
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="Internal server error") from err

    if not user:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=f"User with email '{email}' not found")

    return user


@router.post("/users", response_model=User, status_code=status.HTTP_201_CREATED, response_model_exclude_none=True)
async def create_email_user_endpoint(request: CreateEmailUserRequest) -> User:
    """Create a new email user."""
    try:
        # Check if user already exists
        existing_user = get_user(request.email)
        if existing_user:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT, detail=f"User with email '{request.email}' already exists"
            )

        user = create_user(request.email, request.password_hash)
        return user
    except HTTPException:
        raise  # Re-raise HTTPException as-is
    except ValidationError as err:
        logger.error("Validation error creating user: {}", err)
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail="Invalid user data") from err
    except Exception as err:
        logger.error("Failed to create user {}: {}", request.email, err)
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="Internal server error") from err


@router.post("/users/guest", response_model=User, status_code=status.HTTP_201_CREATED, response_model_exclude_none=True)
async def create_guest_user_endpoint() -> User:
    """Create a new guest user."""
    try:
        user = create_guest_user()
        return user
    except Exception as err:
        logger.error("Failed to create guest user: {}", err)
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="Internal server error") from err


@router.post("/users/oauth", response_model=User, status_code=status.HTTP_201_CREATED, response_model_exclude_none=True)
async def create_oauth_user(request: CreateOAuthUserRequest) -> User:
    """Create or get a user via OAuth."""
    try:
        user = get_or_create_user_from_oauth(request.email, request.provider, request.provider_account_id)
        return user
    except ValidationError as err:
        logger.error("Validation error creating OAuth user: {}", err)
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail="Invalid OAuth user data") from err
    except Exception as err:
        logger.error("Failed to create OAuth user: {}", err)
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="Internal server error") from err


@router.get("/users/{user_id}/chats", response_model=ChatListResponse)
async def get_user_chats(
    user_id: str,
    limit: int = Query(default=20, ge=1, le=100),
    starting_after: str | None = Query(default=None),
    ending_before: str | None = Query(default=None),
) -> ChatListResponse:
    """Get chats for a user with pagination."""
    try:
        return get_chats_by_user_id(user_id, limit, starting_after, ending_before)
    except Exception as err:
        logger.error("Failed to get chats for user {}: {}", user_id, err)
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="Internal server error") from err


@router.get("/users/{user_id}/message-count", response_model=MessageCountResponse)
async def get_user_message_count(
    user_id: str, hours: int = Query(default=24, ge=1, description="Number of hours to look back")
) -> MessageCountResponse:
    """Get message count for a user in the last N hours."""
    try:
        count = get_message_count_by_user_id(user_id, hours)
        return MessageCountResponse(count=count)
    except Exception as err:
        logger.error("Failed to get message count for user {}: {}", user_id, err)
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="Internal server error") from err
