"""Tests for remediation/tokens.py -- the GitHub App JWT and the installation
tokens it buys. Every GitHub call is mocked; the RSA key is generated here in
memory, so nothing in this file touches the network or a real credential.
"""
from __future__ import annotations

import jwt
import pytest
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import rsa

from remediation.tokens import (
    AppTokenProvider,
    DevTokenProvider,
    TokenError,
    app_configured,
    app_jwt,
    default_provider,
    fetch_installation,
)

_KEY = rsa.generate_private_key(public_exponent=65537, key_size=2048)
PRIVATE_PEM = _KEY.private_bytes(
    encoding=serialization.Encoding.PEM,
    format=serialization.PrivateFormat.PKCS8,
    encryption_algorithm=serialization.NoEncryption(),
).decode()
PUBLIC_PEM = _KEY.public_key().public_bytes(
    encoding=serialization.Encoding.PEM,
    format=serialization.PublicFormat.SubjectPublicKeyInfo,
).decode()


@pytest.fixture
def configured_app(tmp_path, monkeypatch):
    key_path = tmp_path / "app.pem"
    key_path.write_text(PRIVATE_PEM, encoding="utf-8")
    monkeypatch.setenv("GITHUB_APP_ID", "424242")
    monkeypatch.setenv("GITHUB_APP_PRIVATE_KEY_PATH", str(key_path))
    monkeypatch.delenv("SENTINELS_ALLOW_DEV_TOKEN", raising=False)
    monkeypatch.delenv("SENTINELS_GITHUB_DEV_TOKEN", raising=False)
    return key_path


def test_app_not_configured_without_env(monkeypatch):
    monkeypatch.delenv("GITHUB_APP_ID", raising=False)
    monkeypatch.delenv("GITHUB_APP_PRIVATE_KEY_PATH", raising=False)
    assert app_configured() is False


def test_app_jwt_carries_the_expected_claims(configured_app):
    token = app_jwt(now=1_000_000)
    claims = jwt.decode(token, PUBLIC_PEM, algorithms=["RS256"], options={"verify_exp": False})
    assert claims["iss"] == "424242"
    assert claims["iat"] == 1_000_000 - 60      # backdated against clock skew
    assert claims["exp"] == 1_000_000 + 9 * 60  # under GitHub's 10-minute ceiling


def test_app_jwt_is_signed_with_the_configured_key(configured_app):
    other = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    other_public = other.public_key().public_bytes(
        encoding=serialization.Encoding.PEM,
        format=serialization.PublicFormat.SubjectPublicKeyInfo,
    ).decode()
    token = app_jwt(now=1_000_000)
    with pytest.raises(jwt.InvalidSignatureError):
        jwt.decode(token, other_public, algorithms=["RS256"], options={"verify_exp": False})


def test_app_jwt_raises_when_unconfigured(monkeypatch):
    monkeypatch.delenv("GITHUB_APP_ID", raising=False)
    monkeypatch.delenv("GITHUB_APP_PRIVATE_KEY_PATH", raising=False)
    with pytest.raises(TokenError):
        app_jwt()


def test_private_key_missing_file_is_treated_as_unconfigured(monkeypatch, tmp_path):
    monkeypatch.setenv("GITHUB_APP_ID", "1")
    monkeypatch.setenv("GITHUB_APP_PRIVATE_KEY_PATH", str(tmp_path / "nope.pem"))
    assert app_configured() is False


async def test_mints_an_installation_token(configured_app, mock_api):
    client = mock_api({
        ("POST", "/app/installations/99/access_tokens"): (
            201, {"token": "ghs_secret", "expires_at": "2026-08-12T12:00:00Z"}
        ),
    })
    result = await AppTokenProvider().token_for(client, 99)
    await client.aclose()
    assert result.token == "ghs_secret"
    assert result.expires_at == "2026-08-12T12:00:00Z"


async def test_401_reports_a_key_or_app_id_problem(configured_app, mock_api):
    client = mock_api({("POST", "/app/installations/99/access_tokens"): (401, {})})
    with pytest.raises(TokenError, match="GITHUB_APP_ID"):
        await AppTokenProvider().token_for(client, 99)
    await client.aclose()


async def test_404_reports_the_installation_as_gone(configured_app, mock_api):
    client = mock_api({("POST", "/app/installations/99/access_tokens"): (404, {})})
    with pytest.raises(TokenError, match="no longer exists"):
        await AppTokenProvider().token_for(client, 99)
    await client.aclose()


async def test_unexpected_status_is_still_terminal(configured_app, mock_api):
    client = mock_api({("POST", "/app/installations/99/access_tokens"): (500, {})})
    with pytest.raises(TokenError, match="HTTP 500"):
        await AppTokenProvider().token_for(client, 99)
    await client.aclose()


async def test_a_201_with_no_token_is_rejected(configured_app, mock_api):
    client = mock_api({("POST", "/app/installations/99/access_tokens"): (201, {"expires_at": "x"})})
    with pytest.raises(TokenError, match="no token"):
        await AppTokenProvider().token_for(client, 99)
    await client.aclose()


async def test_fetch_installation_reads_the_account(configured_app, mock_api):
    client = mock_api({
        ("GET", "/app/installations/99"): (
            200, {"account": {"login": "octo"}, "repository_selection": "selected"}
        ),
    })
    data = await fetch_installation(client, 99)
    await client.aclose()
    assert data["account"]["login"] == "octo"


async def test_fetch_installation_returns_none_when_github_declines(configured_app, mock_api):
    client = mock_api({})
    assert await fetch_installation(client, 99) is None
    await client.aclose()


async def test_dev_token_refuses_without_the_explicit_opt_in(monkeypatch, mock_api):
    monkeypatch.setenv("SENTINELS_GITHUB_DEV_TOKEN", "ghp_something")
    monkeypatch.delenv("SENTINELS_ALLOW_DEV_TOKEN", raising=False)
    client = mock_api({})
    with pytest.raises(TokenError, match="SENTINELS_ALLOW_DEV_TOKEN"):
        await DevTokenProvider().token_for(client, 1)
    await client.aclose()


async def test_dev_token_works_with_both_switches_on(monkeypatch, mock_api):
    monkeypatch.setenv("SENTINELS_GITHUB_DEV_TOKEN", "ghp_something")
    monkeypatch.setenv("SENTINELS_ALLOW_DEV_TOKEN", "1")
    client = mock_api({})
    result = await DevTokenProvider().token_for(client, 1)
    await client.aclose()
    assert result.token == "ghp_something"


async def test_dev_token_opted_in_but_unset_still_fails(monkeypatch, mock_api):
    monkeypatch.setenv("SENTINELS_ALLOW_DEV_TOKEN", "1")
    monkeypatch.delenv("SENTINELS_GITHUB_DEV_TOKEN", raising=False)
    client = mock_api({})
    with pytest.raises(TokenError, match="not set"):
        await DevTokenProvider().token_for(client, 1)
    await client.aclose()


def test_default_provider_is_the_app_unless_both_dev_switches_are_on(monkeypatch):
    monkeypatch.delenv("SENTINELS_ALLOW_DEV_TOKEN", raising=False)
    monkeypatch.delenv("SENTINELS_GITHUB_DEV_TOKEN", raising=False)
    assert isinstance(default_provider(), AppTokenProvider)

    monkeypatch.setenv("SENTINELS_GITHUB_DEV_TOKEN", "ghp_x")
    assert isinstance(default_provider(), AppTokenProvider)  # token alone isn't enough

    monkeypatch.setenv("SENTINELS_ALLOW_DEV_TOKEN", "1")
    assert isinstance(default_provider(), DevTokenProvider)
