import logging
import schwabdev

from app.core.config import settings

logger = logging.getLogger(__name__)

_client: schwabdev.Client | None = None


def get_schwab_client() -> schwabdev.Client:
    global _client
    if _client is None:
        _client = schwabdev.Client(
            app_key=settings.schwab_app_key,
            app_secret=settings.schwab_app_secret,
            callback_url=settings.schwab_callback_url,
            call_on_auth=_on_auth,
        )
    return _client


def _on_auth(url: str) -> str:
    logger.info("Schwab re-authentication required. Open this URL to authenticate: %s", url)
    return input("Paste the callback URL after authenticating: ")
