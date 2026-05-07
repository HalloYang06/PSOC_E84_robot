from __future__ import annotations

from app.settings import Settings


def test_settings_parse_cors_allowed_origins_list() -> None:
    settings = Settings(
        cors_allowed_origins="https://coop.example.com, https://ops.example.com\nhttps://extra.example.com",
        supertokens_website_domain="https://fallback.example.com",
    )

    assert settings.cors_allowed_origins_list == [
        "https://coop.example.com",
        "https://ops.example.com",
        "https://extra.example.com",
    ]


def test_settings_use_website_domain_as_cors_fallback() -> None:
    settings = Settings(
        cors_allowed_origins="",
        supertokens_website_domain="https://coop.example.com",
    )

    assert settings.cors_allowed_origins_list == ["https://coop.example.com"]


def test_settings_parse_supertokens_cookie_secure_override() -> None:
    truthy = Settings(supertokens_cookie_secure="true")
    falsy = Settings(supertokens_cookie_secure="false")
    empty = Settings(supertokens_cookie_secure="")

    assert truthy.supertokens_cookie_secure_override is True
    assert falsy.supertokens_cookie_secure_override is False
    assert empty.supertokens_cookie_secure_override is None
