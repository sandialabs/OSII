from dataclasses import replace
import json

import pytest

from osii.domain.read.contracts import DocumentRecord, Page, RepresentationRecord, SegmentRecord
from osii.domain.research import EvidenceChanged, ReportGenerationError, ReportRequest, write_report


class Reader:
    def __init__(self):
        self.documents = [DocumentRecord("file-a", "papers/report.txt", "report.txt")]
        self.representation = RepresentationRecord("canonical", "file-a",
            "Detector study\nJane Researcher, 2024\nThermal neutrons are measured.",
            (SegmentRecord("p1", "", 0, 67, {"page": 2}),))

    def list_documents(self, scope, **kwargs):
        return Page(tuple(self.documents), len(self.documents))

    def get_document(self, file_id):
        return next((d for d in self.documents if d.file_id == file_id), None)

    def get_representation(self, file_id, representation_id="canonical"):
        return self.representation if file_id == "file-a" else None


def request(**kwargs):
    return ReportRequest(scope={"scope_type": "object", "file_id": "file-a"},
                         prompt="Explain the detector", **kwargs)


def test_links_reference_exact_source_text_and_heuristic_bibliography():
    reader = Reader()
    result = write_report(reader, request(), lambda messages: "# Detector\n\nIt measures neutrons. [[S1]]", provider="test", model="writer")
    source = result.sources[0]
    assert source.excerpt == reader.representation.text[source.char_start:source.char_end]
    assert source.page == 2
    assert source.segment_id == "p1"
    assert "char_start=0" in source.href
    assert "extraction_id=canonical" in source.href
    assert f"[S1]({source.href})" in result.markdown
    assert "Unknown author (2024). *Detector study*" in result.markdown
    assert "best guess" in result.markdown
    assert len(source.text_sha256) == 64


@pytest.mark.parametrize("answer", ["Facts [[S99]]", "Facts with no citations", "Facts [[invented]]", "Facts [[S1]] [fake](/files/secret)"])
def test_invalid_or_missing_citations_are_not_returned(answer):
    with pytest.raises(ReportGenerationError):
        write_report(Reader(), request(), lambda _: answer)


def test_revision_rehydrates_links_and_preserves_user_bibliography():
    reader = Reader()
    original = write_report(reader, request(), lambda _: "Original [[S1]]")
    original.markdown = original.markdown.partition("\n## Bibliography\n")[0] + "\n## Bibliography\n\nMy corrected reference."
    def complete(messages):
        data = json.loads(messages[1]["content"])
        assert "Original [[S1]]" in data["current_report"]
        assert data["revision_request"] == "Clarify"
        assert data["evidence"][0]["excerpt"] == reader.representation.text
        return "Clarified [[S1]]"
    result = write_report(reader, request(current_markdown=original.markdown, improvement="Clarify", sources=original.sources), complete)
    assert result.markdown.endswith("My corrected reference.")


def test_changed_or_forged_evidence_is_rejected_before_generation():
    reader = Reader()
    original = write_report(reader, request())
    reader.representation = replace(reader.representation, text="Changed text")
    with pytest.raises(EvidenceChanged):
        write_report(reader, request(current_markdown=original.markdown, improvement="Clarify", sources=original.sources), lambda _: pytest.fail("must not invoke model"))
    reader = Reader()
    original.sources[0].excerpt = "forged"
    with pytest.raises(EvidenceChanged):
        write_report(reader, request(sources=original.sources))


def test_out_of_scope_citations_and_disappearing_documents_are_rejected():
    reader = Reader()
    original = write_report(reader, request())
    payload = request(sources=original.sources)
    payload.scope.file_id = "another-document"
    with pytest.raises(EvidenceChanged):
        write_report(reader, payload)


def test_corpus_change_during_generation_is_detected():
    reader = Reader()
    def complete(_):
        reader.representation = replace(reader.representation, text="changed during call")
        return "Report [[S1]]"
    with pytest.raises(EvidenceChanged):
        write_report(reader, request(), complete)


def test_empty_scope_and_offline_revision_explain_next_step():
    reader = Reader()
    reader.documents = []
    with pytest.raises(ValueError, match="No extracted text"):
        write_report(reader, request())
    reader = Reader()
    with pytest.raises(ValueError, match="Choose a chat model"):
        write_report(reader, request(current_markdown="current", improvement="Improve"))
    assert write_report(reader, request()).provider == "extractive"


def test_source_paths_and_model_prompts_never_define_reference_urls():
    reader = Reader()
    reader.documents[0] = replace(reader.documents[0], filename="[tricky](javascript:bad)", source_relpath="../../private")
    result = write_report(reader, request(), lambda _: "Report [[S1]]")
    assert result.sources[0].href.startswith("/files/file-a?")
    assert "../../private" not in result.sources[0].href


def test_prompt_and_scope_validation():
    with pytest.raises(ValueError):
        ReportRequest(scope={"scope_type": "root"}, prompt="report")
    with pytest.raises(ValueError):
        request(format="html")
    with pytest.raises(ValueError):
        ReportRequest(scope={"scope_type": "object", "file_id": "file-a"}, prompt=" ")


def test_report_samples_documents_explicitly_and_preserves_page_boundaries():
    class LargeReader(Reader):
        def __init__(self):
            super().__init__()
            self.documents = [DocumentRecord(f"file-{i}", f"{i:03}.txt", f"{i}.txt") for i in range(80)]

        def list_documents(self, scope, limit=24, **kwargs):
            return Page(tuple(self.documents[:limit]), 80)

        def get_representation(self, file_id, representation_id="canonical"):
            return replace(self.representation, file_id=file_id)

    result = write_report(LargeReader(), ReportRequest(scope={"scope_type": "collection", "collection_id": "large"}, prompt="Explain"))
    assert result.documents_in_scope == 80
    assert result.documents_sampled == 24
    assert len(result.sources) == 24
    assert all(source.page == 2 for source in result.sources)
    assert any("first 24" in warning for warning in result.warnings)
    assert "text_sha256=" in result.sources[0].href


def test_source_text_that_looks_like_a_citation_remains_quoted_evidence():
    reader = Reader()
    reader.representation = replace(reader.representation, text="This is source text with [[S99]] in it.", segments=())
    result = write_report(reader, request())
    assert result.sources[0].excerpt.endswith("[[S99]] in it.")
    assert "\\[\\[S99\\]\\]" in result.markdown
