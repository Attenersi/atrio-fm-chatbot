"""Per-request correlation id (``X-Request-ID``) via contextvars for logging."""

from __future__ import annotations

import logging
import re
import uuid
from contextvars import ContextVar

REQUEST_ID_HEADER = "X-Request-ID"

request_id_var: ContextVar[str] = ContextVar("request_id", default="")

_MAX_LEN = 128
# Accept only unambiguous correlation tokens; otherwise generate a UUID.
_SAFE_REQUEST_ID = re.compile(r"^[a-zA-Z0-9-]{1,128}$")


def get_request_id() -> str:
    rid = request_id_var.get()
    return rid if rid else "-"


def normalize_request_id(raw: str | None) -> str:
    if raw is None:
        return str(uuid.uuid4())
    s = raw.strip()[:_MAX_LEN]
    if not s or not _SAFE_REQUEST_ID.match(s):
        return str(uuid.uuid4())
    return s


class RequestIdLogFilter(logging.Filter):
    """Inject ``record.request_id`` for format strings that include ``%(request_id)s``."""

    def filter(self, record: logging.LogRecord) -> bool:  # noqa: A003
        record.request_id = get_request_id()
        return True


def add_request_id_filters(*logger_names: str) -> None:
    filt = RequestIdLogFilter()
    for name in logger_names:
        logging.getLogger(name).addFilter(filt)
