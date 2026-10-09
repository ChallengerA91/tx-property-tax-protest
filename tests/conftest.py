"""Shared fixtures: the fictional sample cases and helpers to build a package from a case dict."""
from __future__ import annotations

import copy
import json
from pathlib import Path
from typing import Any, Dict

import pytest

REPO = Path(__file__).resolve().parent.parent
EXAMPLES = REPO / "examples"
SCRIPTS = REPO / "skills" / "tx-property-tax-protest" / "scripts"


def read_json(path: Path) -> Dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


@pytest.fixture()
def homestead_case() -> Dict[str, Any]:
    return read_json(EXAMPLES / "sample-case.json")


@pytest.fixture()
def rental_case() -> Dict[str, Any]:
    return read_json(EXAMPLES / "sample-case-rental.json")


@pytest.fixture()
def write_case(tmp_path):
    """Write a case dict to a temp case.json and return its path."""
    def _write(data: Dict[str, Any], name: str = "case.json") -> Path:
        path = tmp_path / name
        path.write_text(json.dumps(copy.deepcopy(data)), encoding="utf-8")
        return path
    return _write


@pytest.fixture()
def capped_case() -> Dict[str, Any]:
    """Market value $520,000, capped appraised value $462,000, argued $470,000 (between the two)."""
    return read_json(EXAMPLES / "sample-case-capped.json")
