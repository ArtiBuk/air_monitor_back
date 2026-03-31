import os

MYCITYAIR_TOKEN = os.getenv("MYCITYAIR_TOKEN")
REQUEST_TIMEOUT = int(os.getenv("REQUEST_TIMEOUT", "30"))
USE_FAKE_USER_AGENT = os.getenv("USE_FAKE_USER_AGENT", "1") == "1"

DEFAULT_HEADERS = {
    "Accept-Language": "ru-RU,ru;q=0.9,en-US;q=0.8,en;q=0.7",
    "Accept": "*/*",
    "Connection": "keep-alive",
}
