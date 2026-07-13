"""OAuth2 client-credentials token source.

A credential mints its own short-lived JWT (the console never hands out tokens).
`TokenSource` fetches one on demand and caches it until shortly before expiry, so
callers can just ask for `.token()` every time.
"""
from __future__ import annotations

import base64
import json
import time
import urllib.error
import urllib.parse
import urllib.request

from .errors import TokenError

_REFRESH_SKEW = 60.0  # refresh this many seconds before expiry


class TokenSource:
    """Mints and caches an access token for one (credential, scope)."""

    def __init__(self, token_url: str, client_id: str, client_secret: str,
                 scope: str) -> None:
        self._url = token_url
        self._cid = client_id
        self._secret = client_secret
        self._scope = scope
        self._token: str | None = None
        self._expires_at = 0.0

    def token(self) -> str:
        """A valid access token, refreshed automatically before it expires."""
        if self._token and time.time() < self._expires_at - _REFRESH_SKEW:
            return self._token

        body = urllib.parse.urlencode(
            {"grant_type": "client_credentials", "scope": self._scope}
        ).encode()
        basic = base64.b64encode(f"{self._cid}:{self._secret}".encode()).decode()
        req = urllib.request.Request(
            self._url,
            data=body,
            headers={
                "Authorization": f"Basic {basic}",
                "Content-Type": "application/x-www-form-urlencoded",
            },
        )
        try:
            with urllib.request.urlopen(req, timeout=15) as resp:
                data = json.loads(resp.read())
        except urllib.error.HTTPError as e:
            detail = e.read().decode("utf-8", "replace")[:300]
            raise TokenError(f"token request failed (HTTP {e.code}): {detail}") from None
        except urllib.error.URLError as e:
            raise TokenError(f"token request failed: {e.reason}") from None
        except (ValueError, KeyError):
            raise TokenError("token endpoint returned an unexpected response") from None

        self._token = data["access_token"]
        self._expires_at = time.time() + float(data.get("expires_in", 3600))
        return self._token
