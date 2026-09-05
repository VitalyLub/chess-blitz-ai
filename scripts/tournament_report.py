"""Build a self-contained HTML one-pager for the tournament (docs/tournament.html).

Reads data/tournament.json (standings + games) and data/reports/*.json (per-move
detail), computes stats, renders charts with matplotlib, and embeds them as
base64 PNGs in a single HTML file (no CDN, works offline, ships on GitHub Pages).

    python scripts/tournament_report.py
"""

from __future__ import annotations

import base64
import glob
import io
import json
from collections import Counter, defaultdict
from datetime import datetime
from pathlib import Path

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402

ROOT = Path(__file__).resolve().parent.parent
DATA = ROOT / "data"
DOCS = ROOT / "docs"
OUT = DOCS / "tournament.html"

BG = "#f7f7f5"
INK = "#23211d"
ACCENT = "#4a7a4a"


def load():
    tj = json.loads((DATA / "tournament.json").read_text())
    reports = {}
    for p in glob.glob(str(DATA / "reports" / "*.json")):
        r = json.loads(Path(p).read_text())
        reports[r["game"]["game_id"]] = r
    return tj, reports


def fig_to_uri(fig) -> str:
    buf = io.BytesIO()
    fig.savefig(buf, format="png", dpi=110, bbox_inches="tight", facecolor="white")
    plt.close(fig)
    return "data:image/png;base64," + base64.b64encode(buf.getvalue()).decode()


def color_map(players):
    cmap = plt.get_cmap("tab10")
    return {p: cmap(i % 10) for i, p in enumerate(players)}


# --------------------------------------------------------------------------- #
# Charts
# --------------------------------------------------------------------------- #
def chart_points(standings, colors):
    players = [s["player"] for s in standings][::-1]
    pts = [s["points"] for s in standings][::-1]
    fig, ax = plt.subplots(figsize=(7, 4))
    ax.barh(players, pts, color=[colors[p] for p in players])
    for i, v in enumerate(pts):
        ax.text(v + 0.2, i, f"{v:g}", va="center", fontsize=9)
    ax.set_xlabel("points"); ax.set_title("Standings — total points")
    ax.margins(x=0.12)
    return fig_to_uri(fig)


def chart_crosstable(players, games):
    n = len(players)
    idx = {p: i for i, p in enumerate(players)}
    mat = [[float("nan")] * n for _ in range(n)]
    score = defaultdict(float)
    for g in games:
        if g.get("termination") == "error":
            continue
        w, b, win = g["white"], g["black"], g.get("winner")
        if win is None:
            score[(w, b)] += 0.5; score[(b, w)] += 0.5
        else:
            score[(win, b if win == w else w)] += 1.0
    for a in players:
        for c in players:
            if a != c:
                mat[idx[a]][idx[c]] = score.get((a, c), 0.0)
    fig, ax = plt.subplots(figsize=(7, 6))
    im = ax.imshow(mat, cmap="RdYlGn", vmin=0, vmax=5)
    ax.set_xticks(range(n)); ax.set_yticks(range(n))
    ax.set_xticklabels(players, rotation=45, ha="right", fontsize=8)
    ax.set_yticklabels(players, fontsize=8)
    for i in range(n):
        for j in range(n):
            if i != j:
                ax.text(j, i, f"{mat[i][j]:g}", ha="center", va="center", fontsize=8)
    ax.set_title("Head-to-head — row player's points vs column (out of 5)")
    fig.colorbar(im, ax=ax, shrink=0.7, label="points / 5")
    return fig_to_uri(fig)


def chart_openings(players, reports, colors):
    # first move as White per player
    openings = defaultdict(Counter)
    for r in reports.values():
        mv = r["moves"]
        if mv:
            openings[r["game"]["white_model"]][mv[0]["san"]] += 1
    all_moves = Counter()
    for c in openings.values():
        all_moves.update(c)
    top = [m for m, _ in all_moves.most_common(6)]
    cats = top + ["other"]
    move_colors = dict(zip(top, plt.get_cmap("Set2").colors))
    move_colors["other"] = "#bbbbbb"

    fig, ax = plt.subplots(figsize=(7, 4))
    ys = list(range(len(players)))
    left = [0.0] * len(players)
    for cat in cats:
        widths = []
        for p in players:
            tot = sum(openings[p].values()) or 1
            cnt = openings[p][cat] if cat != "other" else \
                sum(v for k, v in openings[p].items() if k not in top)
            widths.append(100 * cnt / tot)
        ax.barh(ys, widths, left=left, label=cat, color=move_colors[cat])
        left = [l + w for l, w in zip(left, widths)]
    ax.set_yticks(ys); ax.set_yticklabels(players, fontsize=8)
    ax.set_xlabel("% of games (as White)")
    ax.set_title("Openings — first move as White")
    ax.legend(ncol=len(cats), fontsize=7, loc="upper center", bbox_to_anchor=(0.5, -0.12))
    return fig_to_uri(fig)


def chart_terminations(games):
    c = Counter(g["termination"] for g in games)
    labels = list(c.keys()); vals = [c[k] for k in labels]
    order = sorted(range(len(labels)), key=lambda i: -vals[i])
    labels = [labels[i] for i in order]; vals = [vals[i] for i in order]
    fig, ax = plt.subplots(figsize=(7, 4))
    ax.bar(labels, vals, color=ACCENT)
    for i, v in enumerate(vals):
        ax.text(i, v + 0.5, str(v), ha="center", fontsize=9)
    ax.set_ylabel("games"); ax.set_title("How games were decided")
    plt.setp(ax.get_xticklabels(), rotation=30, ha="right", fontsize=8)
    return fig_to_uri(fig)


def chart_points_by_color(players, games, colors):
    wp = defaultdict(float); bp = defaultdict(float)
    for g in games:
        if g.get("termination") == "error":
            continue
        w, b, win = g["white"], g["black"], g.get("winner")
        if win is None:
            wp[w] += 0.5; bp[b] += 0.5
        elif win == w:
            wp[w] += 1
        else:
            bp[b] += 1
    import numpy as np
    x = np.arange(len(players))
    fig, ax = plt.subplots(figsize=(7, 4))
    ax.bar(x - 0.2, [wp[p] for p in players], 0.4, label="as White", color="#d9b36b")
    ax.bar(x + 0.2, [bp[p] for p in players], 0.4, label="as Black", color="#6b6b6b")
    ax.set_xticks(x); ax.set_xticklabels(players, rotation=45, ha="right", fontsize=8)
    ax.set_ylabel("points"); ax.set_title("Points by color"); ax.legend()
    return fig_to_uri(fig)


def _per_player_move_stats(reports):
    think = defaultdict(float); count = defaultdict(int); cost = defaultdict(float)
    for r in reports.values():
        for m in r["moves"]:
            p = m["mover_model"]
            think[p] += m["think_time"]; count[p] += 1
            cost[p] += (m.get("cost_usd") or 0.0)
    return think, count, cost


def chart_think(players, reports, colors):
    think, count, _ = _per_player_move_stats(reports)
    avg = [think[p] / count[p] if count[p] else 0 for p in players]
    fig, ax = plt.subplots(figsize=(7, 4))
    ax.bar(players, avg, color=[colors[p] for p in players])
    for i, v in enumerate(avg):
        ax.text(i, v + 0.1, f"{v:.1f}s", ha="center", fontsize=8)
    ax.set_ylabel("seconds"); ax.set_title("Avg think time per move")
    plt.setp(ax.get_xticklabels(), rotation=45, ha="right", fontsize=8)
    return fig_to_uri(fig)


def chart_cost(players, reports, colors):
    _, _, cost = _per_player_move_stats(reports)
    vals = [cost[p] for p in players]
    fig, ax = plt.subplots(figsize=(7, 4))
    ax.bar(players, vals, color=[colors[p] for p in players])
    for i, v in enumerate(vals):
        ax.text(i, v, f"${v:.2f}", ha="center", va="bottom", fontsize=8)
    ax.set_ylabel("USD"); ax.set_title("Total API cost per player")
    plt.setp(ax.get_xticklabels(), rotation=45, ha="right", fontsize=8)
    return fig_to_uri(fig)


def chart_lengths(games):
    lengths = [g["total_moves"] for g in games]
    fig, ax = plt.subplots(figsize=(7, 4))
    ax.hist(lengths, bins=20, color=ACCENT, edgecolor="white")
    ax.set_xlabel("plies (half-moves)"); ax.set_ylabel("games")
    ax.set_title("Game length distribution")
    return fig_to_uri(fig)


# --------------------------------------------------------------------------- #
def build_html(tj, reports) -> str:
    standings = tj["standings"]
    games = tj["games"]
    cfg = tj.get("config", {})
    players = [s["player"] for s in standings]
    colors = color_map(players)

    terms = Counter(g["termination"] for g in games)
    checkmates = terms.get("checkmate", 0)
    timeouts = terms.get("timeout", 0)
    forfeits = terms.get("illegal_forfeit", 0)

    rows = "".join(
        f"<tr><td>{i}</td><td>{s['player']}</td><td>{s['points']:g}</td>"
        f"<td>{s['w']}</td><td>{s['d']}</td><td>{s['l']}</td><td>{s['games']}</td></tr>"
        for i, s in enumerate(standings, 1)
    )

    charts = [
        ("Standings", chart_points(standings, colors)),
        ("Head-to-head (crosstable)", chart_crosstable(players, games)),
        ("Openings", chart_openings(players, reports, colors)),
        ("How games were decided", chart_terminations(games)),
        ("Points by color", chart_points_by_color(players, games, colors)),
        ("Avg think time / move", chart_think(players, reports, colors)),
        ("API cost per player", chart_cost(players, reports, colors)),
        ("Game length", chart_lengths(games)),
    ]
    cards = "".join(
        f'<figure><img src="{uri}" alt="{title}"/><figcaption>{title}</figcaption></figure>'
        for title, uri in charts
    )

    return f"""<!DOCTYPE html>
<html lang="en"><head><meta charset="utf-8"/>
<meta name="viewport" content="width=device-width, initial-scale=1"/>
<title>Chess Blitz AI — Tournament report</title>
<style>
  body {{ margin:0; font-family: system-ui,-apple-system,Segoe UI,Roboto,sans-serif;
         color:{INK}; background:{BG}; }}
  main {{ max-width:1000px; margin:0 auto; padding:24px; }}
  h1 {{ margin:0 0 4px; }}
  .sub {{ color:#8a857c; margin:0 0 16px; }}
  .panel {{ background:#fff; border:1px solid #e5e2db; border-radius:10px;
            padding:16px 20px; margin-bottom:20px; }}
  table {{ border-collapse:collapse; width:100%; font-variant-numeric:tabular-nums; }}
  th,td {{ text-align:left; padding:6px 10px; border-bottom:1px solid #eee; }}
  th {{ color:#8a857c; }}
  tr:first-child td {{ font-weight:600; }}
  .grid {{ display:grid; grid-template-columns:repeat(2,1fr); gap:18px; }}
  @media (max-width:720px) {{ .grid {{ grid-template-columns:1fr; }} }}
  figure {{ margin:0; background:#fff; border:1px solid #e5e2db; border-radius:10px; padding:10px; }}
  figure img {{ width:100%; height:auto; display:block; }}
  figcaption {{ text-align:center; color:#8a857c; font-size:13px; padding-top:6px; }}
  a {{ color:{ACCENT}; }}
</style></head><body><main>
  <h1>♞ Chess Blitz AI — Tournament</h1>
  <p class="sub">Round-robin · {len(players)} players · {cfg.get('games_per_pair','?')} games/pair ·
     time control {cfg.get('time_control','?')} · {len(games)} games ·
     generated {datetime.now():%Y-%m-%d}</p>

  <div class="panel">
    <p><b>{checkmates}</b> checkmates · <b>{timeouts}</b> timeouts ·
       <b>{forfeits}</b> illegal forfeits (of {len(games)} games). Most games were
       decided on the clock or by an illegal move rather than over the board —
       so this leaderboard rewards clock management and legal play as much as
       chess strength.</p>
    <table>
      <tr><th>#</th><th>player</th><th>pts</th><th>W</th><th>D</th><th>L</th><th>games</th></tr>
      {rows}
    </table>
  </div>

  <div class="grid">{cards}</div>

  <p class="sub" style="text-align:center;margin-top:20px">
    <a href="index.html">← browse &amp; replay the games</a>
  </p>
</main></body></html>"""


def main():
    DOCS.mkdir(parents=True, exist_ok=True)
    tj, reports = load()
    OUT.write_text(build_html(tj, reports), encoding="utf-8")
    kb = OUT.stat().st_size / 1024
    print(f"Wrote {OUT} ({kb:.0f} KB, {len(reports)} games).")


if __name__ == "__main__":
    main()
