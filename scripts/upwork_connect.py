"""Sign in to Upwork's official MCP server and list its tools. Nothing else: this script never
calls a tool, so it cannot read your data, spend Connects or send anything.

    uv run --env-file .env python -m scripts.upwork_connect

You sign in on Upwork in your own browser (OAuth with PKCE, through the MCP SDK). Tokens are
Fernet-encrypted with TOKEN_ENCRYPTION_KEY into var/upwork/ (git-ignored) and never printed.
The tool names and schemas go to var/upwork/tools.json; they are what the upwork_live adapter
has to be mapped from. The server URL comes from UPWORK_MCP_URL. The sign-in redirect is a
one-off local listener (--redirect-uri), separate from the web app's UPWORK_REDIRECT_URI.
`--forget` deletes the stored sign-in.
"""

from __future__ import annotations

import argparse
import asyncio
import json
import os
import shutil
import sys
import threading
import webbrowser
from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path
from urllib.parse import parse_qs, urlsplit

from mcp import ClientSession
from mcp.client.auth import OAuthClientProvider
from mcp.client.streamable_http import streamablehttp_client
from mcp.shared.auth import OAuthClientInformationFull, OAuthClientMetadata, OAuthToken

from apps.api.security import TokenVault

ROOT = Path(__file__).resolve().parents[1]
STORE = ROOT / "var" / "upwork"
DEFAULT_URL = "https://mcp.upwork.com/mcp"
DEFAULT_REDIRECT = "http://localhost:8765/callback"


class EncryptedStorage:
    """The SDK's token storage, sealed with the app's token vault."""

    def __init__(self, folder: Path, vault: TokenVault):
        self.folder, self.vault = folder, vault

    def _read(self, name: str) -> dict | None:
        path = self.folder / name
        return self.vault.open(path.read_text(encoding="ascii")) if path.exists() else None

    def _write(self, name: str, data: dict) -> None:
        self.folder.mkdir(parents=True, exist_ok=True)
        (self.folder / name).write_text(self.vault.seal(data), encoding="ascii")

    async def get_tokens(self) -> OAuthToken | None:
        data = self._read("tokens.enc")
        return OAuthToken.model_validate(data) if data else None

    async def set_tokens(self, tokens: OAuthToken) -> None:
        self._write("tokens.enc", tokens.model_dump(mode="json", exclude_none=True))

    async def get_client_info(self) -> OAuthClientInformationFull | None:
        data = self._read("client.enc")
        return OAuthClientInformationFull.model_validate(data) if data else None

    async def set_client_info(self, client_info: OAuthClientInformationFull) -> None:
        self._write("client.enc", client_info.model_dump(mode="json", exclude_none=True))


def parse_callback(path: str) -> tuple[str, str | None] | None:
    """(code, state) from the redirect request path, or None if it carries no code."""
    query = parse_qs(urlsplit(path).query)
    if "code" not in query:
        return None
    return query["code"][0], query.get("state", [None])[0]


def wait_for_redirect(redirect_uri: str) -> tuple[str, str | None]:
    """Serve the loopback redirect once and return the authorization code."""
    target = urlsplit(redirect_uri)
    result: list[tuple[str, str | None]] = []
    done = threading.Event()

    class Handler(BaseHTTPRequestHandler):
        def do_GET(self) -> None:  # noqa: N802 - http.server's name
            parsed = parse_callback(self.path)
            self.send_response(200 if parsed else 400)
            self.send_header("Content-Type", "text/plain; charset=utf-8")
            self.end_headers()
            self.wfile.write(
                b"Signed in. You can close this tab." if parsed else b"No authorization code."
            )
            if parsed:
                result.append(parsed)
                done.set()

        def log_message(self, *args) -> None:  # the URL holds the code: never log it
            return

    server = HTTPServer((target.hostname or "localhost", target.port or 80), Handler)
    threading.Thread(target=server.serve_forever, daemon=True).start()
    try:
        if not done.wait(timeout=300):
            raise TimeoutError("no sign-in within 5 minutes")
        return result[0]
    finally:
        server.shutdown()


async def list_upwork_tools(url: str, redirect_uri: str, storage: EncryptedStorage) -> list[dict]:
    async def open_browser(authorization_url: str) -> None:
        print("Opening Upwork sign-in in your browser. If nothing opens, visit:")
        print(authorization_url)
        webbrowser.open(authorization_url)

    async def callback() -> tuple[str, str | None]:
        return await asyncio.to_thread(wait_for_redirect, redirect_uri)

    auth = OAuthClientProvider(
        server_url=url,
        client_metadata=OAuthClientMetadata(
            client_name="GigBid",
            redirect_uris=[redirect_uri],
            token_endpoint_auth_method="none",
        ),
        storage=storage,
        redirect_handler=open_browser,
        callback_handler=callback,
    )
    async with (
        streamablehttp_client(url, auth=auth) as (read, write, _),
        ClientSession(read, write) as session,
    ):
        await session.initialize()
        tools, cursor = [], None
        while True:
            page = await session.list_tools(cursor=cursor)
            tools += [t.model_dump(mode="json", exclude_none=True) for t in page.tools]
            cursor = page.nextCursor
            if not cursor:
                return tools


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--forget", action="store_true", help="delete the stored sign-in")
    ap.add_argument("--redirect-uri", default=DEFAULT_REDIRECT, help="local sign-in listener")
    args = ap.parse_args(argv)
    if args.forget:
        shutil.rmtree(STORE, ignore_errors=True)
        print("stored Upwork sign-in deleted")
        return 0
    if not os.environ.get("TOKEN_ENCRYPTION_KEY"):
        print("TOKEN_ENCRYPTION_KEY is not set; see .env.example", file=sys.stderr)
        return 2
    url = os.environ.get("UPWORK_MCP_URL") or DEFAULT_URL
    try:
        tools = asyncio.run(
            list_upwork_tools(url, args.redirect_uri, EncryptedStorage(STORE, TokenVault()))
        )
    except Exception as exc:  # noqa: BLE001 - show the real reason; nothing was changed
        while getattr(exc, "exceptions", None):
            exc = exc.exceptions[0]
        print(f"could not connect: {type(exc).__name__}: {exc}", file=sys.stderr)
        return 1
    STORE.mkdir(parents=True, exist_ok=True)
    (STORE / "tools.json").write_text(json.dumps(tools, indent=2) + "\n", encoding="utf-8")
    print(f"signed in; {len(tools)} tools (schemas saved to var/upwork/tools.json):")
    for tool in tools:
        notes = tool.get("annotations") or {}
        kind = "read" if notes.get("readOnlyHint") else "may write"
        print(f"  {tool['name']:<40} {kind}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
