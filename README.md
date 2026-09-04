# Chess Blitz AI

A framework where two AI agents play **blitz chess** against each other over API
calls. The backend runs the game, manages the clocks, enforces the rules, saves
every game, and produces a per-move and per-game report ("which model won and
why"). The frontend lets you watch games **live** or **replay** finished games
move by move, with clocks.

All pure-chess logic (legality, SAN/UCI, PGN, draw detection) is handled by the
[`python-chess`](https://python-chess.readthedocs.io/) package.

## Live replay (GitHub Pages)

Browse and step through committed games in your browser — no server needed:
**https://vitalylub.github.io/chess-blitz-ai/**

GitHub can't run the backend, so **live-watching and starting new games require
running the app locally** (below); the Pages site is replay-only. To publish new
games: play them, then rebuild and commit the static site:

```bash
python scripts/export_static.py   # rebuilds docs/ from data/ (games + reports)
git add docs && git commit -m "Add games" && git push
```

## Features

- **Mock agents** out of the box (random legal moves) so the whole pipeline works
  with no LLM or API key.
- **Real AI agents** for three providers behind one interface:
  **DeepSeek** & **OpenAI GPT** (OpenAI-compatible) and **Anthropic Claude**
  (official SDK). Each provider exposes a selectable list of its models — edit
  them in one place, `backend/providers.py`.
- **Per-game configurable time control** — default **3+2** (3 minutes base, +2s
  per move). Any base/increment is accepted.
- **Illegal-move rule:** a player's 1st illegal move gives the opponent +60s and
  the agent is re-prompted to try again; a 2nd illegal move forfeits the game.
- **Known storage formats:** games index in `data/games.csv`, moves + clock times
  in standard PGN (`data/pgn/<id>.pgn`, with `[%clk]` annotations), and full
  per-move + per-game reports in `data/reports/<id>.json`.

## Setup

```bash
source .venv/bin/activate        # existing project venv
pip install -r requirements.txt
```

For real agents, put your keys in a git-ignored `.env` at the project root (copy
`.env.example`). They load automatically no matter how you launch — terminal,
`uvicorn --reload`, or PyCharm. Real shell `export`s still take precedence.

```
OPENAI_API_KEY=sk-proj-...
DEEPSEEK_API_KEY=sk-...
ANTHROPIC_API_KEY=sk-ant-api03-...
```

## Generate mock games (headless)

```bash
python -m backend.runner --white mock --black mock --games 3          # default 3+2 (180+2)
python -m backend.runner --tc 180+5 --games 1                         # other time control
python -m backend.runner --games 5 --illegal-prob 0.15                # exercise penalties
```

Each game writes a CSV row, a `.pgn`, and a `.json` report under `data/`.

## Run the server (live view + replay)

```bash
uvicorn backend.app:app --reload
# open http://127.0.0.1:8000/
```

- **New game:** start a mock game from the lobby; you're taken to the live view.
- **Live:** board, both clocks (side to move ticks down), last move + the agent's
  reasoning, running move list — streamed over WebSocket.
- **Replay:** open a finished game and step through it move by move (or autoplay),
  with the clocks as they were recorded.

## Real AI agents

Keys are read from environment variables (never hardcoded):

| Provider | Env var | Default model | Notes |
|----------|---------|---------------|-------|
| `deepseek` | `DEEPSEEK_API_KEY` | `deepseek-v4-flash` | OpenAI-compatible (`https://api.deepseek.com`) |
| `gpt` | `OPENAI_API_KEY` | `gpt-4o` | OpenAI |
| `claude` | `ANTHROPIC_API_KEY` | `claude-opus-4-8` | Anthropic SDK; `--white-thinking fast\|adaptive` |

Provider/model lists live in `backend/providers.py` — edit that file to add or
remove models; they show up automatically in the CLI and the frontend dropdowns.

```bash
# Claude (fast) vs DeepSeek
python -m backend.runner --white claude --white-model claude-opus-4-8 \
                         --black deepseek --black-model deepseek-v4-flash --games 1

# Claude with adaptive thinking (spends more of its clock) vs GPT
python -m backend.runner --white claude --white-thinking adaptive \
                         --black gpt --black-model gpt-4o --games 1
```

**Claude thinking modes:** `fast` (default) uses no extended thinking — lowest
latency, fair for a blitz clock. `adaptive` lets Claude think at high effort for
stronger moves, but each move eats more wall-clock time (more of its clock).

The prompts (see `backend/prompts.py`) describe the situation (FEN + move history),
send both clocks, list the legal moves, and require a compact JSON reply
`{"move": "<uci>", "reasoning": "..."}`. Claude uses a structured-output schema to
guarantee that shape; OpenAI/DeepSeek use JSON response mode.

In the web UI, the **New game** form has per-side provider + model dropdowns (plus
the Claude thinking toggle), so you can pit any two models against each other live.

## Layout

```
backend/   game engine, clocks, agents, prompts, storage, FastAPI app, runner CLI
frontend/  static HTML/JS/CSS (self-rendered board, live WS view, replay)
data/      games.csv + pgn/ + reports/   (created on first run)
```

## API

| Method | Path                     | Purpose                          |
|--------|--------------------------|----------------------------------|
| GET    | `/providers`             | providers + selectable models    |
| POST   | `/games`                 | start a game (`GameConfig` body) |
| GET    | `/games`                 | list live + finished games       |
| GET    | `/games/{id}`            | full report (for replay)         |
| GET    | `/games/{id}/pgn`        | raw PGN                          |
| WS     | `/games/{id}/live`       | live move/clock event stream     |
