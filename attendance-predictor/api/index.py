"""
Vercel Python serverless entry: WSGI `app` with PATH_INFO fix so /api/* reaches Flask routes.
"""
from __future__ import annotations

import os
import sys
from urllib.parse import urlparse

_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
_BACKEND = os.path.join(_ROOT, "backend")
if _BACKEND not in sys.path:
    sys.path.insert(0, _BACKEND)

os.chdir(_BACKEND)

from app import app as _flask_app  # noqa: E402


class _VercelPathFix:
    """
    Vercel sometimes invokes this function with PATH_INFO like /api/index while the browser
    requested /api/predict. Prefer PATH_INFO when it already looks like a real API path;
    otherwise recover path from REQUEST_URI / RAW_URI.
    """

    _SKIP = frozenset({"/api/index", "/api/index.py"})

    def __call__(self, environ, start_response):
        path_info = environ.get("PATH_INFO") or ""

        if path_info.startswith("/api/") and path_info not in self._SKIP:
            return _flask_app(environ, start_response)

        raw = (
            environ.get("REQUEST_URI")
            or environ.get("RAW_URI")
            or environ.get("HTTP_X_ORIGINAL_URL")
            or ""
        )
        if raw:
            if raw.startswith("http://") or raw.startswith("https://"):
                parsed = urlparse(raw)
            else:
                parsed = urlparse(raw if raw.startswith("/") else "/" + raw)
            real_path = parsed.path.split("?", 1)[0]
            if real_path.startswith("/api/") and real_path not in self._SKIP:
                environ["PATH_INFO"] = real_path
                if parsed.query:
                    environ["QUERY_STRING"] = parsed.query
                return _flask_app(environ, start_response)

        return _flask_app(environ, start_response)


app = _VercelPathFix()
