"""Desktop-only loopback protection and compiled dashboard serving."""
from __future__ import annotations

import hmac
from pathlib import Path

from fastapi import HTTPException
from fastapi.responses import FileResponse
from starlette.responses import JSONResponse


class DesktopAccess:
    def __init__(self, app, *, token: str, port: int):
        self.app = app
        self.token = "Bearer " + token
        self.host = f"127.0.0.1:{port}"

    async def __call__(self, scope, receive, send):
        if scope["type"] not in {"http", "websocket"}:
            return await self.app(scope, receive, send)
        headers = dict(scope.get("headers", []))
        supplied = headers.get(b"authorization", b"").decode("latin1")
        host = headers.get(b"host", b"").decode("latin1")
        origin = headers.get(b"origin", b"").decode("latin1")
        allowed = (hmac.compare_digest(supplied, self.token) and host == self.host
                   and (not origin or origin == "http://" + self.host))
        if not allowed:
            if scope["type"] == "websocket":
                return await send({"type": "websocket.close", "code": 1008})
            response = JSONResponse({"detail": "This endpoint belongs to the OSII desktop session."}, status_code=403)
            return await response(scope, receive, send)
        async def secured_send(message):
            if message["type"] == "http.response.start":
                headers_out = list(message.get("headers", []))
                headers_out += [(b"x-content-type-options", b"nosniff"), (b"referrer-policy", b"no-referrer"),
                    (b"content-security-policy", b"default-src 'self'; script-src 'self'; worker-src 'self' blob:; style-src 'self' 'unsafe-inline'; img-src 'self' data: blob:; font-src 'self' data:; connect-src 'self'; frame-src 'self' blob:; object-src 'none'; base-uri 'self'; frame-ancestors 'self'")]
                message = {**message, "headers": headers_out}
            await send(message)
        return await self.app(scope, receive, secured_send)


def attach_dashboard(app, directory: Path, token: str, *, port: int) -> None:
    directory = directory.resolve()
    if not (directory / "index.html").is_file():
        raise RuntimeError("The compiled dashboard is missing. Reinstall OSII.")
    # Preserve every API route and replace only Core's JSON landing page.
    app.router.routes[:] = [route for route in app.router.routes if getattr(route, "path", None) != "/"]

    @app.get("/{asset:path}", include_in_schema=False)
    def dashboard_asset(asset: str):
        target = (directory / asset).resolve()
        if not target.is_relative_to(directory):
            raise HTTPException(status_code=404)
        if target.is_file():
            return FileResponse(target)
        if asset.split("/", 1)[0] in {"api", "artifact", "assets", "docs", "openapi.json", "health"} or Path(asset).suffix:
            raise HTTPException(status_code=404)
        return FileResponse(directory / "index.html", headers={"Cache-Control": "no-store"})

    app.add_middleware(DesktopAccess, token=token, port=port)
