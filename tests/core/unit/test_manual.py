"""Manual content invariants."""

from __future__ import annotations

from lairen import __version__
from lairen.cli import cli
from lairen.manual import (
    IDENTITY_NOTES,
    TOPIC_ORDER,
    TOPICS,
    all_payload,
    all_text,
    topic_payload,
)
from lairen.providers import PROVIDERS


def test_topics_are_ordered_and_complete() -> None:
    assert set(TOPIC_ORDER) == set(TOPICS)
    assert len(TOPIC_ORDER) == len(TOPICS)


def test_every_topic_is_concise_and_has_an_example() -> None:
    for slug in TOPIC_ORDER:
        title, text = TOPICS[slug]
        assert title
        assert text.strip()
        assert "lairen " in text
        assert len(text.splitlines()) < 90


def test_identity_notes_cover_every_provider() -> None:
    assert set(IDENTITY_NOTES) == set(PROVIDERS)


def test_commands_topic_covers_the_cli() -> None:
    text = TOPICS["commands"][1]
    for name in cli.commands:
        if name == "stats":
            assert "alias: stats" in text
            continue
        assert f"lairen {name}" in text


def test_topic_payload_shape() -> None:
    payload = topic_payload("commands")
    assert payload["topic"] == "commands"
    assert payload["title"] == "Commands"
    assert "lairen register" in payload["text"]


def test_all_payload_includes_version_and_every_topic() -> None:
    payload = all_payload()
    assert payload["version"] == __version__
    topics = payload["topics"]
    assert isinstance(topics, list)
    assert [item["topic"] for item in topics] == list(TOPIC_ORDER)


def test_all_text_includes_every_section() -> None:
    text = all_text()
    assert f"version: {__version__}" in text
    for title, _ in TOPICS.values():
        assert title.upper() in text
