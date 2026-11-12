import pytest
from osii.domain.workbench import home_state


def test_readiness_is_per_tool_and_partial_indexing_is_usable():
    state = home_state(
        documents=12,
        text_documents=8,
        indexed_documents=3,
        index_ready=True,
        chat_configured=False,
        setup_dismissed=False,
    )
    tools = state["tools"]
    assert (
        tools["search"]["enabled"]
        and tools["browse"]["enabled"]
        and tools["overview"]["enabled"]
    )
    assert not tools["chat"]["enabled"] and not tools["research"]["enabled"]
    assert tools["topics"] == {"enabled": True, "reason": "3 of 12 documents ready"}


@pytest.mark.parametrize(
    "documents,text,chat,indexed,valid,expected",
    [
        (0, 0, False, 0, False, set()),
        (2, 0, True, 0, False, {"browse", "overview"}),
        (2, 2, True, 0, False, {"browse", "overview", "search", "chat", "research"}),
        (2, 2, True, 2, False, {"browse", "overview", "search", "chat", "research"}),
    ],
)
def test_incomplete_information_never_enables_an_unusable_tile(
    documents, text, chat, indexed, valid, expected
):
    state = home_state(
        documents=documents,
        text_documents=text,
        indexed_documents=indexed,
        index_ready=valid,
        chat_configured=chat,
        setup_dismissed=True,
    )
    assert {
        key for key, value in state["tools"].items() if value["enabled"]
    } == expected
    assert all(value["reason"] for value in state["tools"].values())
    assert not state["setup"]["visible"]
