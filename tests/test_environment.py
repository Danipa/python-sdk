"""Environment from the key prefix, and the explicit overrides.

``dk_test_`` → sandbox, ``dk_live_`` → live (the server's own markers, see
``MerchantApiKeyService``). An explicit ``base_url`` / ``environment`` always
wins. Any other prefix with no override is a configuration error at
construction: a key must never be guessed into an environment.
"""

from __future__ import annotations

import asyncio

import pytest

from danipa import AsyncDanipa, Danipa, DanipaConfigurationError, DanipaError
from danipa.http import (
    PRODUCTION_BASE_URL,
    PRODUCTION_NOT_LIVE_MESSAGE,
    SANDBOX_BASE_URL,
    infer_base_url,
    resolve_base_url,
)
from tests.conftest import MERCHANT_BODY, FakeServer, json_response


def test_test_key_defaults_to_sandbox() -> None:
    assert SANDBOX_BASE_URL == "https://api.sandbox.danipa.com/ms"
    server = FakeServer(json_response(200, MERCHANT_BODY))
    with Danipa(api_key="dk_test_abc", transport=server.transport) as danipa:
        assert danipa.base_url == SANDBOX_BASE_URL
        danipa.merchants.me()
    assert str(server.last.url) == "https://api.sandbox.danipa.com/ms/v1/merchants/me"


def test_live_key_is_refused_until_production_launches() -> None:
    assert PRODUCTION_BASE_URL == "https://api.danipa.com/ms"
    assert infer_base_url("dk_live_abc") == PRODUCTION_BASE_URL
    server = FakeServer(json_response(200, MERCHANT_BODY))
    with pytest.raises(DanipaConfigurationError) as excinfo:
        Danipa(api_key="dk_live_topsecret", transport=server.transport)
    assert str(excinfo.value) == PRODUCTION_NOT_LIVE_MESSAGE
    assert "topsecret" not in str(excinfo.value)
    assert server.requests == []


@pytest.mark.parametrize(
    "api_key",
    ["sk_test_abc", "something_else", "DK_TEST_abc", "dk_testabc", "dk_x", "pk_live_abc", " dk_test_x"],
)
def test_unknown_prefix_is_a_configuration_error_at_construction(api_key: str) -> None:
    server = FakeServer(json_response(200, MERCHANT_BODY))
    with pytest.raises(DanipaConfigurationError, match="dk_test_") as info:
        Danipa(api_key=api_key, transport=server.transport)
    assert server.requests == []
    # catchable as the SDK base error and as a plain ValueError
    assert isinstance(info.value, DanipaError)
    assert isinstance(info.value, ValueError)
    # the message never echoes the key
    assert api_key.strip() not in str(info.value)


def test_unknown_prefix_async_is_a_configuration_error() -> None:
    with pytest.raises(DanipaConfigurationError):
        AsyncDanipa(api_key="unknown_key")


def test_infer_base_url_raises_for_unknown_prefix() -> None:
    with pytest.raises(DanipaConfigurationError):
        infer_base_url("xyz")


def test_explicit_base_url_overrides_a_test_key() -> None:
    server = FakeServer(json_response(200, MERCHANT_BODY))
    with Danipa(
        api_key="dk_test_abc", base_url="http://localhost:8080/ms/", transport=server.transport
    ) as danipa:
        danipa.merchants.me()
    assert str(server.last.url) == "http://localhost:8080/ms/v1/merchants/me"


def test_explicit_base_url_rescues_an_unknown_prefix() -> None:
    danipa = Danipa(api_key="legacy_key", base_url="https://api.example.test/ms")
    assert danipa.base_url == "https://api.example.test/ms"
    danipa.close()


def test_explicit_environment_overrides_the_prefix() -> None:
    assert resolve_base_url("dk_live_abc", None, "sandbox") == SANDBOX_BASE_URL
    assert resolve_base_url("unknown", None, "sandbox") == SANDBOX_BASE_URL
    for key in ("dk_test_abc", "unknown"):
        with pytest.raises(DanipaConfigurationError, match="production is not live yet"):
            resolve_base_url(key, None, "live")


def test_environment_option_on_both_clients() -> None:
    danipa = Danipa(api_key="custom", environment="sandbox")
    assert danipa.base_url == SANDBOX_BASE_URL
    danipa.close()

    async def run() -> None:
        with pytest.raises(DanipaConfigurationError, match="production is not live yet"):
            AsyncDanipa(api_key="custom", environment="live")

    asyncio.run(run())


def test_base_url_wins_over_environment() -> None:
    assert (
        resolve_base_url("dk_test_x", "https://api.example.test/ms/", "live")
        == "https://api.example.test/ms"
    )


def test_unknown_environment_is_a_configuration_error() -> None:
    with pytest.raises(DanipaConfigurationError, match="unknown environment"):
        Danipa(api_key="dk_test_abc", environment="production")  # type: ignore[arg-type]
