"use strict";

// --------------------------------------------------------------------------
// Board rendering (Unicode pieces from FEN — no external dependencies)
// --------------------------------------------------------------------------
const PIECES = {
  K: "♔", Q: "♕", R: "♖", B: "♗", N: "♘", P: "♙",
  k: "♚", q: "♛", r: "♜", b: "♝", n: "♞", p: "♟",
};
const START_FEN = "rnbqkbnr/pppppppp/8/8/8/8/PPPPPPPP/RNBQKBNR w KQkq - 0 1";

function renderBoard(fen, highlight) {
  const boardEl = document.getElementById("board");
  boardEl.innerHTML = "";
  const placement = (fen || START_FEN).split(" ")[0];
  const rows = placement.split("/");
  const hlSet = new Set(highlight || []);
  for (let r = 0; r < 8; r++) {
    let file = 0;
    for (const ch of rows[r]) {
      if (/\d/.test(ch)) {
        for (let k = 0; k < parseInt(ch, 10); k++) addSquare(boardEl, r, file++, "", hlSet);
      } else {
        addSquare(boardEl, r, file++, PIECES[ch] || "", hlSet);
      }
    }
  }
  updateMaterial(fen || START_FEN);
}

// Naive material count: P=1, N=3, B=3, R=5, Q=9, K=0.
const PIECE_VALUE = { p: 1, n: 3, b: 3, r: 5, q: 9, k: 0 };

function materialFromFen(fen) {
  const placement = (fen || START_FEN).split(" ")[0];
  let white = 0, black = 0;
  for (const ch of placement) {
    const v = PIECE_VALUE[ch.toLowerCase()];
    if (v === undefined) continue; // digits, "/"
    if (ch === ch.toUpperCase()) white += v; else black += v;
  }
  return { white, black };
}

function updateMaterial(fen) {
  const el = document.getElementById("material");
  if (!el) return;
  const { white, black } = materialFromFen(fen);
  const diff = white - black;
  const adv = diff === 0 ? "even" : (diff > 0 ? `White +${diff}` : `Black +${-diff}`);
  el.textContent = `Material  ·  White ${white}  ·  Black ${black}  ·  ${adv}`;
}

function addSquare(boardEl, rank, file, piece, hlSet) {
  const files = "abcdefgh";
  const sq = document.createElement("div");
  const name = files[file] + (8 - rank); // e.g. e4
  const isLight = (rank + file) % 2 === 0;
  sq.className = "sq " + (isLight ? "light" : "dark") + (hlSet.has(name) ? " hl" : "");
  sq.textContent = piece;

  // Coordinates: rank digits down the left file, file letters along the bottom.
  const contrast = isLight ? "on-light" : "on-dark";
  if (file === 0) sq.appendChild(coordLabel(8 - rank, "rank", contrast));
  if (rank === 7) sq.appendChild(coordLabel(files[file], "file", contrast));

  boardEl.appendChild(sq);
}

function coordLabel(text, kind, contrast) {
  const el = document.createElement("span");
  el.className = `coord ${kind} ${contrast}`;
  el.textContent = text;
  return el;
}

function squaresFromUci(uci) {
  if (!uci || uci.length < 4) return [];
  return [uci.slice(0, 2), uci.slice(2, 4)];
}

// --------------------------------------------------------------------------
// Clocks
// --------------------------------------------------------------------------
function fmtClock(sec) {
  sec = Math.max(0, Math.round(sec));
  const m = Math.floor(sec / 60);
  const s = sec % 60;
  return m + ":" + String(s).padStart(2, "0");
}

// --------------------------------------------------------------------------
// Cost formatting (tokens, money, time)
// --------------------------------------------------------------------------
function fmtUsd(x) {
  if (x === null || x === undefined) return "$?";
  return "$" + (x < 0.01 ? x.toFixed(5) : x.toFixed(4));
}

function moveMeta(m) {
  const parts = [`⏱ ${(m.think_time || 0).toFixed(1)}s`];
  const tok = (m.input_tokens || 0) + (m.output_tokens || 0);
  if (tok > 0) {
    parts.push(`${m.input_tokens}+${m.output_tokens} tok`);
    parts.push(fmtUsd(m.cost_usd));
  }
  if (m.retries > 0) parts.push(`⚠ reconnected ×${m.retries}`);
  return parts.join("  ·  ");
}

function thinkSummary(secs, moves, model) {
  const name = model ? ` (${model})` : "";
  const avg = moves ? `, ${(secs / moves).toFixed(1)}s/move over ${moves}` : "";
  return `${name} ${secs.toFixed(1)}s${avg}`;
}

function setGameThink(g) {
  const el = document.getElementById("game-think");
  if (!el) return;
  const w = (g && g.white_think_sec) || 0;
  const b = (g && g.black_think_sec) || 0;
  if (w + b === 0) { el.textContent = ""; return; }
  el.textContent =
    "Thinking — White" + thinkSummary(w, g.white_moves || 0, g.white_model) +
    "  ·  Black" + thinkSummary(b, g.black_moves || 0, g.black_model);
}

function setGameCost(g) {
  const el = document.getElementById("game-cost");
  const tok = (g && (g.total_input_tokens || 0) + (g.total_output_tokens || 0)) || 0;
  if (!g || tok === 0) { el.textContent = ""; return; }
  el.textContent =
    `Cost — total ${fmtUsd(g.total_cost_usd)} · ${tok.toLocaleString()} tok` +
    `  (White ${fmtUsd(g.white_cost_usd)} · Black ${fmtUsd(g.black_cost_usd)})`;
}

function setClock(color, seconds, active) {
  const el = document.getElementById("clock-" + color);
  el.textContent = fmtClock(seconds);
  el.classList.toggle("active", !!active);
  el.classList.toggle("low", seconds <= 10);
}

// --------------------------------------------------------------------------
// Data source: "api" (backend) or "static" (committed files for GitHub Pages)
// --------------------------------------------------------------------------
const STATIC = (typeof window !== "undefined" && window.CHESS_MODE === "static");

async function fetchGamesList() {
  if (STATIC) return fetch("games/index.json").then((r) => r.json());
  return fetch("/games").then((r) => r.json());
}

async function fetchGame(id) {
  if (STATIC) {
    const d = await fetch(`games/${id}.json`).then((r) => r.json());
    return { live: false, ...d }; // committed report is {game, config, moves}
  }
  return fetch("/games/" + id).then((r) => r.json());
}

// No backend in static mode: hide new-game, live, and prompts panels.
let staticSetupDone = false;
function setupStaticMode() {
  if (!STATIC || staticSetupDone) return;
  staticSetupDone = true;
  ["new-game-form", "system-prompt", "live-table"].forEach((elId) => {
    const el = document.getElementById(elId);
    const panel = el && el.closest(".panel");
    if (panel) panel.hidden = true;
  });
}

// --------------------------------------------------------------------------
// Routing: #  (list) | #live/<id> | #replay/<id>
// --------------------------------------------------------------------------
let ticker = null;
let socket = null;

function stopActivity() {
  if (ticker) { clearInterval(ticker); ticker = null; }
  if (socket) { socket.close(); socket = null; }
  if (autoplay) { clearInterval(autoplay); autoplay = null; }
}

function route() {
  stopActivity();
  const hash = location.hash.slice(1);
  const [mode, id] = hash.split("/");
  const listView = document.getElementById("list-view");
  const gameView = document.getElementById("game-view");
  if (mode === "live" && id) {
    listView.hidden = true; gameView.hidden = false; startLive(id);
  } else if (mode === "replay" && id) {
    listView.hidden = true; gameView.hidden = false; startReplay(id);
  } else {
    listView.hidden = false; gameView.hidden = true;
    setupStaticMode();
    if (!STATIC) { loadProviders(); loadPrompts(); }
    loadLists();
  }
}

// --------------------------------------------------------------------------
// List / lobby
// --------------------------------------------------------------------------
async function loadLists() {
  const data = await fetchGamesList();
  const liveBody = document.querySelector("#live-table tbody");
  const finBody = document.querySelector("#finished-table tbody");
  liveBody.innerHTML = "";
  finBody.innerHTML = "";

  (data.live || []).forEach((g) => {
    const tr = document.createElement("tr");
    tr.innerHTML = `<td>${g.white_model} vs ${g.black_model}</td>
      <td>${g.time_control}</td><td>live</td>
      <td><a class="btn" href="#live/${g.game_id}">Watch</a></td>`;
    liveBody.appendChild(tr);
  });
  document.getElementById("no-live").hidden = (data.live || []).length > 0;

  (data.finished || []).forEach((g) => {
    const tr = document.createElement("tr");
    const wc = parseFloat(g.white_cost_usd) || 0;
    const bc = parseFloat(g.black_cost_usd) || 0;
    const costCell = wc + bc > 0 ? `${fmtUsd(wc)} / ${fmtUsd(bc)}` : "—";
    const wt = parseFloat(g.white_think_sec) || 0;
    const bt = parseFloat(g.black_think_sec) || 0;
    const thinkCell = wt + bt > 0 ? `${wt.toFixed(0)}s / ${bt.toFixed(0)}s` : "—";
    tr.innerHTML = `<td>${g.white_model} vs ${g.black_model}</td>
      <td>${g.time_control}</td><td>${g.result}</td>
      <td>${thinkCell}</td>
      <td>${costCell}</td>
      <td class="muted">${g.why || g.termination}</td>
      <td><a class="btn" href="#replay/${g.game_id}">Replay</a></td>`;
    finBody.appendChild(tr);
  });
  document.getElementById("no-finished").hidden = (data.finished || []).length > 0;
}

// --- prompts panel (what we send the AI) ---
let promptsLoaded = false;
async function loadPrompts() {
  if (promptsLoaded) return;
  const p = await fetch("/prompts").then((r) => r.json());
  document.getElementById("prompts-note").textContent = p.note || "";
  document.getElementById("system-prompt").textContent = p.system_prompt;
  document.getElementById("move-prompt").textContent = p.move_prompt_example;
  promptsLoaded = true;
}

// --- provider/model dropdowns (populated from /providers) ---
let PROVIDERS = [];

async function loadProviders() {
  if (PROVIDERS.length) return;
  const data = await fetch("/providers").then((r) => r.json());
  PROVIDERS = data.providers;
  for (const side of ["w", "b"]) {
    const sel = document.getElementById(side + "-provider");
    sel.innerHTML = PROVIDERS.map(
      (p) => `<option value="${p.key}">${p.label}</option>`
    ).join("");
    sel.addEventListener("change", () => onProviderChange(side));
    onProviderChange(side);
  }
}

function onProviderChange(side) {
  const prov = PROVIDERS.find((p) => p.key === document.getElementById(side + "-provider").value);
  const modelSel = document.getElementById(side + "-model");
  modelSel.innerHTML = (prov.models || [])
    .map((m) => `<option value="${m}">${m}</option>`)
    .join("");
  modelSel.disabled = !(prov.models && prov.models.length);
  if (!modelSel.options.length) modelSel.innerHTML = `<option value="">(random)</option>`;
  document.getElementById(side + "-thinking-wrap").hidden = !prov.supports_thinking;
  document.getElementById(side + "-mock-wrap").hidden = prov.key !== "mock";
}

function sideSpec(side) {
  const provider = document.getElementById(side + "-provider").value;
  const spec = { provider };
  const model = document.getElementById(side + "-model").value;
  if (model) spec.model = model;
  const prov = PROVIDERS.find((p) => p.key === provider);
  if (prov && prov.supports_thinking) spec.thinking = document.getElementById(side + "-thinking").value;
  if (provider === "mock") spec.illegal_prob = parseFloat(document.getElementById(side === "w" ? "wprob" : "bprob").value);
  return spec;
}

document.getElementById("new-game-form").addEventListener("submit", async (e) => {
  e.preventDefault();
  const body = {
    base_seconds: parseInt(document.getElementById("base").value, 10),
    increment_seconds: parseInt(document.getElementById("inc").value, 10),
    white: sideSpec("w"),
    black: sideSpec("b"),
  };
  const res = await fetch("/games", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body),
  }).then((r) => r.json());
  location.hash = "live/" + res.game_id;
});

// --------------------------------------------------------------------------
// Live view (WebSocket)
// --------------------------------------------------------------------------
function startLive(id) {
  document.getElementById("replay-controls").hidden = true;
  document.getElementById("moves").innerHTML = "";
  document.getElementById("game-title").textContent = "Live game";
  document.getElementById("game-status").textContent = "Connecting…";
  document.getElementById("game-reasoning").textContent = "";
  document.getElementById("game-cost").textContent = "";
  document.getElementById("game-think").textContent = "";
  renderBoard(START_FEN, []);

  // `auth` = authoritative clocks from the last server event; the displayed
  // mover clock is `auth[turn] - (real seconds since turnStart)`.
  let auth = { white: null, black: null };
  let turn = "white";
  let running = true;
  let turnStart = performance.now();
  const totals = {
    total_input_tokens: 0, total_output_tokens: 0,
    total_cost_usd: 0, white_cost_usd: 0, black_cost_usd: 0,
    white_think_sec: 0, black_think_sec: 0, white_moves: 0, black_moves: 0,
    white_model: "", black_model: "",
  };

  function paintClocks() {
    if (auth.white == null || auth.black == null) return;
    const elapsed = running ? (performance.now() - turnStart) / 1000 : 0;
    const w = turn === "white" ? Math.max(0, auth.white - elapsed) : auth.white;
    const b = turn === "black" ? Math.max(0, auth.black - elapsed) : auth.black;
    setClock("white", w, running && turn === "white");
    setClock("black", b, running && turn === "black");
  }

  const proto = location.protocol === "https:" ? "wss:" : "ws:";
  socket = new WebSocket(`${proto}//${location.host}/games/${id}/live`);

  socket.onmessage = (ev) => {
    const e = JSON.parse(ev.data);
    if (e.type === "start") {
      auth = e.clocks; turn = "white"; turnStart = performance.now();
      totals.white_model = e.white_model;
      totals.black_model = e.black_model;
      document.getElementById("game-title").textContent =
        `${e.white_model} (W) vs ${e.black_model} (B) · ${e.time_control}`;
      document.getElementById("game-status").textContent = "In progress…";
      renderBoard(e.fen, []);
    } else if (e.type === "move") {
      const m = e.move;
      auth = e.clocks; turn = e.turn; turnStart = performance.now();
      renderBoard(e.fen, squaresFromUci(m.uci));
      appendMove(m);
      document.getElementById("game-reasoning").textContent =
        `${m.color === "white" ? "White" : "Black"}: ${m.reasoning}`;
      totals.total_input_tokens += m.input_tokens || 0;
      totals.total_output_tokens += m.output_tokens || 0;
      totals.total_cost_usd += m.cost_usd || 0;
      totals[m.color + "_cost_usd"] += m.cost_usd || 0;
      totals[m.color + "_think_sec"] += m.think_time || 0;
      totals[m.color + "_moves"] += 1;
      setGameCost(totals);
      setGameThink(totals);
    } else if (e.type === "penalty") {
      auth = e.clocks; turnStart = performance.now();
      appendPenalty(e);
    } else if (e.type === "end") {
      running = false;
      const res = e.result;
      auth = { white: res.white_clock_end, black: res.black_clock_end };
      document.getElementById("game-status").textContent =
        `${res.result} · ${res.termination}`;
      document.getElementById("game-reasoning").textContent = res.why;
      setGameCost(res);
      setGameThink(res);
    } else if (e.type === "error") {
      document.getElementById("game-status").textContent = "Error: " + e.message;
    }
    paintClocks();
  };
  socket.onclose = () => { running = false; };

  // Smooth real-time tick of the side to move between server events.
  ticker = setInterval(paintClocks, 200);
}

// --------------------------------------------------------------------------
// Replay view
// --------------------------------------------------------------------------
let replay = { moves: [], idx: 0, config: null };
let autoplay = null;

async function startReplay(id) {
  document.getElementById("replay-controls").hidden = false;
  document.getElementById("moves").innerHTML = "";
  const data = await fetchGame(id);
  if (data.live) {
    // Not finished yet — fall back to live view.
    location.hash = "live/" + id;
    return;
  }
  replay.moves = data.moves;
  replay.config = data.config;
  replay.idx = 0;
  const g = data.game;
  document.getElementById("game-title").textContent =
    `${g.white_model} (W) vs ${g.black_model} (B) · ${g.time_control}`;
  document.getElementById("game-status").textContent = `${g.result} · ${g.termination}`;
  document.getElementById("game-reasoning").textContent = g.why;
  setGameCost(g);
  setGameThink(g);

  data.moves.forEach((m, i) => appendMove(m, i));
  showFrame(0);
}

function showFrame(idx) {
  replay.idx = Math.max(0, Math.min(idx, replay.moves.length));
  const base = replay.config ? replay.config.base_seconds : 180;
  if (replay.idx === 0) {
    renderBoard(START_FEN, []);
    setClock("white", base, false);
    setClock("black", base, false);
  } else {
    const m = replay.moves[replay.idx - 1];
    renderBoard(m.fen_after, squaresFromUci(m.uci));
    setClock("white", m.white_clock, m.color === "black");
    setClock("black", m.black_clock, m.color === "white");
    document.getElementById("game-reasoning").textContent =
      `${m.color === "white" ? "White" : "Black"}: ${m.reasoning}`;
  }
  highlightMove(replay.idx - 1);
  document.getElementById("ply-indicator").textContent =
    `${replay.idx} / ${replay.moves.length}`;
}

function highlightMove(i) {
  document.querySelectorAll("#moves li").forEach((li, k) => {
    const on = k === i;
    li.classList.toggle("current", on);
    if (on) li.scrollIntoView({ block: "nearest" });
  });
}

document.getElementById("btn-start").onclick = () => showFrame(0);
document.getElementById("btn-prev").onclick = () => showFrame(replay.idx - 1);
document.getElementById("btn-next").onclick = () => showFrame(replay.idx + 1);
document.getElementById("btn-end").onclick = () => showFrame(replay.moves.length);
document.getElementById("btn-play").onclick = (e) => {
  if (autoplay) {
    clearInterval(autoplay); autoplay = null; e.target.textContent = "▶ Auto";
    return;
  }
  e.target.textContent = "⏸ Stop";
  autoplay = setInterval(() => {
    if (replay.idx >= replay.moves.length) {
      clearInterval(autoplay); autoplay = null; e.target.textContent = "▶ Auto";
      return;
    }
    showFrame(replay.idx + 1);
  }, 800);
};

// --------------------------------------------------------------------------
// Move list helpers (shared by live + replay)
// --------------------------------------------------------------------------
function appendMove(m, idx) {
  const ol = document.getElementById("moves");
  const li = document.createElement("li");
  const clk = m.color === "white" ? m.white_clock : m.black_clock;
  const num = Math.floor((m.ply - 1) / 2) + 1;
  const dot = m.color === "white" ? "." : "…";

  const head = document.createElement("div");
  head.className = "move-head";
  head.textContent = `${num}${dot} ${m.san}  ·  ${fmtClock(clk)}` +
    (m.note ? `  (${m.note})` : "");
  li.appendChild(head);

  if (m.reasoning) {
    const why = document.createElement("div");
    why.className = "move-why";
    why.textContent = m.reasoning;
    li.appendChild(why);
  }

  const meta = document.createElement("div");
  meta.className = "move-meta";
  meta.textContent = moveMeta(m);
  li.appendChild(meta);

  // In replay (idx provided) each move jumps the board to that position.
  if (idx !== undefined) {
    li.classList.add("clickable");
    li.title = "Click to view the board at this move";
    li.addEventListener("click", () => showFrame(idx + 1));
  } else {
    // Live: keep the list following the game.
    ol.parentElement.scrollTop = ol.parentElement.scrollHeight;
  }

  ol.appendChild(li);
}

function appendPenalty(e) {
  const ol = document.getElementById("moves");
  const li = document.createElement("li");
  li.className = "penalty";
  li.textContent = `⚠ ${e.color}: ${e.note}`;
  ol.appendChild(li);
  ol.parentElement.scrollTop = ol.parentElement.scrollHeight;
}

// --------------------------------------------------------------------------
window.addEventListener("hashchange", route);
window.addEventListener("load", route);
