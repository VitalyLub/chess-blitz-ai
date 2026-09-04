// Runtime mode.
// - "api":    served by the FastAPI backend (live games + replay + new game).
// - "static": the GitHub Pages build (docs/config.js) overrides this to read
//             committed game files — replay only, no backend.
window.CHESS_MODE = "api";
