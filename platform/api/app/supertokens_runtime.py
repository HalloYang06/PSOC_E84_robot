from __future__ import annotations

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.settings import Settings


def is_supertokens_enabled(settings: Settings) -> bool:
    return settings.supertokens_enabled


def setup_supertokens(app: FastAPI, settings: Settings) -> None:
    if not is_supertokens_enabled(settings):
        return

    from supertokens_python import InputAppInfo, SupertokensConfig, get_all_cors_headers, init
    from supertokens_python.framework.fastapi.fastapi_middleware import get_middleware
    from supertokens_python.ingredients.emaildelivery.types import SMTPSettings, SMTPSettingsFrom
    from supertokens_python.recipe import emailpassword, emailverification, session
    from supertokens_python.recipe.emailpassword import SMTPService as EmailPasswordSMTPService
    from supertokens_python.recipe.emailverification import SMTPService as EmailVerificationSMTPService
    from supertokens_python.ingredients.emaildelivery.types import EmailDeliveryConfig

    email_password_delivery = None
    email_verification_delivery = None

    if settings.supertokens_smtp_host.strip() and settings.supertokens_smtp_from_email.strip():
        smtp_settings = SMTPSettings(
            host=settings.supertokens_smtp_host.strip(),
            port=settings.supertokens_smtp_port,
            username=settings.supertokens_smtp_username.strip() or None,
            password=settings.supertokens_smtp_password.strip() or None,
            secure=settings.supertokens_smtp_secure,
            from_=SMTPSettingsFrom(
                name=settings.supertokens_smtp_from_name.strip() or settings.supertokens_app_name.strip() or "AI协作平台",
                email=settings.supertokens_smtp_from_email.strip(),
            ),
        )
        email_password_delivery = EmailDeliveryConfig(
            service=EmailPasswordSMTPService(smtp_settings=smtp_settings)
        )
        email_verification_delivery = EmailDeliveryConfig(
            service=EmailVerificationSMTPService(smtp_settings=smtp_settings)
        )

    cookie_secure = (
        settings.supertokens_cookie_secure_override
        if settings.supertokens_cookie_secure_override is not None
        else settings.is_production
    )

    init(
        app_info=InputAppInfo(
            app_name=settings.supertokens_app_name,
            api_domain=settings.supertokens_api_domain,
            website_domain=settings.supertokens_website_domain,
            api_base_path=settings.supertokens_api_base_path,
            website_base_path=settings.supertokens_website_base_path,
        ),
        framework="fastapi",
        supertokens_config=SupertokensConfig(
            connection_uri=settings.supertokens_connection_uri,
            api_key=settings.supertokens_api_key.strip() or None,
        ),
        recipe_list=[
            emailpassword.init(email_delivery=email_password_delivery),
            session.init(
                anti_csrf="NONE",
                cookie_same_site="lax",
                cookie_secure=cookie_secure,
            ),
            emailverification.init(
                settings.supertokens_email_verification_mode.strip().upper(),
                email_delivery=email_verification_delivery,
            ),
        ],
        mode="asgi",
    )

    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors_allowed_origins_list,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["content-type"] + get_all_cors_headers(),
    )
    app.add_middleware(get_middleware())
