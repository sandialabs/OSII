# Enrichment API

`POST /v1/enrich` produces structured, rebuildable artifacts over an object,
folder, collection, or root scope.

This is the normal extension point for experimental campaigns. For example, a
service can receive documents from 1,000 folders, apply facility-specific
rules, and return one typed table containing run conditions and outcomes.

## Request

```json
{
  "api_version": "v1",
  "request_id": "enrich-101",
  "scope": {
    "scope_type": "folder",
    "scope_id": "campaign-2026",
    "documents": [{
      "file_id": "sha256-a",
      "filename": "run-001.txt",
      "text": "Run: 001\nTemperature: 21.4 C\nResult: pass"
    }]
  },
  "expert_context": "Temperatures are ambient unless explicitly labeled.",
  "config": {"include_failed": true}
}
```

## Response

```json
{
  "api_version": "v1",
  "request_id": "enrich-101",
  "processor": {"...descriptor": "..."},
  "artifacts": [{
    "id": "experiment-table",
    "kind": "experiment_results",
    "media_type": "application/json",
    "standard_data": {
      "artifact_type": "table",
      "title": "Campaign results",
      "columns": [
        {"key": "run", "label": "Run", "data_type": "string"},
        {"key": "temperature", "label": "Temperature", "data_type": "number", "unit": "C"}
      ],
      "rows": [{"run": "001", "temperature": 21.4}],
      "row_provenance": []
    }
  }],
  "metadata": {},
  "warnings": []
}
```

Every v1 enrichment must use one of the standard artifact formats so it is
immediately usable in the dashboard and by agents. The dashboard retains a
generic JSON view only for legacy artifacts created before this contract.

See `examples/enricher.py` and `services/table-pdf-enricher`.
