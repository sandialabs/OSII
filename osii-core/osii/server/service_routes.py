"""Administrator-only adapter to the deployment's private tool controller."""
from __future__ import annotations

import http.client
import json
import os
import socket

from fastapi import Depends, HTTPException
from osii.server.auth import require

SERVICE_IDS = {"extractor", "ocr-page", "ocr-regions"}


class UnixConnection(http.client.HTTPConnection):
    def connect(self):
        self.sock = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
        self.sock.settimeout(self.timeout)
        self.sock.connect(self.host)


def controller(method: str, path: str):
    address = os.environ.get("OSII_TOOL_CONTROL_SOCKET", "")
    if not address:
        raise HTTPException(503, "Tool lifecycle control is not configured for this deployment")
    connection = UnixConnection(address, timeout=25)
    try:
        connection.request(method, path, body=b"" if method == "POST" else None)
        response = connection.getresponse()
        raw = response.read(524289)
        if len(raw) > 524288:
            raise ValueError("Oversized controller response")
        payload = json.loads(raw)
        if response.status != 200:
            raise HTTPException(response.status, "Tool controller could not complete this request")
        return payload
    except (OSError, ValueError, http.client.HTTPException):
        raise HTTPException(503, "Tool controller is unavailable; contact the server operator") from None
    finally:
        connection.close()


def register_service_routes(app, store):
    def validate(service_id, action=None):
        if service_id not in SERVICE_IDS or action is not None and action not in {"start", "stop", "restart"}:
            raise HTTPException(404, "Unknown managed tool or action")

    @app.get("/api/admin/services")
    def services(account=Depends(require("admin"))):
        result = controller("GET", "/services")
        from osii.processor_sdk import ProcessorClient
        for item in result.get("services", []):
            if item["status"] != "running":
                continue
            try:
                health = ProcessorClient(item["url"], timeout=2).health()
                if health.get("status") not in {"ok", "ready", "healthy"}:
                    raise ValueError("Not ready")
                item["detail"] = "Process running; health check passed."
            except Exception:
                item["status"] = "unhealthy"
                item["detail"] = "Process running, but its health check failed. Inspect logs before restarting."
        return result

    @app.get("/api/admin/services/{service_id}/logs")
    def logs(service_id: str, account=Depends(require("admin"))):
        validate(service_id)
        result = controller("GET", f"/services/{service_id}/logs")
        store.record("tool_logs_read", account["id"], service_id)
        return result

    @app.post("/api/admin/services/{service_id}/{action}")
    def control(service_id: str, action: str, account=Depends(require("admin"))):
        validate(service_id, action)
        store.record("tool_" + action + "_requested", account["id"], service_id)
        return controller("POST", f"/services/{service_id}/{action}")
