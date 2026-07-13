# Chavruta.AI — Frontend

The chat UI for Chavruta.AI: a three-column "beit midrash" layout (sessions · conversation ·
related sources) that talks to the FastAPI backend in [`app/api.py`](../api.py). Citations are
clickable and resolve to the source text inline. Full **Hebrew (RTL) / English (LTR)** i18n.

## ⭐ The live UI is the static page — `public/ui/chavruta.html`

The app you actually run is **[`public/ui/chavruta.html`](public/ui/chavruta.html)** — a single,
self-contained, **fully offline** page (hand-crafted Tailwind design + vanilla-JS state, i18n, the
sources "stack", the lesson downloads, chavruta mode, settings/theme). It is served by Vite from
`public/` at **`http://localhost:5173/ui/chavruta.html`** (the site root redirects there).

Why a static page and not the React SPA: the earlier React version's styling didn't match the design;
this page is the approved look and is the one maintained. **The `src/` React SPA is DEPRECATED** and
no longer served (kept only for reference).

### Offline assets (no CDN)

Everything is local — the page works with no internet:

- **Tailwind** is pre-built (not the play CDN). Source of truth: `public/ui/tailwind.config.cjs` +
  `public/ui/tw-input.css` → `public/ui/assets/chavruta.tw.css`. **After adding/removing Tailwind
  classes in the HTML, rebuild:**
  ```bash
  cd app/frontend/public/ui
  npx tailwindcss@3 -c tailwind.config.cjs -i tw-input.css -o assets/chavruta.tw.css --minify
  ```
  (v3 CLI on purpose — it matches the config the page was designed against.)
- **Fonts** (Frank Ruhl Libre · Heebo · Material Symbols) are self-hosted woff2 in
  `public/ui/assets/fonts/`, wired by `public/ui/assets/fonts.local.css`. Regenerate with
  `scripts`-style tooling only if the font set changes.

### Editing the UI

- All user-facing strings live in the JS `STRINGS`/`INTENT_LABEL` tables inside the HTML — add both a
  `he` and an `en` form; nothing hardcoded inline.
- `state` + `render()` drive the DOM (no framework). The API base is `/api` (Vite proxies it to the
  backend on :8080).
- The custom look (glass panels, gradients, dark theme) is in the inline `<style>` block; Tailwind
  utilities handle the rest.

## Commands

```bash
npm install      # dependencies (only needed for the deprecated React SPA / tooling)
npm run dev      # Vite dev server → open http://localhost:5173/ui/chavruta.html
```

The dev server expects the backend on port 8080 — cloud LLM
([`scripts/serve.ps1`](../../scripts/serve.ps1)) or **bridge** mode, no external API
([`scripts/serve_bridge.ps1`](../../scripts/serve_bridge.ps1)).

---

### Deprecated: the React SPA (`src/`)

`src/` (React + TypeScript + Vite, `main.tsx` → `<App/>`, components, `i18n.tsx`) is the earlier UI.
It is **not served** (the root `index.html` redirects to the static page). Left in the tree for
reference; do not add features here — edit `public/ui/chavruta.html`.
