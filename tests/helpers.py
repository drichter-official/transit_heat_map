from __future__ import annotations

from pathlib import Path


def write_table(path: Path, name: str, header: list[str], rows: list[list[object]]) -> None:
    lines = [",".join(header)]
    for row in rows:
        lines.append(",".join(str(value) for value in row))
    path.joinpath(name).write_text("\n".join(lines) + "\n", encoding="utf-8")
