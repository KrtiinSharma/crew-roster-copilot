# Crew Roster Copilot — Plan 3: React frontend

> **For agentic workers:** implement task-by-task; each task ends with `npm run build` and `npm run lint` passing and a commit. Steps use checkbox (`- [ ]`) syntax.

**Goal:** A single-page React app (GitHub Pages) over the Plan 2 API. It shows the 7-day pilot roster as a grid, lets the user apply disruptions and switch ruleset, shows the re-plan numbers and plain-language change explanations, and has a chat panel that shows each tool call.

**Architecture:** Vite + React 19 + TypeScript + Tailwind 4, the same toolchain and versions as the owner's previous project (`annual-report-rag/frontend`). The app is stateless towards the server: React state holds `{ruleset, disruptions, chat messages}`. Every change POSTs the whole scenario to `/replan`, and `/chat` gets the same scenario. In dev, Vite proxies `/api` → `http://localhost:8000`; in production `VITE_API_URL` is the Cloud Run URL.

**Spec:** design spec §8. **API contract:** Plan 2 Task 8 (`ScenarioView`, `AgentAnswer`).

## Global Constraints

- Fictional airline **"Skyline Air"**. No IndiGo name, logo or colours anywhere in the UI. The About section says: "Fictional airline. Inspired by the December 2025 crew-rostering disruption in Indian aviation; not affiliated with any airline."
- Copy `package.json` and `package-lock.json` from `C:\Users\KRTIIN SHARMA\OneDrive\Desktop\annual-report-rag\frontend` and install with `npm ci` (exact same versions). Drop no dependencies. `react-markdown` + `remark-gfm` render chat answers.
- Days are shown as "Day 0" … "Day 6" (same numbering as the API and agent).
- Works at phone width (single column below `md`), with a light theme only. Keep a neutral palette: slate, plus one accent (sky). Red marks breaches or uncrewed slots, amber marks changed duties.
- No secrets in the frontend. `VITE_API_URL` and `VITE_BASE` are build-time variables only.
- Commit locally on `main` only (no remote yet); messages end with `Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>`.
- Frontend checks are `npm run build` (tsc + vite) and `npm run lint`. There is no separate JS test framework (YAGNI). The backend suite must stay green.

## API types (`frontend/src/api.ts`), mirroring Plan 2 exactly

```ts
export const API_URL = (import.meta.env.VITE_API_URL ?? '/api').replace(/\/$/, '')

export type Ruleset = 'dgca_current' | 'dgca_dec2025_exemption'
export type Disruption =
  | { kind: 'sick'; pilot_id: string; from_day: number; to_day: number }
  | { kind: 'delay'; flight_id: string; minutes: number }
  | { kind: 'cancel'; flight_id: string }
export interface Violation { rule: string; pilot_id: string | null; duty_id: string | null;
  day: number | null; value: number; limit: number; message: string }
export interface PilotView { id: string; name: string; rank: 'CPT' | 'FO'; base: string;
  unavailable_days: number[]; sick_days: number[] }
export interface FlightView { id: string; day: number; origin: string; dest: string;
  dep: string; arr: string; dep_min: number; arr_min: number }
export interface DutyView { id: string; base: string; day: number; route: string;
  flight_ids: string[]; report: string; release: string; report_min: number;
  release_min: number; flight_time_h: number; duty_h: number; landings: number;
  night: boolean; legal: boolean; cpt: string | null; fo: string | null }
export interface ChangeView { id: string; duty_id: string; role: 'CPT' | 'FO';
  old_pilot: string | null; new_pilot: string | null; reasons: Violation[]; explanation: string }
export interface Stats { duties: number; slots: number; crewed: number; uncovered: number;
  changes: number; violations: number; solve_seconds: number; status: string }
export interface ScenarioView { ruleset: Ruleset; label: string; disruptions: Disruption[];
  stats: Stats; pilots: PilotView[]; flights: FlightView[]; duties: DutyView[];
  changes: ChangeView[]; illegal_duties: string[] }
export interface ChatTurn { role: 'user' | 'assistant'; content: string }
export interface ToolCallTrace { name: string; args: Record<string, unknown>; seconds: number; ok: boolean }
export interface AgentAnswer { answer: string; verified: boolean; ungrounded: string[];
  tool_calls: ToolCallTrace[] }

export async function replan(ruleset: Ruleset, disruptions: Disruption[]): Promise<ScenarioView>
export async function chat(ruleset: Ruleset, disruptions: Disruption[], messages: ChatTurn[]): Promise<AgentAnswer>
// both POST JSON; on !ok throw Error(detail from {"detail": ...} or status text)
```

## Screens and components

- **Header:** "Crew Roster Copilot · Skyline Air", a ruleset toggle (current rules / Dec-2025 exemption), a Reset button (clears disruptions and chat), and an About link.
- **Numbers strip** (`StatsBar`): duties, crewed slots `crewed/slots`, uncrewed (red if > 0), assignments changed, rule breaches (green "0 breaches ✓" or red), solve time. A spinner while a request is in flight.
- **Disruption panel** (`DisruptionPanel`): three small forms:
  - **Pilot sick:** a pilot select grouped by base, showing name and id, plus from and to day selects.
  - **Delay flight:** a day select, then a flight select for that day showing id, route and departure, plus minutes (30–600, step 15).
  - **Cancel flight:** a day select and a flight select.
  - Below the forms, the list of applied disruptions as chips with ×; removing one re-plans.
- **Roster grid** (`RosterGrid`): a base filter (DEL/BOM), a rank filter (all/CPT/FO) and a "changed only" checkbox. Rows are pilots (name, id, rank), columns Day 0–6. Each cell shows that pilot's duty for the day:
  - the route, shortened to the airports after the base, e.g. "BOM·PNQ";
  - report–release times and flight hours;
  - a 🌙 marker for night duties.
  - Grey cells mark unavailable or sick days (striped red for sick).
  - Amber outlines mark duties whose assignment changed. Click a cell to open a side card with the duty details and, if changed, its explanation.
  - Below the grid, an "Uncrewed duties" list (red) when any slot is empty.
  - Scrolls horizontally inside its own container on small screens. The page itself never scrolls sideways.
- **Changes list** (`ChangesList`): one row per change: duty id, seat, old → new pilot names, the explanation, and reason chips (rule names).
- **Chat** (`ChatPanel`):
  - A message list where assistant answers render with react-markdown and show a "verified ✓" badge, or "unverified numbers: …" in amber.
  - A collapsible "tools used" list (name, seconds, ✓/✗).
  - Three example prompts:
    - "Who could replace the captain of BOM-D3-05 if they fell sick?"
    - "How many hours can DEL-C01 still fly by day 4?"
    - "How many pilots would BOM need under the Dec-2025 exemption?"
  - A 503 shows "The assistant isn't configured yet (no Groq key)." and a 429 shows the API's message.
- **About** (`AboutView`, a modal or section): what the app does, the two-step optimiser, the number check, the DGCA rules with values from `GET /rules`, the fictional-airline disclaimer, and a link to the GitHub repo (placeholder `https://github.com/KrtiinSharma/crew-roster-copilot`).

## Tasks

### Task 1: Scaffold, API client and data loading
- [ ] Create `frontend/` by copying `package.json`, `package-lock.json`, `tsconfig*.json`, `eslint.config.js`, `vite.config.ts` and `index.html` from the previous project. Rename the package to `crew-roster-copilot-frontend` and the title to "Crew Roster Copilot". In `vite.config.ts` the proxy must strip the prefix, because the backend routes have no `/api`: `proxy: { '/api': { target: 'http://localhost:8000', rewrite: (p) => p.replace(/^\/api/, '') } }`. Run `npm ci`.
- [ ] `src/api.ts` as above. `src/App.tsx` loads `replan(ruleset, [])` on start and on ruleset change, and shows loading/error states. `src/index.css` has `@import "tailwindcss";`.
- [ ] `npm run build && npm run lint` pass. Start the backend (`uv run crew-serve`, background) and the dev server (`npm run dev`, background), fetch `http://localhost:5173/api/roster` through the proxy to confirm the wiring, then stop both. Commit "feat(frontend): scaffold, API client and scenario loading".

### Task 2: Roster grid, stats bar and duty details
- [ ] `StatsBar`, `RosterGrid` (filters, cells, night marker, unavailable/sick shading, changed outline, uncrewed list) and `DutyCard`. `src/lib/format.ts` holds the helpers `shortRoute`, `dayLabel`, `pilotName(map, id)`.
- [ ] Build + lint; commit "feat(frontend): roster grid and numbers strip".

### Task 3: Disruption panel and changes list
- [ ] `DisruptionPanel` (three forms, chips, remove) and `ChangesList`. App state: applying or removing a disruption calls `replan` with the full list. The previous view stays visible with a spinner until the new one arrives. On an API error (e.g. 422) the error is shown and the failed disruption is not kept.
- [ ] Build + lint; commit "feat(frontend): disruptions, re-plan and change explanations".

### Task 4: Chat panel and About
- [ ] `ChatPanel` (history, examples, verified badge, tools-used list, 503/429 messages) and `AboutView` (loads `GET {API_URL}/rules`; shows hours as `value/60` for time rules).
- [ ] Layout: two columns from `lg` (left: disruptions, stats, changes, chat; right: grid), one column below.
- [ ] Build + lint; commit "feat(frontend): copilot chat and about page".

### Task 5: GitHub Pages workflow and CI
- [ ] `.github/workflows/pages.yml`, adapted from the previous project. Build with `VITE_BASE=/crew-roster-copilot/` and `VITE_API_URL=${{ vars.API_URL }}`, and deploy with actions/deploy-pages.
- [ ] `.github/workflows/ci.yml`: backend `uv sync --frozen`, `ruff check src tests scripts`, `pytest`; frontend `npm ci && npm run build`.
- [ ] Commit "ci: GitHub Pages deploy and CI workflows". (These only run once the owner creates the GitHub repo.)
