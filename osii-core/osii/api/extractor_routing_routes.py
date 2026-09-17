from fastapi import APIRouter

from osii.extraction.registry import list_extractor_descriptions

router = APIRouter()


@router.get("/api/extractors")
def get_extractors():
    return {
        "extractors": list_extractor_descriptions()
    }