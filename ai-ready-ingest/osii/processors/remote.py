from __future__ import annotations

import json
import os
import urllib.error
import urllib.request
import uuid
from pathlib import Path
from typing import Any

from osii.domain.artifacts.enrichment_artifacts import (
    write_scope_enrichment_variant,
)
from osii.enrichment.common import collect_scope_texts


def configured_processor_urls() -> list[str]:
    configured = [
        value.strip().rstrip("/")
        for value in os.getenv("OSII_PROCESSORS", "").split(",")
        if value.strip()
    ]
    osii_root = os.getenv("OSII_ROOT")
    if osii_root:
        registry_path = Path(osii_root).expanduser() / "state" / "processor_endpoints.json"
        try:
            endpoints = json.loads(registry_path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            endpoints = []
        for endpoint in endpoints:
            if endpoint.get("enabled") and endpoint.get("base_url"):
                configured.append(str(endpoint["base_url"]).rstrip("/"))

    # An endpoint may be configured in both places; only probe it once.
    return list(dict.fromkeys(configured))


def _request_json(url: str, *, payload: dict | None = None, timeout: float = 120.0) -> dict:
    data = None if payload is None else json.dumps(payload).encode("utf-8")
    request = urllib.request.Request(
        url,
        data=data,
        headers={"Content-Type": "application/json"},
        method="GET" if payload is None else "POST",
    )
    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:
            return json.load(response)
    except (urllib.error.URLError, json.JSONDecodeError) as exc:
        raise RuntimeError(f"Processor request to {url} failed: {exc}") from exc


def discover_remote_processors(*, include_errors: bool = False) -> list[dict[str, Any]]:
    discovered = []
    for base_url in configured_processor_urls():
        try:
            descriptor = _request_json(f"{base_url}/v1/descriptor", timeout=5.0)
            descriptor["base_url"] = base_url
            descriptor["remote"] = True
            discovered.append(descriptor)
        except RuntimeError as exc:
            if include_errors:
                discovered.append({"base_url": base_url, "remote": True, "error": str(exc)})
    return discovered


class RemoteEnricher:
    def __init__(self, descriptor: dict[str, Any]) -> None:
        self._descriptor = descriptor
        self.base_url = descriptor["base_url"]
        self.name = descriptor["name"]
        self.version = descriptor["version"]
        self.display_name = descriptor["display_name"]
        self.description = descriptor["description"]

    def describe(self) -> dict[str, Any]:
        return dict(self._descriptor)

    def enrich(
        self,
        *,
        osii_store: Path,
        scope: dict,
        expert_context: str | None = None,
        enricher_config: dict | None = None,
    ) -> dict:
        texts, _ = collect_scope_texts(osii_store, scope)
        scope_type = (scope.get("scope_type") or scope.get("type") or "").strip().lower()
        scope_id = (
            scope.get("file_id")
            or scope.get("folder_id")
            or scope.get("collection_id")
            or "root"
        )
        documents = [
            {
                "file_id": item["file_id"],
                "filename": item["file_id"],
                "media_type": "text/plain",
                "text": item["text"],
                "metadata": {
                    "representation": item.get("representation"),
                    "path": item.get("path"),
                },
            }
            for item in texts
        ]

        processor_input = {
            "scope": {
                "scope_type": scope_type,
                "scope_id": str(scope_id),
                "documents": documents,
            }
        }

        response = _request_json(
            f"{self.base_url}/v1/enrich",
            payload={
                "api_version": "v1",
                "request_id": str(uuid.uuid4()),
                **processor_input,
                "expert_context": expert_context,
                "config": enricher_config or {},
            },
        )
        artifacts = response.get("artifacts") or []
        if not artifacts:
            raise RuntimeError(f"Remote enricher '{self.name}' returned no artifacts")

        results = []
        for artifact in artifacts:
            payload = artifact.get("standard_data")
            if payload is None:
                payload = artifact.get("json_data")
            if payload is None:
                payload = {"text": artifact.get("text")}
            kind = artifact.get("kind") or "enrichment"
            metadata = {
                **(artifact.get("metadata") or {}),
                "artifact_id": artifact.get("id"),
                "method": self.name,
                "version": self.version,
                "processor_url": self.base_url,
            }
            results.append(
                write_scope_enrichment_variant(
                    osii_store,
                    scope,
                    kind=kind,
                    method=(
                        self.name
                        if len(artifacts) == 1
                        else f"{self.name}.{artifact.get('id') or len(results) + 1}"
                    ),
                    payload=payload,
                    metadata=metadata,
                )
            )

        return {
            "ok": True,
            "result": results[0],
            "artifacts": results,
            "error": None,
        }
