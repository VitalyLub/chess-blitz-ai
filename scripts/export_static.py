"""Build a static GitHub Pages site (docs/) from the frontend + saved games.

Produces a server-less **replay** site: the same UI, but reading committed game
files instead of the backend API. Live-watching and starting new games are
disabled (they need the running backend). Run this whenever you want to publish
new games, then commit docs/.

    python scripts/export_static.py

GitHub Pages: repo Settings → Pages → Source = "main" branch, "/docs" folder.
"""

from __future__ import annotations

import csv
import json
import shutil
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
FRONTEND = ROOT / "frontend"
DATA = ROOT / "data"
DOCS = ROOT / "docs"

STATIC_CONFIG = (
    "// GitHub Pages build — read committed game files, no backend.\n"
    'window.CHESS_MODE = "static";\n'
)


def main() -> None:
    games_csv = DATA / "games.csv"
    reports_dir = DATA / "reports"
    if not games_csv.exists():
        raise SystemExit(f"No games found at {games_csv}. Play some games first.")

    (DOCS / "games").mkdir(parents=True, exist_ok=True)

    # 1. Copy the UI (identical files) + a static-mode config override.
    for name in ("index.html", "app.js", "style.css"):
        shutil.copyfile(FRONTEND / name, DOCS / name)
    (DOCS / "config.js").write_text(STATIC_CONFIG, encoding="utf-8")
    (DOCS / ".nojekyll").write_text("", encoding="utf-8")  # serve files as-is

    # 2. Games index (newest first) — same shape the lobby's finished table reads.
    with games_csv.open(newline="", encoding="utf-8") as fh:
        rows = list(csv.DictReader(fh))
    rows.reverse()
    (DOCS / "games" / "index.json").write_text(
        json.dumps({"live": [], "finished": rows}, indent=2), encoding="utf-8"
    )

    # 3. Per-game reports (the replay reads these directly).
    exported = 0
    for row in rows:
        gid = row["game_id"]
        report = reports_dir / f"{gid}.json"
        if report.exists():
            shutil.copyfile(report, DOCS / "games" / f"{gid}.json")
            exported += 1

    print(f"Exported {exported} game(s) to {DOCS} (index + {exported} report files).")
    print("Commit docs/ and enable GitHub Pages (main branch, /docs folder).")


if __name__ == "__main__":
    main()
