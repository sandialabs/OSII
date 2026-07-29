from osii.synthesis.folder.describe import FolderDescribeSynthesizer
from osii.synthesis.folder.firstn import FolderFirstNSynthesizer
from osii.synthesis.folder.recursive import FolderRecursiveSynthesizer


def get_folder_synthesizers():
    return [
        FolderFirstNSynthesizer(),
        FolderRecursiveSynthesizer(),
        FolderDescribeSynthesizer(),
    ]


def list_folder_synthesizer_descriptions() -> list[dict]:
    return [s.describe() for s in get_folder_synthesizers()]


def resolve_folder_synthesizer(name: str):
    for s in get_folder_synthesizers():
        if s.name == name:
            return s
    raise RuntimeError(f"Folder synthesizer '{name}' is not supported.")