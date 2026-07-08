# Chavruta.AI — Frontend (React + Vite SPA)

The chat UI for Chavruta.AI: a three-column "beit midrash" layout (sessions · conversation ·
related sources) that talks to the FastAPI backend in [`app/api.py`](../api.py). Citations are
clickable and resolve to the source on Sefaria.

## Stack

- **React + TypeScript + Vite** (HMR dev server on port **5173**)
- **Tailwind** utility styling (`index.css`, `@theme` tokens — light/dark, "beit midrash" palette)
- **Heebo** (sans) + **Frank Ruhl Libre** (serif) — both render Hebrew and Latin cleanly

## Internationalization (Hebrew / English)

Language is handled entirely through [`src/i18n.tsx`](src/i18n.tsx):

- `LangProvider` wraps the app; `useLang()` exposes `t(key)`, `lang`, `toggle()`, and `dir`.
- The `STRINGS` table holds every UI string with a `he` and `en` form — **no hardcoded UI text
  in components**. Add new copy here, not inline.
- Switching language updates `document.documentElement.lang`/`dir` (RTL ↔ LTR) and persists the
  choice in `localStorage` (`chavruta-lang`). Default is Hebrew.
- The `lang` is sent to the backend on every query so the LLM answers in the requested language
  (the backend selects Hebrew vs. English system prompts accordingly).
- Avatar initials and cited-source tags (Rashi / רש"י, Gemara / גמרא …) are language-aware.

When adding a component, route all user-facing text through `t()` and use direction-aware Tailwind
utilities (`ms-`/`me-`/`ps-`/`pe-`/`start-`/`end-`, `rtl:`) so it works in both directions.

## Project layout

```
src/
  main.tsx                 entry — wraps <App/> in <LangProvider>
  App.tsx                  layout shell (3 columns + mobile drawers)
  i18n.tsx                 language context + STRINGS table (he/en)
  types.ts                 shared types (Session, Message, Citation, …)
  index.css                Tailwind theme tokens, fonts, RTL/LTR helpers
  hooks/
    useSession.ts          session list, create/continue/delete, message history
  components/
    TopNav.tsx             header: logo, language toggle, settings
    SessionSidebar.tsx     conversation list grouped by recency
    ChatPane.tsx           message thread + composer (intent, send)
    MessageBubble.tsx      one message; inline citation links; source tags
    CitationCard.tsx       expandable source card (HE/EN text, Sefaria link)
    SourcesPanel.tsx       related-sources column
    Icon.tsx               Material Symbols icon renderer
```

## Commands

```bash
npm install      # install dependencies
npm run dev      # Vite dev server → http://localhost:5173
npm run build    # type-check (tsc -b) + production build → dist/
npm run preview  # serve the production build locally
npm run lint     # ESLint
```

The dev server expects the backend running on port 8080 (see [`scripts/serve.ps1`](../../scripts/serve.ps1)).
