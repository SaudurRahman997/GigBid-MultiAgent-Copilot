from cryptography.fernet import Fernet
from mcp.shared.auth import OAuthToken

from apps.api.security import TokenVault
from scripts.upwork_connect import EncryptedStorage, parse_callback


def test_parse_callback_needs_a_code():
    assert parse_callback("/callback?code=abc&state=xyz") == ("abc", "xyz")
    assert parse_callback("/callback?code=abc") == ("abc", None)
    assert parse_callback("/callback?error=access_denied") is None
    assert parse_callback("/favicon.ico") is None


async def _roundtrip(storage: EncryptedStorage) -> OAuthToken | None:
    await storage.set_tokens(OAuthToken(access_token="secret-access-value", token_type="Bearer"))
    return await storage.get_tokens()


def test_tokens_are_encrypted_at_rest(tmp_path):
    import asyncio

    storage = EncryptedStorage(tmp_path, TokenVault(Fernet.generate_key().decode()))
    assert asyncio.run(storage.get_tokens()) is None
    assert asyncio.run(_roundtrip(storage)).access_token == "secret-access-value"
    assert "secret-access-value" not in (tmp_path / "tokens.enc").read_text(encoding="ascii")
    other = EncryptedStorage(tmp_path, TokenVault(Fernet.generate_key().decode()))
    assert asyncio.run(other.get_tokens()) is None  # a different key cannot read them
