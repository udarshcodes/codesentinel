"""Post-deployment acceptance checks. Credentials never enter output or URLs."""
import argparse
from http.cookiejar import CookieJar
from http.client import HTTPException
import json
import re
import subprocess
import time
from urllib.error import HTTPError, URLError
from urllib.parse import urlsplit
from urllib.request import HTTPCookieProcessor, Request, build_opener


def verify_release(base, revision=None, secret=None, attempts=30):
    origin = urlsplit(base)
    if origin.scheme != "https" and not (origin.scheme == "http" and origin.hostname in {"localhost", "127.0.0.1"}):
        raise ValueError("Release probes require HTTPS or local loopback.")
    if origin.username or origin.password or origin.query or origin.fragment or origin.path not in ("", "/"):
        raise ValueError("Use a plain API origin without credentials or URL parameters.")
    base = base.rstrip("/")
    client = build_opener(HTTPCookieProcessor(CookieJar()))

    def request(path, body=None, request_origin=None):
        headers = {}
        if request_origin:
            headers["Origin"] = request_origin
        if body is not None:
            headers["Content-Type"] = "application/json"
        req = Request(base + path, data=json.dumps(body).encode() if body is not None else None, headers=headers)
        return client.open(req, timeout=15)

    for attempt in range(attempts):
        try:
            with request("/ready") as ready, request("/health") as health:
                if ready.status == 200 and (not revision or health.headers.get("X-CodeSentinel-Revision") == revision):
                    break
        except (URLError, HTTPError, OSError, HTTPException):
            pass
        if attempt + 1 == attempts:
            raise RuntimeError("Expected deployed revision did not become ready.")
        time.sleep(5)
    with request("/admin") as response:
        html = response.read().decode()
        if response.status != 200 or 'id="root"' not in html:
            raise RuntimeError("API-hosted admin page is unavailable.")
    script = re.search(r'src="(/assets/[^"?]+\.js)"', html)
    if not script:
        raise RuntimeError("Admin page has no application bundle.")
    with request(script.group(1)) as response:
        if response.status != 200:
            raise RuntimeError("Admin application bundle is unavailable.")
    if not secret:
        return
    try:
        with request("/api/v1/admin/login", {"secret": secret}, base):
            pass
        with request("/api/v1/admin/telemetry") as response:
            if json.load(response).get("status") != "ok":
                raise RuntimeError("Admin telemetry did not return a valid authenticated response.")
        try:
            request("/api/v1/admin/logout", {}, "https://untrusted.invalid")
        except HTTPError as error:
            if error.code != 403:
                raise RuntimeError("Admin origin protection did not reject an untrusted mutation.") from None
        else:
            raise RuntimeError("Admin accepted an untrusted origin.")
    finally:
        with request("/api/v1/admin/logout", {}, base):
            pass
    try:
        request("/api/v1/admin/telemetry")
    except HTTPError as error:
        if error.code != 401:
            raise RuntimeError("Logged-out admin session was not rejected.") from None
    else:
        raise RuntimeError("Admin session remained active after logout.")


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--url", required=True)
    parser.add_argument("--revision")
    parser.add_argument("--azure-admin", action="store_true")
    args = parser.parse_args()
    secret = None
    if args.azure_admin:
        result = subprocess.run(["az", "containerapp", "secret", "show", "-n", "codesentinel-api", "-g", "CodeSentinel-RG",
                                 "--secret-name", "admin-secret", "--query", "value", "-o", "tsv"], capture_output=True, text=True, timeout=30)
        if result.returncode or not result.stdout.strip():
            raise SystemExit("Admin credential was unavailable for the release acceptance check.")
        secret = result.stdout.strip()
    verify_release(args.url, args.revision, secret)
    print("Release readiness and revision checks passed." + (" Authenticated admin lifecycle passed." if secret else ""))
