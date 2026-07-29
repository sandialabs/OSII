from fastapi import APIRouter

from osii.enrichment.registry import list_enricher_descriptions
from osii.extraction.registry import list_extractor_descriptions
from osii.processors.remote import discover_remote_processors
from osii.synthesis.folder_registry import list_folder_synthesizer_descriptions
from osii.synthesis.registry import list_synthesizer_descriptions

router = APIRouter(prefix="/api/processors", tags=["processors"])


@router.get("")
def list_processors():
    local = [
        *(
            {**item, "kind": "extractor", "remote": False}
            for item in list_extractor_descriptions()
        ),
        *(
            {**item, "kind": "synthesizer", "remote": False, "scope": "object"}
            for item in list_synthesizer_descriptions()
        ),
        *(
            {**item, "kind": "synthesizer", "remote": False, "scope": "folder"}
            for item in list_folder_synthesizer_descriptions()
        ),
        *(
            {**item, "kind": "enricher", "remote": False}
            for item in list_enricher_descriptions()
            if not item.get("remote")
        ),
    ]
    return {
        "local": local,
        "remote": discover_remote_processors(include_errors=True),
    }

