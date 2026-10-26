"""Repository layout checks for non-distributed support files."""

from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]


def test_standard_layout_documentation_exists() -> None:
    expected = [
        "README.md",
        "tests/README.md",
        "extern/README.md",
        "extern/tracked/README.md",
        "extern/orphan/README.md",
        "extern/trees/README.md",
        "context/README.md",
        "context/plans/README.md",
        "context/features/README.md",
        "context/design/README.md",
        "context/summaries/README.md",
        "context/archived/README.md",
        "skillset/README.md",
        "docs/README.md",
        ".github/workflows/ci.yml",
    ]
    missing = [path for path in expected if not (ROOT / path).is_file()]
    assert not missing, f"missing layout files: {missing}"
