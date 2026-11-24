"""Browser security headers and a request-size cap, shared by the apps that serve a page."""

from __future__ import annotations

import base64
import hashlib
import re
from pathlib import Path

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse

MAX_BODY = 256_000  # bytes; a full valid request is under ~140 KB even in 3-byte UTF-8


def csp_for(page: Path) -> str:
    """A Content-Security-Policy that allows the page's own inline script and nothing else."""
    scripts = re.findall(r"<script>(.*?)</script>", page.read_text(), re.DOTALL)
    hashes = " ".join(
        f"'sha256-{base64.b64encode(hashlib.sha256(s.encode()).digest()).decode()}'"
        for s in scripts
    )
    return (
        f"default-src 'self'; script-src {hashes}; style-src 'self' 'unsafe-inline'; "
        "img-src 'self' data:; connect-src 'self'; base-uri 'none'; form-action 'self'; "
        "frame-ancestors 'none'"
    )


def harden(app: FastAPI, page: Path, max_body: int = MAX_BODY) -> None:
    """Reject oversized request bodies before parsing, and send security headers on every reply."""
    headers = {
        "Content-Security-Policy": csp_for(page),
        "X-Content-Type-Options": "nosniff",
        "Referrer-Policy": "no-referrer",
    }

    @app.middleware("http")
    async def guard(request: Request, call_next):
        if request.method == "POST":
            size = request.headers.get("content-length")
            if size is None:  # a chunked body could be any size
                return JSONResponse({"error": "length_required"}, status_code=411)
            if not size.isdigit() or int(size) > max_body:
                return JSONResponse({"error": "too_large"}, status_code=413)
        response = await call_next(request)
        response.headers.update(headers)
        return response
