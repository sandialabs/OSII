from collections import Counter
from pathlib import Path

from fastapi import APIRouter, Request

router = APIRouter(prefix="/api", tags=["osii"])


@router.get("/osii/stats")
async def osii_stats(request: Request):
    osii_root = request.app.state.osii_root.resolve()

    total_files = 0
    by_suffix = Counter()

    if osii_root.exists():
        for p in osii_root.rglob("*"):
            if p.is_file():
                total_files += 1
                by_suffix[p.suffix.lower() or "<no_ext>"] += 1

    return {
        "root": str(osii_root),
        "total_files": total_files,
        "by_suffix": dict(sorted(by_suffix.items())),
    }