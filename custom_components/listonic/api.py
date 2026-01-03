"""Listonic API client."""

from __future__ import annotations

import asyncio
import base64
import logging
import time
from dataclasses import dataclass
from typing import Any

import aiohttp

from .const import (
    API_BASE_URL,
    API_LISTS_ENDPOINT,
    API_LOGIN_ENDPOINT,
    CLIENT_ID,
    CLIENT_SECRET,
    REDIRECT_URI,
)

_LOGGER = logging.getLogger(__name__)

# Base64 encoded client credentials for clientauthorization header
_CLIENT_AUTH = base64.b64encode(f"{CLIENT_ID}:{CLIENT_SECRET}".encode()).decode()

# Maximum number of authentication retries for 401 responses
_MAX_AUTH_RETRIES = 1

# Request timeout configuration
_REQUEST_TIMEOUT = 30  # seconds

# Rate limiting configuration
_MAX_CONCURRENT_REQUESTS = 10  # Maximum concurrent requests
_MIN_REQUEST_INTERVAL = 0.1  # Minimum 100ms between requests
_MAX_BACKOFF_RETRIES = 3  # Maximum retries for rate limit/server errors
_INITIAL_BACKOFF_SECONDS = 1.0  # Initial backoff delay
_MAX_BACKOFF_SECONDS = 30.0  # Maximum backoff delay


class ListonicAuthError(Exception):
    """Exception for authentication errors."""


class ListonicApiError(Exception):
    """Exception for API errors."""


class ListonicRateLimitError(ListonicApiError):
    """Exception for rate limit errors after retries exhausted."""


@dataclass
class ListonicItem:
    """Represents a shopping list item."""

    id: int
    name: str
    is_checked: bool
    quantity: str | None = None
    unit: str | None = None
    price: float | None = None
    description: str | None = None
    category_id: int | None = None

    @classmethod
    def from_api(cls, data: dict[str, Any]) -> ListonicItem:
        """Create from API response.

        API uses PascalCase field names:
        - Id (string) or IdAsNumber (int)
        - Name, Checked (1/0), Amount, Unit, Price, Description, CategoryId
        """
        # Handle both string Id and numeric IdAsNumber
        item_id = data.get("IdAsNumber") or int(data.get("Id", data.get("id", 0)))
        # Checked is 1/0 in API, convert to bool
        checked = data.get("Checked", data.get("isChecked", 0))
        is_checked = bool(checked) if isinstance(checked, int) else checked

        return cls(
            id=item_id,
            name=data.get("Name", data.get("name", "")),
            is_checked=is_checked,
            quantity=data.get("Amount", data.get("quantity")),
            unit=data.get("Unit", data.get("unit")),
            price=data.get("Price", data.get("price")),
            description=data.get("Description", data.get("description")),
            category_id=data.get("CategoryId", data.get("categoryId")),
        )


@dataclass
class ListonicList:
    """Represents a shopping list."""

    id: int
    name: str
    items: list[ListonicItem]
    is_archived: bool = False

    @classmethod
    def from_api(cls, data: dict[str, Any]) -> ListonicList:
        """Create from API response.

        API uses PascalCase field names:
        - Id (string), Name, Items, Active (1/0), Deleted (1/0)
        """
        # Items array uses capital I
        items = [
            ListonicItem.from_api(item)
            for item in data.get("Items", data.get("items", []))
        ]
        # Id is a string in the API
        list_id = int(data.get("Id", data.get("id", 0)))
        # is_archived is based on Active=0 or Deleted=1
        is_archived = (
            data.get("Active", data.get("active", 1)) == 0
            or data.get("Deleted", data.get("deleted", 0)) == 1
        )
        return cls(
            id=list_id,
            name=data.get("Name", data.get("name", "")),
            items=items,
            is_archived=is_archived,
        )

    @property
    def unchecked_count(self) -> int:
        """Return count of unchecked items."""
        return sum(1 for item in self.items if not item.is_checked)

    @property
    def checked_count(self) -> int:
        """Return count of checked items."""
        return sum(1 for item in self.items if item.is_checked)


class ListonicApiClient:
    """Client for the Listonic API."""

    def __init__(
        self,
        email: str,
        password: str,
        session: aiohttp.ClientSession | None = None,
    ) -> None:
        """Initialize the API client."""
        self._email = email
        self._password = password
        self._session = session
        self._token: str | None = None
        self._refresh_token: str | None = None
        self._owns_session = session is None

        # Rate limiting state
        self._request_semaphore = asyncio.Semaphore(_MAX_CONCURRENT_REQUESTS)
        self._last_request_time: float = 0.0
        self._rate_limit_lock = asyncio.Lock()

    async def _get_session(self) -> aiohttp.ClientSession:
        """Get or create aiohttp session."""
        if self._session is None:
            self._session = aiohttp.ClientSession()
        return self._session

    async def close(self) -> None:
        """Close the session if we own it."""
        if self._owns_session and self._session is not None:
            await self._session.close()
            self._session = None

    def _get_headers(self) -> dict[str, str]:
        """Get headers for API requests."""
        headers = {
            "Content-Type": "application/json",
            "Accept": "application/json",
        }
        if self._token:
            headers["Authorization"] = f"Bearer {self._token}"
        return headers

    async def _wait_for_rate_limit(self) -> None:
        """Wait to ensure minimum interval between requests."""
        async with self._rate_limit_lock:
            now = time.monotonic()
            elapsed = now - self._last_request_time
            wait_time = _MIN_REQUEST_INTERVAL - elapsed
            if wait_time > 0:
                await asyncio.sleep(wait_time)
            self._last_request_time = time.monotonic()

    async def _request(
        self,
        method: str,
        url: str,
        *,
        headers: dict[str, str] | None = None,
        params: dict[str, str] | None = None,
        json: dict[str, Any] | None = None,
        data: dict[str, str] | None = None,
        skip_rate_limit: bool = False,
    ) -> aiohttp.ClientResponse:
        """Make a rate-limited request with exponential backoff.

        Args:
            method: HTTP method (GET, POST, PATCH, DELETE).
            url: Full URL to request.
            headers: Request headers.
            params: Query parameters.
            json: JSON body data.
            data: Form data.
            skip_rate_limit: If True, skip rate limiting (used for auth requests).

        Returns:
            The aiohttp response object. Caller is responsible for reading/closing.

        Raises:
            ListonicRateLimitError: If rate limit retries exhausted.
            ListonicApiError: On server errors after retries exhausted.
        """
        session = await self._get_session()
        timeout = aiohttp.ClientTimeout(total=_REQUEST_TIMEOUT)

        for attempt in range(_MAX_BACKOFF_RETRIES):
            # Apply rate limiting unless skipped
            if not skip_rate_limit:
                async with self._request_semaphore:
                    await self._wait_for_rate_limit()
                    response = await session.request(
                        method,
                        url,
                        headers=headers,
                        params=params,
                        json=json,
                        data=data,
                        timeout=timeout,
                    )
            else:
                response = await session.request(
                    method,
                    url,
                    headers=headers,
                    params=params,
                    json=json,
                    data=data,
                    timeout=timeout,
                )

            # Check for rate limiting (429)
            if response.status == 429:
                await response.release()
                backoff = min(
                    _INITIAL_BACKOFF_SECONDS * (2**attempt),
                    _MAX_BACKOFF_SECONDS,
                )
                retry_after = response.headers.get("Retry-After")
                if retry_after:
                    try:
                        backoff = max(backoff, float(retry_after))
                    except ValueError:
                        pass
                _LOGGER.warning(
                    "Rate limited (429), backing off %.1fs (attempt %d/%d)",
                    backoff,
                    attempt + 1,
                    _MAX_BACKOFF_RETRIES,
                )
                await asyncio.sleep(backoff)
                continue

            # Check for server errors (5xx)
            if 500 <= response.status < 600:
                await response.release()
                backoff = min(
                    _INITIAL_BACKOFF_SECONDS * (2**attempt),
                    _MAX_BACKOFF_SECONDS,
                )
                _LOGGER.warning(
                    "Server error (%d), backing off %.1fs (attempt %d/%d)",
                    response.status,
                    backoff,
                    attempt + 1,
                    _MAX_BACKOFF_RETRIES,
                )
                await asyncio.sleep(backoff)
                continue

            # Success or other status - return to caller
            return response

        # Retries exhausted
        raise ListonicRateLimitError(
            f"Request failed after {_MAX_BACKOFF_RETRIES} retries"
        )

    async def authenticate(self) -> bool:
        """Authenticate with the Listonic API."""
        url = f"{API_BASE_URL}{API_LOGIN_ENDPOINT}"
        params = {
            "provider": "password",
            "autoMerge": "1",
            "autoDestruct": "1",
        }
        # Form data for OAuth2-style authentication
        form_data = {
            "username": self._email,
            "password": self._password,
            "client_id": CLIENT_ID,
            "client_secret": CLIENT_SECRET,
            "redirect_uri": REDIRECT_URI,
        }
        headers = {
            "Content-Type": "application/x-www-form-urlencoded",
            "Accept": "application/json",
            "clientauthorization": f"Bearer {_CLIENT_AUTH}",
        }

        try:
            response = await self._request(
                "POST",
                url,
                params=params,
                data=form_data,
                headers=headers,
                skip_rate_limit=True,
            )
            async with response:
                if response.status == 401:
                    raise ListonicAuthError("Invalid credentials")
                if response.status == 400:
                    text = await response.text()
                    # 400 with auth-related message is an auth error
                    if "Unauthorized" in text or "Invalid" in text:
                        raise ListonicAuthError(f"Invalid credentials: {text}")
                    raise ListonicApiError(f"Bad request: {text}")
                if response.status != 200:
                    text = await response.text()
                    raise ListonicApiError(
                        f"Authentication failed: {response.status} - {text}"
                    )

                data = await response.json()
                self._token = data.get("access_token")
                self._refresh_token = data.get("refresh_token")

                if not self._token:
                    raise ListonicAuthError("No token in response")

                _LOGGER.debug("Successfully authenticated with Listonic")
                return True

        except aiohttp.ClientError as err:
            raise ListonicApiError(f"Connection error: {err}") from err

    async def _refresh_access_token(self) -> bool:
        """Refresh the access token using the refresh token.

        Returns True if refresh succeeded, False if full re-auth is needed.
        """
        if not self._refresh_token:
            _LOGGER.debug("No refresh token available, full auth required")
            return False

        url = f"{API_BASE_URL}{API_LOGIN_ENDPOINT}"

        # OAuth2 refresh token flow
        form_data = {
            "grant_type": "refresh_token",
            "refresh_token": self._refresh_token,
            "client_id": CLIENT_ID,
            "client_secret": CLIENT_SECRET,
        }
        headers = {
            "Content-Type": "application/x-www-form-urlencoded",
            "Accept": "application/json",
            "clientauthorization": f"Bearer {_CLIENT_AUTH}",
        }

        try:
            response = await self._request(
                "POST", url, data=form_data, headers=headers, skip_rate_limit=True
            )
            async with response:
                if response.status != 200:
                    _LOGGER.debug(
                        "Token refresh failed with status %s, full auth required",
                        response.status,
                    )
                    self._refresh_token = None
                    return False

                data = await response.json()
                new_token = data.get("access_token")
                new_refresh = data.get("refresh_token")

                if not new_token:
                    _LOGGER.debug("No access token in refresh response")
                    return False

                self._token = new_token
                if new_refresh:
                    self._refresh_token = new_refresh

                _LOGGER.debug("Successfully refreshed access token")
                return True

        except aiohttp.ClientError as err:
            _LOGGER.debug("Token refresh failed with error: %s", err)
            return False

    async def _handle_auth_failure(self) -> bool:
        """Handle authentication failure by trying refresh first, then full auth.

        Returns True if re-authentication succeeded.
        """
        self._token = None

        # Try refresh token first
        if await self._refresh_access_token():
            return True

        # Fall back to full authentication
        try:
            await self.authenticate()
            return True
        except ListonicAuthError:
            return False

    async def _ensure_authenticated(self) -> None:
        """Ensure we have a valid token."""
        if not self._token:
            await self.authenticate()

    async def get_lists(self) -> list[ListonicList]:
        """Get all shopping lists."""
        await self._ensure_authenticated()

        url = f"{API_BASE_URL}{API_LISTS_ENDPOINT}"
        params = {
            "includeShares": "true",
            "archive": "false",
            "includeItems": "true",
        }

        for attempt in range(_MAX_AUTH_RETRIES + 1):
            try:
                response = await self._request(
                    "GET", url, params=params, headers=self._get_headers()
                )
                async with response:
                    if response.status == 401:
                        if attempt < _MAX_AUTH_RETRIES:
                            # Token expired, try refresh then full auth
                            if not await self._handle_auth_failure():
                                raise ListonicAuthError(
                                    "Authentication failed after retry"
                                )
                            continue
                        raise ListonicAuthError("Authentication failed after retry")

                    if response.status != 200:
                        text = await response.text()
                        raise ListonicApiError(
                            f"Failed to get lists: {response.status} - {text}"
                        )

                    data = await response.json()
                    return [ListonicList.from_api(lst) for lst in data]

            except aiohttp.ClientError as err:
                raise ListonicApiError(f"Connection error: {err}") from err

        # This should never be reached due to the raise in the loop
        raise ListonicAuthError("Authentication failed after retry")

    async def get_list(self, list_id: int) -> ListonicList:
        """Get a specific shopping list."""
        await self._ensure_authenticated()

        url = f"{API_BASE_URL}{API_LISTS_ENDPOINT}/{list_id}"
        params = {"includeShares": "true"}

        for attempt in range(_MAX_AUTH_RETRIES + 1):
            try:
                response = await self._request(
                    "GET", url, params=params, headers=self._get_headers()
                )
                async with response:
                    if response.status == 401:
                        if attempt < _MAX_AUTH_RETRIES:
                            if not await self._handle_auth_failure():
                                raise ListonicAuthError(
                                    "Authentication failed after retry"
                                )
                            continue
                        raise ListonicAuthError("Authentication failed after retry")

                    if response.status != 200:
                        text = await response.text()
                        raise ListonicApiError(
                            f"Failed to get list: {response.status} - {text}"
                        )

                    data = await response.json()
                    return ListonicList.from_api(data)

            except aiohttp.ClientError as err:
                raise ListonicApiError(f"Connection error: {err}") from err

        raise ListonicAuthError("Authentication failed after retry")

    async def get_list_items(self, list_id: int) -> list[ListonicItem]:
        """Get items for a specific list."""
        await self._ensure_authenticated()

        url = f"{API_BASE_URL}{API_LISTS_ENDPOINT}/{list_id}/items"

        for attempt in range(_MAX_AUTH_RETRIES + 1):
            try:
                response = await self._request(
                    "GET", url, headers=self._get_headers()
                )
                async with response:
                    if response.status == 401:
                        if attempt < _MAX_AUTH_RETRIES:
                            if not await self._handle_auth_failure():
                                raise ListonicAuthError(
                                    "Authentication failed after retry"
                                )
                            continue
                        raise ListonicAuthError("Authentication failed after retry")

                    if response.status != 200:
                        text = await response.text()
                        raise ListonicApiError(
                            f"Failed to get items: {response.status} - {text}"
                        )

                    data = await response.json()
                    return [ListonicItem.from_api(item) for item in data]

            except aiohttp.ClientError as err:
                raise ListonicApiError(f"Connection error: {err}") from err

        raise ListonicAuthError("Authentication failed after retry")

    async def add_item(
        self,
        list_id: int,
        name: str,
        quantity: str | None = None,
        unit: str | None = None,
    ) -> ListonicItem:
        """Add an item to a list."""
        await self._ensure_authenticated()

        url = f"{API_BASE_URL}{API_LISTS_ENDPOINT}/{list_id}/items"
        # API uses PascalCase field names
        payload: dict[str, Any] = {"Name": name}
        if quantity:
            payload["Amount"] = quantity
        if unit:
            payload["Unit"] = unit

        for attempt in range(_MAX_AUTH_RETRIES + 1):
            try:
                response = await self._request(
                    "POST", url, json=payload, headers=self._get_headers()
                )
                async with response:
                    if response.status == 401:
                        if attempt < _MAX_AUTH_RETRIES:
                            if not await self._handle_auth_failure():
                                raise ListonicAuthError(
                                    "Authentication failed after retry"
                                )
                            continue
                        raise ListonicAuthError("Authentication failed after retry")

                    if response.status not in (200, 201):
                        text = await response.text()
                        raise ListonicApiError(
                            f"Failed to add item: {response.status} - {text}"
                        )

                    data = await response.json()
                    return ListonicItem.from_api(data)

            except aiohttp.ClientError as err:
                raise ListonicApiError(f"Connection error: {err}") from err

        raise ListonicAuthError("Authentication failed after retry")

    async def update_item(
        self,
        list_id: int,
        item_id: int,
        *,
        is_checked: bool | None = None,
        name: str | None = None,
        quantity: str | None = None,
        unit: str | None = None,
        description: str | None = None,
        current_item: ListonicItem | None = None,
    ) -> ListonicItem:
        """Update an item.

        Args:
            list_id: The ID of the list containing the item.
            item_id: The ID of the item to update.
            is_checked: Whether the item is checked off.
            name: The item name.
            quantity: The quantity (e.g., "2", "500g").
            unit: The unit of measurement.
            description: Additional description/notes.
            current_item: Optional current item state. If provided, updates are
                applied locally to construct the return value without an extra
                API call. If not provided, a partial item is returned with only
                the updated fields populated.

        Returns:
            ListonicItem with updated values applied. If current_item was provided,
            this reflects the full item state. Otherwise only updated fields and
            the item_id are guaranteed to be accurate.
        """
        await self._ensure_authenticated()

        url = f"{API_BASE_URL}{API_LISTS_ENDPOINT}/{list_id}/items/{item_id}"

        # Map Python names to API names (PascalCase)
        payload: dict[str, Any] = {}
        if is_checked is not None:
            payload["Checked"] = 1 if is_checked else 0
        if name is not None:
            payload["Name"] = name
        if quantity is not None:
            payload["Amount"] = quantity
        if unit is not None:
            payload["Unit"] = unit
        if description is not None:
            payload["Description"] = description

        for attempt in range(_MAX_AUTH_RETRIES + 1):
            try:
                response = await self._request(
                    "PATCH", url, json=payload, headers=self._get_headers()
                )
                async with response:
                    if response.status == 401:
                        if attempt < _MAX_AUTH_RETRIES:
                            if not await self._handle_auth_failure():
                                raise ListonicAuthError(
                                    "Authentication failed after retry"
                                )
                            continue
                        raise ListonicAuthError("Authentication failed after retry")

                    if response.status != 200:
                        text = await response.text()
                        raise ListonicApiError(
                            f"Failed to update item: {response.status} - {text}"
                        )

                    # API returns empty body on success - construct return value
                    # from current_item (if provided) with updates applied
                    if current_item is not None:
                        return ListonicItem(
                            id=item_id,
                            name=name if name is not None else current_item.name,
                            is_checked=(
                                is_checked
                                if is_checked is not None
                                else current_item.is_checked
                            ),
                            quantity=(
                                quantity
                                if quantity is not None
                                else current_item.quantity
                            ),
                            unit=unit if unit is not None else current_item.unit,
                            price=current_item.price,
                            description=(
                                description
                                if description is not None
                                else current_item.description
                            ),
                            category_id=current_item.category_id,
                        )

                    # No current_item provided - return partial item with updated fields
                    return ListonicItem(
                        id=item_id,
                        name=name if name is not None else "",
                        is_checked=is_checked if is_checked is not None else False,
                        quantity=quantity,
                        unit=unit,
                        description=description,
                    )

            except aiohttp.ClientError as err:
                raise ListonicApiError(f"Connection error: {err}") from err

        raise ListonicAuthError("Authentication failed after retry")

    async def check_item(self, list_id: int, item_id: int) -> ListonicItem:
        """Mark an item as checked."""
        return await self.update_item(list_id, item_id, is_checked=True)

    async def uncheck_item(self, list_id: int, item_id: int) -> ListonicItem:
        """Mark an item as unchecked."""
        return await self.update_item(list_id, item_id, is_checked=False)

    async def delete_item(self, list_id: int, item_id: int) -> bool:
        """Delete an item from a list."""
        await self._ensure_authenticated()

        url = f"{API_BASE_URL}{API_LISTS_ENDPOINT}/{list_id}/items/{item_id}"

        for attempt in range(_MAX_AUTH_RETRIES + 1):
            try:
                response = await self._request(
                    "DELETE", url, headers=self._get_headers()
                )
                async with response:
                    if response.status == 401:
                        if attempt < _MAX_AUTH_RETRIES:
                            if not await self._handle_auth_failure():
                                raise ListonicAuthError(
                                    "Authentication failed after retry"
                                )
                            continue
                        raise ListonicAuthError("Authentication failed after retry")

                    if response.status != 200:
                        text = await response.text()
                        raise ListonicApiError(
                            f"Failed to delete item: {response.status} - {text}"
                        )

                    return True

            except aiohttp.ClientError as err:
                raise ListonicApiError(f"Connection error: {err}") from err

        raise ListonicAuthError("Authentication failed after retry")

    async def create_list(self, name: str) -> ListonicList:
        """Create a new shopping list."""
        await self._ensure_authenticated()

        url = f"{API_BASE_URL}{API_LISTS_ENDPOINT}"
        # API uses PascalCase field names
        payload = {"Name": name}

        for attempt in range(_MAX_AUTH_RETRIES + 1):
            try:
                response = await self._request(
                    "POST", url, json=payload, headers=self._get_headers()
                )
                async with response:
                    if response.status == 401:
                        if attempt < _MAX_AUTH_RETRIES:
                            if not await self._handle_auth_failure():
                                raise ListonicAuthError(
                                    "Authentication failed after retry"
                                )
                            continue
                        raise ListonicAuthError("Authentication failed after retry")

                    if response.status not in (200, 201):
                        text = await response.text()
                        raise ListonicApiError(
                            f"Failed to create list: {response.status} - {text}"
                        )

                    data = await response.json()
                    return ListonicList.from_api(data)

            except aiohttp.ClientError as err:
                raise ListonicApiError(f"Connection error: {err}") from err

        raise ListonicAuthError("Authentication failed after retry")

    async def delete_list(self, list_id: int) -> bool:
        """Delete a shopping list."""
        await self._ensure_authenticated()

        url = f"{API_BASE_URL}{API_LISTS_ENDPOINT}/{list_id}"

        for attempt in range(_MAX_AUTH_RETRIES + 1):
            try:
                response = await self._request(
                    "DELETE", url, headers=self._get_headers()
                )
                async with response:
                    if response.status == 401:
                        if attempt < _MAX_AUTH_RETRIES:
                            if not await self._handle_auth_failure():
                                raise ListonicAuthError(
                                    "Authentication failed after retry"
                                )
                            continue
                        raise ListonicAuthError("Authentication failed after retry")

                    if response.status != 200:
                        text = await response.text()
                        raise ListonicApiError(
                            f"Failed to delete list: {response.status} - {text}"
                        )

                    return True

            except aiohttp.ClientError as err:
                raise ListonicApiError(f"Connection error: {err}") from err

        raise ListonicAuthError("Authentication failed after retry")
