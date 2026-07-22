#!/usr/bin/env python3
"""One-shot: move legacy .crawler downloads/snapshots into fn-* asset folders."""

from __future__ import annotations

import shutil
from pathlib import Path

# Repo-root .crawler (same as DOWNLOADS_ROOT), not crawler/.crawler.
ROOT = Path(__file__).resolve().parents[2] / ".crawler"
DOWNLOADS = ROOT / "downloads"
SNAPSHOTS = ROOT / "snapshots"

MOVES: list[tuple[str, list[str]]] = [
    (
        "fn-dc-n20-260723-legacy",
        ["datacenter-limit20"],
    ),
    (
        "fn-ad-260723-blind",
        ["blind-pages"],
    ),
]


def _ensure_dir(path: Path) -> None:
    path.mkdir(parents=True, exist_ok=True)


def _move_path(src: Path, dest_dir: Path) -> None:
    if not src.exists():
        print(f"skip missing {src}")
        return
    dest = dest_dir / src.name
    if dest.exists():
        print(f"skip exists {dest}")
        return
    _ensure_dir(dest_dir)
    shutil.move(str(src), str(dest))
    print(f"mv {src.relative_to(ROOT)} -> {dest.relative_to(ROOT)}")


def _move_glob(pattern: str, dest_dir: Path) -> None:
    for src in sorted(DOWNLOADS.glob(pattern)):
        if src.is_dir():
            continue
        _move_path(src, dest_dir)


def main() -> None:
    if not DOWNLOADS.is_dir():
        raise SystemExit(f"No downloads dir: {DOWNLOADS}")

    for asset_id, names in MOVES:
        dest = DOWNLOADS / asset_id
        for name in names:
            src = DOWNLOADS / name
            if not src.exists():
                print(f"skip missing {src}")
                continue
            _ensure_dir(dest)
            if src.is_dir():
                for child in sorted(src.iterdir()):
                    _move_path(child, dest)
                try:
                    src.rmdir()
                    print(f"rmdir {src.relative_to(ROOT)}")
                except OSError as exc:
                    print(f"rmdir failed {src}: {exc}")
            else:
                _move_path(src, dest)

    legpdf = DOWNLOADS / "fn-ad-260723-legpdf"
    for pattern in ("02-*.pdf", "03-*.pdf", "04-*.pdf"):
        _move_glob(pattern, legpdf)

    view = DOWNLOADS / "fn-ad-260723-view"
    _move_glob("viewer-*.png", view)
    _move_glob("viewer-01-fail.png", view)

    if SNAPSHOTS.is_dir():
        snap = DOWNLOADS / "fn-ad-260722-snap"
        for child in sorted(SNAPSHOTS.iterdir()):
            _move_path(child, snap)
        try:
            SNAPSHOTS.rmdir()
            print(f"rmdir {SNAPSHOTS.relative_to(ROOT)}")
        except OSError as exc:
            print(f"rmdir failed {SNAPSHOTS}: {exc}")

    # Flatten accidental nested dirs from folder moves (datacenter-limit20 contents)
    for asset_id, _ in MOVES:
        nested = DOWNLOADS / asset_id
        if not nested.is_dir():
            continue
        for child in list(nested.iterdir()):
            if child.is_dir() and child.name in {"datacenter-limit20", "blind-pages"}:
                for inner in sorted(child.iterdir()):
                    _move_path(inner, nested)
                try:
                    child.rmdir()
                except OSError:
                    pass

    print("--- downloads root ---")
    for p in sorted(DOWNLOADS.iterdir()):
        kind = "dir" if p.is_dir() else "file"
        print(f"{kind} {p.name}")


if __name__ == "__main__":
    main()
