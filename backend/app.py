"""FastAPI application: start games, list them, stream live, replay finished ones.

The blitz engine is synchronous and runs in a worker thread; its events are
bridged to any connected WebSocket clients via per-game asyncio queues. Buffered
events let a client that joins mid-game catch up to the current position.
"""

from __future__ import annotations

import asyncio
import threading
from pathlib import Path
from typing import Optional

from fastapi import FastAPI, HTTPException, WebSocket, WebSocketDisconnect
from fastapi.responses import HTMLResponse, PlainTextResponse
from fastapi.staticfiles import StaticFiles

import chess

from . import storage
from .agents.factory import build_agent
from .game import BlitzGame
from .models import GameConfig, Observation
from .prompts import move_prompt, system_prompt
from .providers import PROVIDERS

FRONTEND_DIR = Path(__file__).resolve().parent.parent / "frontend"

app = FastAPI(title="Chess Blitz AI")


class GameSession:
    """Live state + event fan-out for one running game."""

    def __init__(self, game_id: str, config: GameConfig, loop: asyncio.AbstractEventLoop):
        self.game_id = game_id
        self.config = config
        self.loop = loop
        self.events: list[dict] = []  # buffered history for late joiners
        self.subscribers: set[asyncio.Queue] = set()
        self.status = "running"  # running | finished
        self.result: Optional[dict] = None

    def on_event(self, event: dict) -> None:
        """Called from the worker thread; bridges to the async world."""
        self.loop.call_soon_threadsafe(self._dispatch, event)

    def _dispatch(self, event: dict) -> None:
        self.events.append(event)
        if event.get("type") == "end":
            self.status = "finished"
            self.result = event.get("result")
        for q in list(self.subscribers):
            q.put_nowait(event)


SESSIONS: dict[str, GameSession] = {}


def _run_game(session: GameSession) -> None:
    config = session.config
    white = build_agent(config.white, "white")
    black = build_agent(config.black, "black")
    game = BlitzGame(
        config,
        white,
        black,
        game_id=session.game_id,
        on_event=session.on_event,
        realtime=True,  # pace moves so the live view is watchable
    )
    try:
        game.run()
    except Exception as exc:  # surface engine errors to the live view
        session.on_event({"type": "error", "message": str(exc)})


def _side_label(spec) -> str:
    """Readable 'provider/model' (or agent name) for the games list."""
    if spec.name:
        return spec.name
    if spec.provider == "mock":
        return "mock"
    return spec.model or spec.provider


@app.get("/providers")
async def list_providers() -> dict:
    """Providers + their selectable models, for the new-game dropdowns."""
    return {
        "providers": [
            {
                "key": p.key,
                "label": p.label,
                "models": p.models,
                "default_model": p.default_model,
                "supports_thinking": p.supports_thinking,
            }
            for p in PROVIDERS.values()
        ]
    }


@app.get("/prompts")
async def get_prompts() -> dict:
    """The exact prompts sent to the AI: the system prompt and a per-turn
    example built from the starting position (so the format is concrete)."""
    board = chess.Board()
    obs = Observation(
        color="white",
        fen=board.fen(),
        move_history_san=[],
        legal_moves_uci=[m.uci() for m in board.legal_moves],
        fullmove_number=1,
        your_clock=180.0,
        opponent_clock=180.0,
        increment=2,
    )
    return {
        "system_prompt": system_prompt("<your color>"),
        "move_prompt_example": move_prompt(obs),
        "note": (
            "Each player gets the same prompts with their own color filled in "
            "(white or black). The per-turn example shows White to move from the "
            "starting position; Black receives the equivalent with 'as black'."
        ),
    }


@app.post("/games")
async def create_game(config: GameConfig) -> dict:
    """Start a new game in the background; returns its id."""
    import uuid

    game_id = uuid.uuid4().hex[:12]
    loop = asyncio.get_running_loop()
    session = GameSession(game_id, config, loop)
    SESSIONS[game_id] = session
    threading.Thread(target=_run_game, args=(session,), daemon=True).start()
    return {"game_id": game_id, "time_control": config.time_control_str}


@app.get("/games")
async def list_games() -> dict:
    """Live (in-memory) + finished (from CSV) games."""
    live = [
        {
            "game_id": s.game_id,
            "status": s.status,
            "white_model": _side_label(s.config.white),
            "black_model": _side_label(s.config.black),
            "time_control": s.config.time_control_str,
            "result": (s.result or {}).get("result", "*"),
            "why": (s.result or {}).get("why", ""),
        }
        for s in SESSIONS.values()
        if s.status == "running"
    ]
    finished = storage.list_games()
    return {"live": live, "finished": finished}


@app.get("/games/{game_id}")
async def get_game(game_id: str) -> dict:
    """Full record for replay (from the saved report)."""
    report = storage.load_report(game_id)
    if report is None:
        session = SESSIONS.get(game_id)
        if session is not None:
            return {"live": True, "status": session.status, "events": session.events}
        raise HTTPException(status_code=404, detail="game not found")
    return {"live": False, **report}


@app.get("/games/{game_id}/pgn", response_class=PlainTextResponse)
async def get_pgn(game_id: str) -> str:
    pgn = storage.load_pgn(game_id)
    if pgn is None:
        raise HTTPException(status_code=404, detail="pgn not found")
    return pgn


@app.websocket("/games/{game_id}/live")
async def live(websocket: WebSocket, game_id: str) -> None:
    await websocket.accept()
    session = SESSIONS.get(game_id)
    if session is None:
        await websocket.send_json({"type": "error", "message": "unknown game"})
        await websocket.close()
        return

    queue: asyncio.Queue = asyncio.Queue()
    # Replay buffered events so a mid-game joiner is caught up, then subscribe.
    for event in list(session.events):
        await websocket.send_json(event)
    finished = session.status == "finished"
    session.subscribers.add(queue)
    try:
        while not finished:
            event = await queue.get()
            await websocket.send_json(event)
            if event.get("type") == "end":
                finished = True
    except WebSocketDisconnect:
        pass
    finally:
        session.subscribers.discard(queue)


# Serve the frontend (index.html at "/").
if FRONTEND_DIR.exists():
    app.mount("/", StaticFiles(directory=str(FRONTEND_DIR), html=True), name="frontend")
else:  # pragma: no cover
    @app.get("/", response_class=HTMLResponse)
    async def _root() -> str:
        return "<h1>Chess Blitz AI</h1><p>frontend/ not found</p>"
