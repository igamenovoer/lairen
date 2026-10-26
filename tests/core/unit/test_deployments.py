"""Deployment log behavior and project-root derivation."""

from __future__ import annotations

import os
import stat

from lairen.deployments import DeploymentLog, project_root_for_home


def test_project_root_for_provider_homes() -> None:
    assert project_root_for_home("/home/me/project/.codex") == "/home/me/project"
    assert project_root_for_home("/home/me/project/.kimi-code") == "/home/me/project"
    assert project_root_for_home("/home/me/project/.claude") == "/home/me/project"
    assert project_root_for_home("/home/me/.kimi-code") == "/home/me"
    assert project_root_for_home("/home/me/project/custom-home") is None


def test_deployment_log_append_and_read(tmp_path) -> None:
    log = DeploymentLog(tmp_path / "state" / "deployments.jsonl")
    log.append(
        {
            "ts": "2026-10-26T12:00:00+00:00",
            "action": "deploy",
            "ref": "codex/alice@example.com",
            "home": "/home/me/project/.codex",
        }
    )

    entries = log.entries()
    assert len(entries) == 1
    assert entries[0]["ref"] == "codex/alice@example.com"
    if os.name == "posix":
        mode = stat.S_IMODE(log.path.stat().st_mode)
        assert mode == 0o600


def test_deployment_log_skips_malformed_lines(tmp_path) -> None:
    path = tmp_path / "deployments.jsonl"
    path.write_text(
        '{"action": "deploy", "ref": "codex/a", "home": "/p/.codex"}\n'
        "not json\n"
        "[]\n"
        '{"action": "update", "ref": "codex/b"}\n',
        encoding="utf-8",
    )
    log = DeploymentLog(path)

    assert [entry["ref"] for entry in log.entries()] == ["codex/a", "codex/b"]


def test_leases_for_keeps_newest_entry_per_home(tmp_path) -> None:
    log = DeploymentLog(tmp_path / "deployments.jsonl")
    for ts, alias in (
        ("2026-10-24T00:00:00+00:00", "old"),
        ("2026-10-26T00:00:00+00:00", "new"),
    ):
        log.append(
            {
                "ts": ts,
                "action": "deploy",
                "ref": "codex/alice@example.com",
                "alias": alias,
                "home": "/home/me/project/.codex",
            }
        )
    log.append(
        {
            "ts": "2026-10-26T01:00:00+00:00",
            "action": "deploy",
            "ref": "codex/other@example.com",
            "home": "/home/me/other/.codex",
        }
    )

    leases = log.leases_for(["codex/alice@example.com"])
    assert len(leases) == 1
    assert leases[0]["alias"] == "new"


def test_related_refs_follows_update_chain(tmp_path) -> None:
    log = DeploymentLog(tmp_path / "deployments.jsonl")
    log.append(
        {
            "action": "update",
            "ref": "codex/mid@example.com",
            "previous_ref": "codex/old@example.com",
        }
    )
    log.append(
        {
            "action": "update",
            "ref": "codex/new@example.com",
            "previous_ref": "codex/mid@example.com",
        }
    )

    assert log.related_refs("codex/new@example.com") == {
        "codex/new@example.com",
        "codex/mid@example.com",
        "codex/old@example.com",
    }
