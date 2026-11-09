"""Association and availability behavior derived from the deployment ledger."""

from __future__ import annotations

from pathlib import Path

from lairen.associations import available_accounts, build_associations
from lairen.deployments import DeploymentLog
from lairen.models import Account


def account(
    provider: str,
    account_id: str,
    *,
    alias: str | None = None,
    last_home: str | None = None,
    last_at: str | None = None,
) -> Account:
    return Account(
        provider=provider,
        id=account_id,
        label=account_id,
        source_home=f"/source/{account_id}",
        alias=alias,
        last_deployed_at=last_at,
        last_deployed_home=last_home,
    )


def deploy(
    log: DeploymentLog,
    stamp: str,
    ref: str,
    home: Path,
    *,
    project: Path | None = None,
    alias: str | None = None,
) -> None:
    provider = ref.partition("/")[0]
    entry: dict[str, object] = {
        "ts": stamp,
        "action": "deploy",
        "provider": provider,
        "ref": ref,
        "home": str(home),
    }
    if project is not None:
        entry["project"] = str(project)
    if alias is not None:
        entry["alias"] = alias
    log.append(entry)


def test_newest_deploy_per_home_wins(tmp_path) -> None:
    log = DeploymentLog(tmp_path / "deployments.jsonl")
    home = tmp_path / "project" / ".codex"
    project = tmp_path / "project"
    deploy(
        log,
        "2026-11-01T00:00:00+00:00",
        "codex/alice@example.com",
        home,
        project=project,
    )
    deploy(
        log,
        "2026-11-02T00:00:00+00:00",
        "codex/bob@example.com",
        home,
        project=project,
    )
    accounts = [
        account("codex", "alice@example.com"),
        account("codex", "bob@example.com"),
    ]

    associations = build_associations(accounts, log)
    by_ref = {item.ref: item for item in associations}

    assert by_ref["codex/alice@example.com"].state == "overwritten"
    assert by_ref["codex/bob@example.com"].state == "active"
    assert by_ref["codex/bob@example.com"].project == str(project.resolve())

    available = available_accounts(accounts, associations)
    assert [item.account.ref for item in available] == ["codex/alice@example.com"]
    assert available[0].last_assignment is not None
    assert available[0].last_assignment.state == "overwritten"


def test_multiple_homes_and_providers_per_project(tmp_path) -> None:
    log = DeploymentLog(tmp_path / "deployments.jsonl")
    project = tmp_path / "project"
    deploy(
        log,
        "2026-11-01T00:00:00+00:00",
        "kimi/user-1--device-1",
        project / ".kimi-code",
        project=project,
    )
    deploy(
        log,
        "2026-11-01T01:00:00+00:00",
        "kimi/user-1--device-2",
        project / ".kimi-code-2",
        project=project,
    )
    deploy(
        log,
        "2026-11-01T02:00:00+00:00",
        "codex/alice@example.com",
        project / ".codex",
        project=project,
    )
    accounts = [
        account("kimi", "user-1--device-1"),
        account("kimi", "user-1--device-2"),
        account("codex", "alice@example.com"),
    ]

    associations = build_associations(accounts, log)

    assert {item.state for item in associations} == {"active"}
    assert {item.project for item in associations} == {str(project.resolve())}
    assert {item.home for item in associations} == {
        str((project / ".codex").resolve()),
        str((project / ".kimi-code").resolve()),
        str((project / ".kimi-code-2").resolve()),
    }
    assert available_accounts(accounts, associations) == []


def test_update_chain_attributes_old_deployments_to_current_account(tmp_path) -> None:
    log = DeploymentLog(tmp_path / "deployments.jsonl")
    project = tmp_path / "project"
    home = project / ".kimi-code"
    deploy(
        log,
        "2026-11-01T00:00:00+00:00",
        "kimi/user-1--old-device",
        home,
        project=project,
    )
    log.append(
        {
            "ts": "2026-11-02T00:00:00+00:00",
            "action": "update",
            "provider": "kimi",
            "ref": "kimi/user-1--new-device",
            "previous_ref": "kimi/user-1--old-device",
            "source_home": str(home),
        }
    )
    accounts = [account("kimi", "user-1--new-device")]

    associations = build_associations(accounts, log)

    assert len(associations) == 1
    assert associations[0].ref == "kimi/user-1--new-device"
    assert associations[0].state == "overwritten"


def test_custom_home_name_uses_the_recorded_project(tmp_path) -> None:
    log = DeploymentLog(tmp_path / "deployments.jsonl")
    project = tmp_path / "project"
    home = project / ".kimi-code-worker-a"
    deploy(
        log,
        "2026-11-01T00:00:00+00:00",
        "kimi/user-1--device-1",
        home,
        project=project,
    )
    accounts = [account("kimi", "user-1--device-1")]

    associations = build_associations(accounts, log)

    assert associations[0].project == str(project.resolve())
    assert associations[0].home == str(home.resolve())
    assert associations[0].state == "active"


def test_identity_rebind_invalidates_previous_deployments(tmp_path) -> None:
    log = DeploymentLog(tmp_path / "deployments.jsonl")
    project = tmp_path / "project"
    home = project / ".kimi-code"
    deploy(
        log,
        "2026-11-01T00:00:00+00:00",
        "kimi/user-1--old-device",
        home,
        project=project,
    )
    log.append(
        {
            "ts": "2026-11-02T00:00:00+00:00",
            "action": "update",
            "provider": "kimi",
            "ref": "kimi/user-1--new-device",
            "previous_ref": "kimi/user-1--old-device",
            "source_home": "/kimi-homes/new",
        }
    )
    accounts = [account("kimi", "user-1--new-device")]

    associations = build_associations(accounts, log)

    assert len(associations) == 1
    assert associations[0].state == "overwritten"
    assert [
        item.account.ref for item in available_accounts(accounts, associations)
    ] == ["kimi/user-1--new-device"]

    deploy(
        log,
        "2026-11-03T00:00:00+00:00",
        "kimi/user-1--new-device",
        home,
        project=project,
    )
    associations = build_associations(accounts, log)

    assert len(associations) == 1
    assert associations[0].state == "active"
    assert available_accounts(accounts, associations) == []


def test_account_with_one_active_home_is_not_available(tmp_path) -> None:
    log = DeploymentLog(tmp_path / "deployments.jsonl")
    project = tmp_path / "project"
    deploy(
        log,
        "2026-11-01T00:00:00+00:00",
        "kimi/user-1--device-1",
        project / ".kimi-code",
        project=project,
    )
    deploy(
        log,
        "2026-11-01T01:00:00+00:00",
        "kimi/user-1--device-2",
        project / ".kimi-code-2",
        project=project,
    )
    deploy(
        log,
        "2026-11-01T02:00:00+00:00",
        "kimi/user-2--device-3",
        project / ".kimi-code-2",
        project=project,
    )
    accounts = [
        account("kimi", "user-1--device-1"),
        account("kimi", "user-1--device-2"),
        account("kimi", "user-2--device-3"),
    ]

    associations = build_associations(accounts, log)
    available = available_accounts(accounts, associations)

    assert [item.account.ref for item in available] == [
        "kimi/user-1--device-2"
    ]
