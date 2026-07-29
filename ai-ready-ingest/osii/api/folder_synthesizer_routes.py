from fastapi import APIRouter

from osii.synthesis.folder_registry import list_folder_synthesizer_descriptions

router = APIRouter()


@router.get("/api/folder-synthesizers")
def get_folder_synthesizers():
    return {
        "folder_synthesizers": list_folder_synthesizer_descriptions()
    }