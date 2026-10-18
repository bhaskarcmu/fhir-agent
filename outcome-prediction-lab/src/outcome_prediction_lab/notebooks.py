"""Notebook hygiene (decisions.md O38): notebooks may be committed only with outputs stripped.

Outputs are hard to review and can carry data into git, so a committed notebook must have no cell
outputs and no execution counts. CI runs `outcome-prediction-lab notebooks-check`.
"""
from __future__ import annotations

import json
from pathlib import Path

NOTEBOOKS = Path(__file__).resolve().parents[2] / "notebooks"


def problems(path: Path) -> list[str]:
    try:
        nb = json.loads(path.read_text())
    except json.JSONDecodeError as exc:
        return [f"{path}: not valid notebook JSON ({exc.msg})"]
    found = []
    for i, cell in enumerate(nb.get("cells", [])):
        if cell.get("cell_type") != "code":
            continue
        if cell.get("outputs"):
            found.append(f"{path}: cell {i} has {len(cell['outputs'])} output(s)")
        if cell.get("execution_count") is not None:
            found.append(f"{path}: cell {i} has execution_count {cell['execution_count']}")
    return found


def check(root: Path = NOTEBOOKS) -> list[str]:
    return [p for nb in sorted(root.rglob("*.ipynb")) if ".ipynb_checkpoints" not in nb.parts
            for p in problems(nb)]


def strip(path: Path) -> None:
    """Remove outputs and execution counts in place (what to run before committing)."""
    nb = json.loads(path.read_text())
    for cell in nb.get("cells", []):
        if cell.get("cell_type") == "code":
            cell["outputs"], cell["execution_count"] = [], None
    path.write_text(json.dumps(nb, indent=1) + "\n")
