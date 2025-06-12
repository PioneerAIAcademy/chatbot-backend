"""
User database operations.
"""

import uuid
from datetime import UTC, datetime

from boto3.dynamodb.conditions import Key
from botocore.exceptions import ClientError

from app.custom_logger import get_logger
from app.db.db import users_table
from app.models.user import User

# Configure logging
logger = get_logger()

# Users
# - PK=user_id
#   - created_at = ISO-8601 string
#   - stripe_customer_id = nullable string
#   - active_subscription_id = nullable string
#   - subscription_status = nullable active | canceled
#   - plan_id = nullable string
#   - current_period_start = nullable ISO-8601 string
#   - current_period_end = nullable ISO-8601 string
#   - cancel_at_period_end = bool
# GSI1-Email: email -> user_id, password_hash, created_at
# GSI2-UsersByType: Type + CreatedAt -> user_id
# GSI3-StripeCustomer: stripe_customer_id -> user_id, active_subscription_id, subscription_status
# GSI4-Subscription: active_subscription_id -> user_id, stripe_customer_id, subscription_status


def get_user(email: str) -> User | None:
    """Fetch user by email."""
    resp = users_table.query(IndexName="GSI1-Email", KeyConditionExpression=Key("email").eq(email))
    items = resp.get("Items", [])
    return User.model_validate(items[0]) if items else None


def create_user(email: str, password_hash: str) -> User:
    """Create a new email user."""
    user_id = str(uuid.uuid4())
    now = datetime.now(UTC).isoformat()
    item = {
        "user_id": user_id,
        "email": email,
        "source": "email",
        "password_hash": password_hash,
        "created_at": now,
        "cancel_at_period_end": False,
    }
    try:
        users_table.put_item(Item=item)
        return User.model_validate(item)
    except ClientError as err:
        logger.error("Failed to create user {}: {}", email, err)
        raise RuntimeError("Could not write new user to database") from err


def create_guest_user() -> User:
    """Create a new guest user."""
    user_id = str(uuid.uuid4())
    now = datetime.now(UTC)
    now_iso = now.isoformat()
    email = f"guest-{int(now.timestamp() * 1000)}@local.com"
    item = {
        "user_id": user_id,
        "email": email,
        "source": "guest",
        "created_at": now_iso,
        "cancel_at_period_end": False,
    }
    try:
        users_table.put_item(Item=item)
        return User.model_validate(item)
    except ClientError as err:
        logger.error("Failed to create user {}: {}", email, err)
        raise RuntimeError("Could not write new user to database") from err


def get_or_create_user_from_oauth(email: str | None, provider: str, provider_account_id: str) -> User:
    """Fetch or create a user via OAuth."""
    email = email or f"{provider}-{provider_account_id}@oauth.local"
    user = get_user(email)
    if user:
        return user
    # No existing user, create new
    user_id = str(uuid.uuid4())
    now = datetime.now(UTC).isoformat()
    item = {
        "user_id": user_id,
        "email": email,
        "source": "oauth",
        "provider": provider,
        "provider_account_id": provider_account_id,
        "created_at": now,
        "cancel_at_period_end": False,
    }
    try:
        users_table.put_item(Item=item, ConditionExpression="attribute_not_exists(email)")
        return User.model_validate(item)
    except users_table.meta.client.exceptions.ConditionalCheckFailedException:
        # race: someone else just created it
        user = get_user(email)
        if not user:
            raise RuntimeError("User creation race condition: user not found after creation") from None
        return user
    except ClientError as err:
        logger.error("Failed to create user {}: {}", email, err)
        raise RuntimeError("Could not write new user to database") from err
