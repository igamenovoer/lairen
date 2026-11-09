"""Project status inspection without the CLI."""

from __future__ import annotations

import base64
import json
from pathlib import Path

from lairen.paths import Paths
from lairen.status import inspect_project


def b64(value: dict[str, object]) -> str:
    return (
        base64.urlsafe_b64encode(json.dumps(value).encode("utf-8"))
        .rstrip(b"=")
        .decode("ascii")
    )


def jwt(claims: dict[str, object]) -> str:
    return f"{b64({'alg': 'none'})}.{b64(claims)}.signature"


def write_codex(home: Path, email: str, last_refresh: str = "refresh") -> str:
    home.mkdir(parents=True)
    blob = json.dumps(
        {
            "tokens": {
                "id_token": jwt({"email": email}),
                "access_token": jwt({"exp": 2_000_000_000}),
            },
            "last_refresh": last_refresh,
        }
    )
    (home / "auth.json").write_text(blob, encoding="utf-8")
    return blob


def write_kimi(home: Path) -> Path:
    credentials = home / "credentials"
    credentials.mkdir(parents=True)
    blob = json.dumps(
        {
            "access_token": jwt({"user_id": "user-1", "device_id": "device-1"}),
            "refresh_token": jwt({"user_id": "user-1", "device_id": "device-1"}),
            "expires_at": 2_000_000_000,
            "scope": "kimi-code",
        }
    )
    credential = credentials / "kimi-code.json"
    credential.write_text(blob, encoding="utf-8")
    return credential


def make_paths(tmp_path: Path) -> Paths:
    return Paths(
        config_dir=tmp_path / "config",
        data_dir=tmp_path / "data",
        state_dir=tmp_path / "state",
    )


def test_status_reports_an_empty_provider_home_as_no_login(tmp_path) -> None:
    paths = make_paths(tmp_path)
    project = tmp_path / "project"
    (project / ".codex").mkdir(parents=True)

    report = inspect_project(project, ("codex",), paths)

    assert report.accounts[0].state == "no-login"
    assert report.ok


def test_status_inspects_a_provider_home_passed_as_project(tmp_path) -> None:
    paths = make_paths(tmp_path)
    home = tmp_path / "project" / ".codex"
    write_codex(home, "alice@example.com")

    report = inspect_project(home, ("codex",), paths)

    assert report.accounts[0].home == home.resolve()
    assert report.accounts[0].state == "unregistered"
    assert report.problems


def test_status_inspects_a_kimi_home_with_credentials_at_root(tmp_path) -> None:
    paths = make_paths(tmp_path)
    home = tmp_path / "kimi-homes" / "kimi-2064-1"
    credential = write_kimi(home)

    report = inspect_project(home, ("kimi",), paths)

    assert len(report.accounts) == 1
    item = report.accounts[0]
    assert item.home == home.resolve()
    assert item.credential == credential.resolve()
    assert item.ref == "kimi/user-1--device-1"
    assert item.state == "unregistered"
