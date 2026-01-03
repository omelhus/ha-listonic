"""Tests for the Listonic API client."""

from __future__ import annotations

import re

import pytest
from aioresponses import aioresponses

from custom_components.listonic.api import (
    ListonicApiClient,
    ListonicAuthError,
    ListonicItem,
    ListonicList,
)

# Regex patterns for URL matching
LOGIN_URL_PATTERN = re.compile(r"^https://api\.listonic\.com/api/loginextended.*$")
LISTS_URL_PATTERN = re.compile(r"^https://api\.listonic\.com/api/lists(\?.*)?$")
LIST_ITEMS_PATTERN = re.compile(r"^https://api\.listonic\.com/api/lists/\d+/items.*$")
ITEM_PATTERN = re.compile(r"^https://api\.listonic\.com/api/lists/\d+/items/\d+$")


class TestListonicItem:
    """Tests for ListonicItem dataclass."""

    def test_from_api_minimal(self):
        """Test creating item from minimal API response."""
        data = {"id": 123, "name": "Test Item", "isChecked": False}
        item = ListonicItem.from_api(data)

        assert item.id == 123
        assert item.name == "Test Item"
        assert item.is_checked is False
        assert item.quantity is None
        assert item.unit is None

    def test_from_api_full(self):
        """Test creating item from full API response."""
        data = {
            "id": 456,
            "name": "Milk",
            "isChecked": True,
            "quantity": "2",
            "unit": "L",
            "price": 3.99,
            "description": "Whole milk",
            "categoryId": 10,
        }
        item = ListonicItem.from_api(data)

        assert item.id == 456
        assert item.name == "Milk"
        assert item.is_checked is True
        assert item.quantity == "2"
        assert item.unit == "L"
        assert item.price == 3.99
        assert item.description == "Whole milk"
        assert item.category_id == 10


class TestListonicList:
    """Tests for ListonicList dataclass."""

    def test_from_api(self, mock_api_response_lists):
        """Test creating list from API response."""
        data = mock_api_response_lists[0]
        lst = ListonicList.from_api(data)

        assert lst.id == 123456
        assert lst.name == "Groceries"
        assert lst.is_archived is False
        assert len(lst.items) == 2

    def test_unchecked_count(self, mock_api_response_lists):
        """Test unchecked item count."""
        data = mock_api_response_lists[0]
        lst = ListonicList.from_api(data)

        assert lst.unchecked_count == 1  # Milk is unchecked

    def test_checked_count(self, mock_api_response_lists):
        """Test checked item count."""
        data = mock_api_response_lists[0]
        lst = ListonicList.from_api(data)

        assert lst.checked_count == 1  # Bread is checked


class TestListonicApiClient:
    """Tests for ListonicApiClient."""

    @pytest.mark.asyncio
    async def test_authenticate_success(
        self, email, password, mock_api_response_login
    ):
        """Test successful authentication."""
        with aioresponses() as m:
            m.post(
                LOGIN_URL_PATTERN,
                payload=mock_api_response_login,
            )

            client = ListonicApiClient(email, password)
            result = await client.authenticate()

            assert result is True
            assert client._token == "mock_token_12345"

            await client.close()

    @pytest.mark.asyncio
    async def test_authenticate_invalid_credentials(self, email, password):
        """Test authentication with invalid credentials."""
        with aioresponses() as m:
            m.post(
                LOGIN_URL_PATTERN,
                status=401,
            )

            client = ListonicApiClient(email, password)

            with pytest.raises(ListonicAuthError):
                await client.authenticate()

            await client.close()

    @pytest.mark.asyncio
    async def test_get_lists(
        self, email, password, mock_api_response_login, mock_api_response_lists
    ):
        """Test getting all lists."""
        with aioresponses() as m:
            m.post(
                LOGIN_URL_PATTERN,
                payload=mock_api_response_login,
            )
            m.get(
                LISTS_URL_PATTERN,
                payload=mock_api_response_lists,
            )

            client = ListonicApiClient(email, password)
            lists = await client.get_lists()

            assert len(lists) == 2
            assert lists[0].name == "Groceries"
            assert lists[1].name == "Hardware Store"

            await client.close()

    @pytest.mark.asyncio
    async def test_add_item(
        self, email, password, mock_api_response_login, mock_api_response_item
    ):
        """Test adding an item to a list."""
        with aioresponses() as m:
            m.post(
                LOGIN_URL_PATTERN,
                payload=mock_api_response_login,
            )
            m.post(
                LIST_ITEMS_PATTERN,
                payload=mock_api_response_item,
                status=201,
            )

            client = ListonicApiClient(email, password)
            item = await client.add_item(123456, "Eggs", "12", "pcs")

            assert item.id == 3001
            assert item.name == "Eggs"

            await client.close()

    @pytest.mark.asyncio
    async def test_check_item(
        self, email, password, mock_api_response_login
    ):
        """Test checking an item."""
        # API returns empty body on PATCH success
        # After PATCH, we fetch the items to get updated state
        checked_items = [
            {
                "Id": "1001",
                "IdAsNumber": 1001,
                "Name": "Milk",
                "Checked": 1,
                "Amount": "2",
                "Unit": "L",
            }
        ]

        with aioresponses() as m:
            m.post(
                LOGIN_URL_PATTERN,
                payload=mock_api_response_login,
            )
            m.patch(
                ITEM_PATTERN,
                payload="",  # Empty response
            )
            m.get(
                LIST_ITEMS_PATTERN,
                payload=checked_items,
            )

            client = ListonicApiClient(email, password)
            item = await client.check_item(123456, 1001)

            assert item.is_checked is True

            await client.close()

    @pytest.mark.asyncio
    async def test_delete_item(
        self, email, password, mock_api_response_login
    ):
        """Test deleting an item."""
        with aioresponses() as m:
            m.post(
                LOGIN_URL_PATTERN,
                payload=mock_api_response_login,
            )
            m.delete(
                ITEM_PATTERN,
                status=200,
            )

            client = ListonicApiClient(email, password)
            result = await client.delete_item(123456, 1001)

            assert result is True

            await client.close()

    @pytest.mark.asyncio
    async def test_create_list(
        self, email, password, mock_api_response_login
    ):
        """Test creating a new list."""
        new_list = {
            "id": 999999,
            "name": "New List",
            "isArchived": False,
            "items": [],
        }

        with aioresponses() as m:
            m.post(
                LOGIN_URL_PATTERN,
                payload=mock_api_response_login,
            )
            m.post(
                LISTS_URL_PATTERN,
                payload=new_list,
                status=201,
            )

            client = ListonicApiClient(email, password)
            lst = await client.create_list("New List")

            assert lst.id == 999999
            assert lst.name == "New List"

            await client.close()

    @pytest.mark.asyncio
    async def test_token_refresh_on_401(
        self, email, password, mock_api_response_login, mock_api_response_lists
    ):
        """Test that token is refreshed on 401 response."""
        with aioresponses() as m:
            # First login
            m.post(
                LOGIN_URL_PATTERN,
                payload=mock_api_response_login,
            )
            # First get_lists returns 401
            m.get(
                LISTS_URL_PATTERN,
                status=401,
            )
            # Re-authentication
            m.post(
                LOGIN_URL_PATTERN,
                payload=mock_api_response_login,
            )
            # Second get_lists succeeds
            m.get(
                LISTS_URL_PATTERN,
                payload=mock_api_response_lists,
            )

            client = ListonicApiClient(email, password)
            lists = await client.get_lists()

            assert len(lists) == 2

            await client.close()
