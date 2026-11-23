"""Quiet successful status reads without hiding failures or user actions."""
import logging


class StatusAccessFilter(logging.Filter):
    def filter(self, record):
        args = record.args
        if not isinstance(args, tuple) or len(args) != 5:
            return True
        _, method, path, _, status = args
        path = str(path).split("?", 1)[0]
        routine = path in {"/health", "/v1/diagnostics", "/api/admin/setup", "/api/admin/processor-settings", "/api/intake/defaults", "/api/extractor-routes", "/api/admin/model-providers", "/api/admin/processors", "/api/intake/readiness", "/api/runs", "/api/workbench/home", "/api/volume/sources", "/api/volume/runs"} or path.endswith(("/logs", "/scans"))
        return not ((method == "GET" or (method == "POST" and path in {"/api/admin/model-providers/discover", "/api/scopes/overview"})) and isinstance(status, int) and 200 <= status < 300 and (routine or path in {"/api/admin/model-providers/discover", "/api/scopes/overview"}))


def quiet_status_logs():
    logger = logging.getLogger("uvicorn.access")
    if not any(isinstance(f, StatusAccessFilter) for f in logger.filters):
        logger.addFilter(StatusAccessFilter())
