from pathlib import Path

import pytest

from email_triage.config import Config, load_config

REPO_CONFIG = Path(__file__).resolve().parents[1] / "config.toml"


def write(tmp_path: Path, body: str) -> Path:
    path = tmp_path / "config.toml"
    path.write_text(body)
    return path


def test_loads_repo_config():
    config = load_config(REPO_CONFIG)
    assert config.category_names == [
        "Urgent",
        "Needs-Reply",
        "FYI",
        "Jobs",
        "Newsletter",
        "Promotions",
        "Receipts-Notifications",
    ]
    assert config.label_for("FYI") == "Triage/FYI"


def test_defaults_applied(tmp_path):
    path = write(
        tmp_path,
        """
[[categories]]
name = "A"
description = "a"
""",
    )
    config = load_config(path)
    assert config.label_prefix == "Triage"
    assert config.lookback_days == 2
    assert config.max_per_run == 50


def test_rejects_duplicate_categories():
    with pytest.raises(ValueError, match="Duplicate"):
        Config(
            categories=[
                {"name": "A", "description": "x"},
                {"name": "A", "description": "y"},
            ]
        )


def test_rejects_empty_categories():
    with pytest.raises(ValueError):
        Config(categories=[])


def test_rejects_category_names_with_spaces():
    # Spaces would break the unquoted Gmail search query.
    with pytest.raises(ValueError):
        Config(categories=[{"name": "Needs Reply", "description": "x"}])
