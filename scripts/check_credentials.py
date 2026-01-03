#!/usr/bin/env python3
"""Check Listonic webapp for credential changes.

This script fetches the Listonic webapp JS bundle and extracts the OAuth
credentials. If they differ from the current values in const.py, it updates
the file.

Exit codes:
    0 - No changes needed
    1 - Error occurred
    2 - Credentials updated
"""

from __future__ import annotations

import re
import sys
from pathlib import Path

import requests

WEBAPP_URL = "https://app.listonic.com"
CONST_FILE = Path(__file__).parent.parent / "custom_components" / "listonic" / "const.py"


def get_app_js_url() -> str | None:
    """Fetch the webapp and find the _app JS bundle URL."""
    response = requests.get(WEBAPP_URL, timeout=30)
    response.raise_for_status()

    # Find the _app chunk URL in the HTML
    # Pattern: /_next/static/chunks/pages/_app-{hash}.js
    match = re.search(
        r'/_next/static/chunks/pages/_app-[a-f0-9]+\.js',
        response.text
    )
    if match:
        return f"{WEBAPP_URL}{match.group(0)}"
    return None


def extract_credentials(js_content: str) -> dict[str, str] | None:
    """Extract OAuth credentials from the JS bundle."""
    # Pattern matches the credential function in the bundle:
    # var e="listonicv2",t="fjdfsoj...",r="https://..."
    # return{clientId:e,clientSecret:t,redirectUrl:r}
    pattern = r'var\s+\w+="(listonicv2)",\w+="([^"]+)",\w+="(https://[^"]+)"'
    match = re.search(pattern, js_content)

    if match:
        return {
            "client_id": match.group(1),
            "client_secret": match.group(2),
            "redirect_uri": match.group(3),
        }
    return None


def get_current_credentials() -> dict[str, str]:
    """Read current credentials from const.py."""
    content = CONST_FILE.read_text()

    credentials = {}
    for var_name, key in [
        ("CLIENT_ID", "client_id"),
        ("CLIENT_SECRET", "client_secret"),
        ("REDIRECT_URI", "redirect_uri"),
    ]:
        match = re.search(rf'^{var_name}\s*=\s*"([^"]+)"', content, re.MULTILINE)
        if match:
            credentials[key] = match.group(1)

    return credentials


def update_credentials(new_credentials: dict[str, str]) -> None:
    """Update const.py with new credentials."""
    content = CONST_FILE.read_text()

    for var_name, key in [
        ("CLIENT_ID", "client_id"),
        ("CLIENT_SECRET", "client_secret"),
        ("REDIRECT_URI", "redirect_uri"),
    ]:
        if key in new_credentials:
            content = re.sub(
                rf'^({var_name}\s*=\s*")[^"]+(")',
                rf'\g<1>{new_credentials[key]}\g<2>',
                content,
                flags=re.MULTILINE,
            )

    CONST_FILE.write_text(content)


def main() -> int:
    """Main entry point."""
    print("Checking Listonic credentials...")

    # Get the app JS URL
    print(f"Fetching {WEBAPP_URL}...")
    app_js_url = get_app_js_url()
    if not app_js_url:
        print("ERROR: Could not find _app JS bundle URL")
        return 1

    print(f"Found JS bundle: {app_js_url}")

    # Fetch the JS bundle
    print("Fetching JS bundle...")
    response = requests.get(app_js_url, timeout=30)
    response.raise_for_status()

    # Extract credentials
    new_credentials = extract_credentials(response.text)
    if not new_credentials:
        print("ERROR: Could not extract credentials from JS bundle")
        return 1

    print(f"Extracted credentials: client_id={new_credentials['client_id']}")

    # Get current credentials
    current_credentials = get_current_credentials()
    print(f"Current credentials: client_id={current_credentials.get('client_id', 'NOT FOUND')}")

    # Compare
    if new_credentials == current_credentials:
        print("Credentials unchanged")
        return 0

    # Update
    print("Credentials changed! Updating const.py...")
    print(f"  client_id: {current_credentials.get('client_id')} -> {new_credentials['client_id']}")
    print(f"  client_secret: {'*' * 8} -> {'*' * 8}")
    print(f"  redirect_uri: {current_credentials.get('redirect_uri')} -> {new_credentials['redirect_uri']}")

    update_credentials(new_credentials)
    print("Updated const.py")

    return 2


if __name__ == "__main__":
    sys.exit(main())
