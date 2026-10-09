"""Minimal JSON-over-HTTPS helper with retries (standard library only)."""
import json
import time
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode
from urllib.request import Request, urlopen

USER_AGENT = "filmio-mapping/1.0 (+https://github.com/ceto/filmio-mapping)"


class HttpError(Exception):
    def __init__(self, status, url):
        Exception.__init__(self, "HTTP %s for %s" % (status, url))
        self.status = status


def get_json(url, params=None, headers=None, timeout=20, retries=4, opener=urlopen, sleep=time.sleep):
    """GET url and decode JSON. Retries network errors, 429 and 5xx with
    back-off (honouring Retry-After); other HTTP errors raise HttpError."""
    if params:
        url += ("&" if "?" in url else "?") + urlencode(params)
    hdrs = {"User-Agent": USER_AGENT, "Accept": "application/json"}
    hdrs.update(headers or {})
    delay = 1.0
    for attempt in range(retries + 1):
        try:
            with opener(Request(url, headers=hdrs), timeout=timeout) as resp:
                return json.loads(resp.read().decode("utf-8"))
        except HTTPError as exc:
            status = exc.code
            retry_after = exc.headers.get("Retry-After") if exc.headers else None
            exc.close()
            if status != 429 and status < 500:
                raise HttpError(status, _safe(url))
            wait = float(retry_after) if retry_after and retry_after.isdigit() else delay
        except (URLError, OSError):
            wait = delay
        if attempt == retries:
            raise HttpError("network", _safe(url))
        sleep(wait)
        delay = min(delay * 2, 30)


def _safe(url):
    """URL without its query string (it may contain an API key)."""
    return url.split("?", 1)[0]
