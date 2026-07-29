import json

from osii.extraction.registry import list_extractor_descriptions
from osii.synthesis.registry import list_synthesizer_descriptions
from osii.synthesis.folder_registry import list_folder_synthesizer_descriptions


def main():
    payload = {
        "extractors": list_extractor_descriptions(),
        "synthesizers": list_synthesizer_descriptions(),
        "folder_synthesizers": list_folder_synthesizer_descriptions(),
    }
    print(json.dumps(payload, indent=2))


if __name__ == "__main__":
    main()