"""
Cross-site request check for the API (CSRF, belt and braces).

The API authenticates with a bearer token, which another site cannot attach to
a request, and the refresh cookie is SameSite=Strict and scoped to its one URL.
Two endpoints still matter without a token: sign-in and sign-up, which set that
cookie (a forged sign-in would put the victim into the attacker's account), and
refresh itself on an older browser that ignores SameSite.

So a state-changing request that a browser marks as coming from another site is
refused before any view runs. Requests with no Origin at all — Telegram's
webhook, the cron caller, curl — are not browsers acting for a user and pass.
"""
from urllib.parse import urlsplit

from django.conf import settings
from django.http import JsonResponse

SAFE_METHODS = {"GET", "HEAD", "OPTIONS", "TRACE"}
LOCAL_HOSTS = {"localhost", "127.0.0.1", "[::1]"}


def _origin_of(url):
    parts = urlsplit(url or "")
    return f"{parts.scheme}://{parts.netloc}".lower() if parts.scheme and parts.netloc else ""


def trusted(request, origin):
    origin = origin.lower()
    if origin == _origin_of(f"{'https' if request.is_secure() else 'http'}://{request.get_host()}"):
        return True
    allowed = {_origin_of(o) for o in settings.CSRF_TRUSTED_ORIGINS} | {_origin_of(settings.APP_ORIGIN)}
    if origin in allowed:
        return True
    # Local development: the Vite server on any port proxies to the API.
    return settings.DEBUG and urlsplit(origin).hostname in {h.strip("[]") for h in LOCAL_HOSTS}


class OriginCheckMiddleware:
    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        if request.method not in SAFE_METHODS and request.path.startswith("/api/"):
            origin = request.headers.get("Origin")
            if origin:
                # "null" comes from sandboxed frames and file:// pages, never from the app.
                refused = origin == "null" or not trusted(request, origin)
            else:
                refused = request.headers.get("Sec-Fetch-Site") == "cross-site"
            if refused:
                return JsonResponse({"detail": "Cross-site request refused.", "code": "cross_site"}, status=403)
        return self.get_response(request)
