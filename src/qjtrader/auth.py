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


class BrokerTokenSource:
    """Fetch capability-limited tokens from QJ Connect on loopback.

    QJ Connect keeps the account credential in the operating-system vault. A
    supervised child receives only a loopback URL and a per-run bearer key.
    The broker refuses scopes that were not approved for that project/run.
    """

    def __init__(self, broker_url: str, broker_key: str, scope: str) -> None:
        self._url = broker_url.rstrip("/")
        self._key = broker_key
        self._scope = scope
        self._token: str | None = None
        self._expires_at = 0.0

    def token(self) -> str:
        if self._token and time.time() < self._expires_at - _REFRESH_SKEW:
            return self._token
        req = urllib.request.Request(
            f"{self._url}/token",
            data=json.dumps({"scope": self._scope}).encode(),
            headers={
                "Authorization": f"Bearer {self._key}",
                "Content-Type": "application/json",
            },
        )
        try:
            with urllib.request.urlopen(req, timeout=5) as resp:
                data = json.loads(resp.read())
            token = data["access_token"]
            expires_in = float(data.get("expires_in", 300))
        except urllib.error.HTTPError as error:
            detail = error.read().decode("utf-8", "replace")[:300]
            raise TokenError(
                f"QJ Connect denied the requested capability (HTTP {error.code}): {detail}"
            ) from None
        except urllib.error.URLError as error:
            raise TokenError(f"QJ Connect token broker is unavailable: {error.reason}") from None
        except (ValueError, KeyError):
            raise TokenError("QJ Connect token broker returned an unexpected response") from None
        self._token = token
        self._expires_at = time.time() + expires_in
        return self._token
