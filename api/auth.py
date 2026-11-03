"""API-key authentication for every route (REST and /mcp), as ASGI middleware.

Set API_KEY to enable it. The key can be sent as:
  - header  X-API-Key: <key>
  - header  Authorization: Bearer <key>
  - query   ?api_key=<key>   (for clients that cannot set headers, e.g. some MCP connector UIs)
If API_KEY is unset, auth is off (local development only).
"""

from __future__ import annotations

import json
import logging
import os
import secrets
from urllib.parse import parse_qs

log = logging.getLogger("b2b-crm")

PUBLIC_PATHS = {"/", "/health", "/docs", "/docs/oauth2-redirect", "/openapi.json", "/redoc"}


def _extract_key(scope) -> str | None:
    headers = {k.decode().lower(): v.decode() for k, v in scope.get("headers", [])}
    if headers.get("x-api-key"):
        return headers["x-api-key"]
    auth = headers.get("authorization", "")
    if auth.lower().startswith("bearer "):
        return auth[7:].strip()
    values = parse_qs(scope.get("query_string", b"").decode()).get("api_key")
    return values[0] if values else None


class APIKeyMiddleware:
    def __init__(self, app):
        self.app = app
        if not os.environ.get("API_KEY"):
            log.warning("API_KEY is not set: the API and MCP endpoint are open to anyone.")

    async def __call__(self, scope, receive, send):
        expected = os.environ.get("API_KEY")
        if (scope["type"] != "http" or not expected or scope["path"] in PUBLIC_PATHS
                or scope.get("method") == "OPTIONS"):
            return await self.app(scope, receive, send)

        key = _extract_key(scope)
        if key and secrets.compare_digest(key.encode(), expected.encode()):
            return await self.app(scope, receive, send)

        body = json.dumps({"detail": "Missing or invalid API key"}).encode()
        await send({"type": "http.response.start", "status": 401, "headers": [
            (b"content-type", b"application/json"),
            (b"www-authenticate", b"Bearer"),
            (b"content-length", str(len(body)).encode()),
        ]})
        await send({"type": "http.response.body", "body": body})
