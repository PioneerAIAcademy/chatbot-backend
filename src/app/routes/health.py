"""
Health check route for monitoring the service.

This module contains a simple endpoint for health checks and monitoring.
"""

from fastapi import APIRouter, Request, status
from pydantic import BaseModel

from app.custom_logger import get_logger

# Configure logging
logger = get_logger()


class HealthResponse(BaseModel):
    """Response model for health endpoint."""

    status: str


# Create a router for the health endpoint
router = APIRouter()


@router.get(
    "/health",
    response_model=HealthResponse,
    status_code=status.HTTP_200_OK,
)
async def health(request: Request) -> HealthResponse:
    """Health check endpoint that returns status of the service."""
    logger.info("Health check", path=request.url.path, method=request.method)
    return HealthResponse(status="healthy")
