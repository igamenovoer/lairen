"""CLI behavior of the agent-oriented manual."""

from __future__ import annotations

import json

from click.testing import CliRunner

from lairen.cli import cli
from lairen.manual import TOPIC_ORDER


def test_manual_default_prints_overview() -> None:
    result = CliRunner().invoke(cli, ["manual"])
    assert result.exit_code == 0, result.output
    assert "CORE COMMANDS" in result.output
    assert "lairen manual all" in result.output


def test_manual_topics_are_available() -> None:
    runner = CliRunner()
    for slug in TOPIC_ORDER:
        result = runner.invoke(cli, ["manual", slug])
        assert result.exit_code == 0, (slug, result.output)
        assert "lairen " in result.output


def test_manual_all_is_complete() -> None:
    result = CliRunner().invoke(cli, ["manual", "all"])
    assert result.exit_code == 0, result.output
    for slug in TOPIC_ORDER:
        assert slug.upper() in result.output


def test_manual_all_json() -> None:
    result = CliRunner().invoke(cli, ["manual", "all", "--json"])
    assert result.exit_code == 0, result.output
    payload = json.loads(result.output)
    assert payload["version"]
    assert [item["topic"] for item in payload["topics"]] == list(TOPIC_ORDER)


def test_manual_topic_json() -> None:
    result = CliRunner().invoke(cli, ["manual", "providers", "--json"])
    assert result.exit_code == 0, result.output
    payload = json.loads(result.output)
    assert payload["topic"] == "providers"
    assert payload["title"] == "Providers"
    assert "codex" in payload["text"]


def test_manual_unknown_topic_fails() -> None:
    result = CliRunner().invoke(cli, ["manual", "nope"])
    assert result.exit_code == 2
