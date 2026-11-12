"""Temporary storage helpers for the demo module."""

from __future__ import annotations

import json
import shutil
import time
import uuid
from pathlib import Path

import cv2

from app.config import settings
from app.core.pdf import render_pdf_pages
from app.core.utils import encode_png, load_image_bytes


class DemoStorage:
    """Manage demo uploads, rendered pages, previews, and cached region sets."""

    def __init__(self, root_dir: str) -> None:
        """Initialize storage.

        Parameters
        ----------
        root_dir : str
            Root storage directory.
        """
        self.root = Path(root_dir)
        self.root.mkdir(parents=True, exist_ok=True)

    def cleanup_old(self, max_age_hours: int = 6) -> None:
        """Remove old demo directories.

        Parameters
        ----------
        max_age_hours : int, optional
            Maximum directory age in hours, by default 6.
        """
        cutoff = time.time() - (max_age_hours * 3600)
        for child in self.root.iterdir():
            try:
                if child.is_dir() and child.stat().st_mtime < cutoff:
                    shutil.rmtree(child, ignore_errors=True)
            except Exception:
                continue

    def create_document(self, file_bytes: bytes, filename: str, dpi: int) -> dict:
        """Create a new demo document record.

        Parameters
        ----------
        file_bytes : bytes
            Uploaded file bytes.
        filename : str
            Original filename.
        dpi : int
            Render DPI for PDFs.

        Returns
        -------
        dict
            Document metadata.
        """
        self.cleanup_old()

        doc_id = uuid.uuid4().hex
        doc_dir = self.root / doc_id
        pages_dir = doc_dir / "pages"
        previews_dir = doc_dir / "previews"
        regions_dir = doc_dir / "regions"

        pages_dir.mkdir(parents=True, exist_ok=True)
        previews_dir.mkdir(parents=True, exist_ok=True)
        regions_dir.mkdir(parents=True, exist_ok=True)

        source_path = doc_dir / filename
        source_path.write_bytes(file_bytes)

        if filename.lower().endswith(".pdf"):
            pages = render_pdf_pages(file_bytes, dpi=dpi)
        else:
            pages = [load_image_bytes(file_bytes, filename)]

        page_records = []
        for index, page_image in enumerate(pages, start=1):
            page_path = pages_dir / f"page-{index}.png"
            cv2.imwrite(str(page_path), page_image)
            page_records.append(
                {
                    "page": index,
                    "width": int(page_image.shape[1]),
                    "height": int(page_image.shape[0]),
                    "image_url": f"/demo/assets/{doc_id}/pages/page-{index}.png",
                }
            )

        return {
            "doc_id": doc_id,
            "page_count": len(page_records),
            "pages": page_records,
        }

    def get_page_path(self, doc_id: str, page: int) -> Path:
        """Return the stored path for a rendered page.

        Parameters
        ----------
        doc_id : str
            Document identifier.
        page : int
            Page number.

        Returns
        -------
        Path
            Page image path.
        """
        return self.root / doc_id / "pages" / f"page-{page}.png"

    def get_doc_dir(self, doc_id: str) -> Path:
        """Return the document directory.

        Parameters
        ----------
        doc_id : str
            Document identifier.

        Returns
        -------
        Path
            Document directory.
        """
        return self.root / doc_id

    def save_preview(self, doc_id: str, page: int, name: str, image) -> str:
        """Save a preview image for the demo.

        Parameters
        ----------
        doc_id : str
            Document identifier.
        page : int
            Page number.
        name : str
            Preview name.
        image : np.ndarray
            Image to save.

        Returns
        -------
        str
            Browser-accessible URL.
        """
        preview_dir = self.root / doc_id / "previews"
        preview_dir.mkdir(parents=True, exist_ok=True)

        file_path = preview_dir / f"page-{page}-{name}.png"
        png_bytes = encode_png(image)
        file_path.write_bytes(png_bytes)

        return f"/demo/assets/{doc_id}/previews/{file_path.name}"

    def save_region_set(
        self,
        doc_id: str,
        page: int,
        params: dict,
        regions: list[dict],
        stats: dict,
    ) -> str:
        """Persist a detected region set.

        Parameters
        ----------
        doc_id : str
            Document identifier.
        page : int
            Page number.
        params : dict
            Detection parameters.
        regions : list[dict]
            Detected regions.
        stats : dict
            Detection statistics.

        Returns
        -------
        str
            Region set identifier.
        """
        region_set_id = uuid.uuid4().hex
        region_dir = self.root / doc_id / "regions"
        region_dir.mkdir(parents=True, exist_ok=True)

        payload = {
            "region_set_id": region_set_id,
            "doc_id": doc_id,
            "page": page,
            "params": params,
            "regions": regions,
            "stats": stats,
        }

        path = region_dir / f"page-{page}-{region_set_id}.json"
        path.write_text(json.dumps(payload, indent=2), encoding="utf-8")
        return region_set_id

    def load_region_set(self, doc_id: str, page: int, region_set_id: str) -> dict:
        """Load a cached region set.

        Parameters
        ----------
        doc_id : str
            Document identifier.
        page : int
            Page number.
        region_set_id : str
            Region set identifier.

        Returns
        -------
        dict
            Region set payload.

        Raises
        ------
        FileNotFoundError
            If the region set file does not exist.
        """
        path = self.root / doc_id / "regions" / f"page-{page}-{region_set_id}.json"
        return json.loads(path.read_text(encoding="utf-8"))


storage = DemoStorage(settings.demo_storage_dir)