"""
Shared database setup and configuration.
"""

import os

import boto3

from app.custom_logger import get_logger

# Configure logging
logger = get_logger()

# Initialize DynamoDB resource and tables
# Use local DynamoDB when DYNAMODB_URL is set
dynamodb_url = os.environ.get("DYNAMODB_URL")
if dynamodb_url:
    # For local DynamoDB, we need to specify a region (any region works)
    dynamodb = boto3.resource("dynamodb", endpoint_url=dynamodb_url, region_name="us-east-1")
else:
    # For AWS DynamoDB, use default region from environment
    dynamodb = boto3.resource("dynamodb")

# Get table names from environment variables with defaults
users_table = dynamodb.Table(os.environ.get("USERS_TABLE", "Users"))
chats_table = dynamodb.Table(os.environ.get("CHATS_TABLE", "Chats"))
