"""Pytest fixtures for Listonic tests."""

from __future__ import annotations

import os
from unittest.mock import AsyncMock

import pytest
from dotenv import load_dotenv

# Load environment variables from .env file
load_dotenv()


@pytest.fixture
def email() -> str:
    """Get test email from environment."""
    return os.getenv("LISTONIC_EMAIL", "test@example.com")


@pytest.fixture
def password() -> str:
    """Get test password from environment."""
    return os.getenv("LISTONIC_PASSWORD", "testpassword")


@pytest.fixture
def mock_api_response_login() -> dict:
    """Mock login response."""
    return {
        "access_token": "mock_token_12345",
        "token_type": "Bearer",
        "expires_in": 86399,
        "refresh_token": "mock_refresh_token",
    }


@pytest.fixture
def mock_api_response_lists() -> list[dict]:
    """Mock lists response."""
    return [
        {
            "id": 123456,
            "name": "Groceries",
            "isArchived": False,
            "items": [
                {
                    "id": 1001,
                    "name": "Milk",
                    "isChecked": False,
                    "quantity": "2",
                    "unit": "L",
                },
                {
                    "id": 1002,
                    "name": "Bread",
                    "isChecked": True,
                    "quantity": "1",
                    "unit": None,
                },
            ],
        },
        {
            "id": 789012,
            "name": "Hardware Store",
            "isArchived": False,
            "items": [
                {
                    "id": 2001,
                    "name": "Screws",
                    "isChecked": False,
                    "quantity": "10",
                    "unit": "pcs",
                },
            ],
        },
    ]


@pytest.fixture
def mock_api_response_item() -> dict:
    """Mock item response."""
    return {
        "id": 3001,
        "name": "Eggs",
        "isChecked": False,
        "quantity": "12",
        "unit": "pcs",
    }


@pytest.fixture
def mock_session():
    """Create a mock aiohttp session."""
    session = AsyncMock()
    return session
