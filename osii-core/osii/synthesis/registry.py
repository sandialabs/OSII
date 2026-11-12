from osii.synthesis.file.describe import DescribeSynthesizer
from osii.synthesis.file.firstn import FirstNSynthesizer
from osii.synthesis.file.image_describe import ImageDescribeSynthesizer
from osii.synthesis.file.recursive import RecursiveSynthesizer


def get_synthesizers():
    return [
        DescribeSynthesizer(),
        FirstNSynthesizer(),
        RecursiveSynthesizer(),
        ImageDescribeSynthesizer(),
    ]


def list_synthesizer_descriptions() -> list[dict]:
    return [s.describe() for s in get_synthesizers() if s.name != "firstN"]


def resolve_synthesizer(name: str):
    for s in get_synthesizers():
        if s.name == name:
            return s
    raise RuntimeError(f"File synthesizer '{name}' is not supported.")


def resolve_synthesis_method(name: str):
    """Resolve the compatibility synthesis names without importing HTTP routes."""
    if name == "firstN":
        return FirstNSynthesizer()
    if name == "recursive":
        return RecursiveSynthesizer()
    from osii.processors.remote import RemoteSynthesizer, resolve_remote_processor
    return RemoteSynthesizer(resolve_remote_processor(name, "synthesizer"))
