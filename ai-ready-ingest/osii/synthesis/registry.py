from osii.synthesis.file.describe import DescribeSynthesizer
from osii.synthesis.file.firstn import FirstNSynthesizer
from osii.synthesis.file.recursive import RecursiveSynthesizer
from osii.synthesis.file.image_describe import ImageDescribeSynthesizer


def get_synthesizers():
    return [
        DescribeSynthesizer(),
        FirstNSynthesizer(),
        RecursiveSynthesizer(),
        ImageDescribeSynthesizer(),
    ]


def list_synthesizer_descriptions() -> list[dict]:
    return [s.describe() for s in get_synthesizers()]


def resolve_synthesizer(name: str):
    for s in get_synthesizers():
        if s.name == name:
            return s
    raise RuntimeError(f"File synthesizer '{name}' is not supported.")