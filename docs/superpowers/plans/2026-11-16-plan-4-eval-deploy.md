# Crew Roster Copilot — Plan 4: Evaluation, deployment and README

> **For agentic workers:** implement task-by-task with TDD for Python code; one commit per task. Steps use checkbox (`- [ ]`) syntax.

**Goal:** Measure the optimiser (CP-SAT re-plan vs greedy vs re-solve from scratch, plus crew sizing) and the agent (tool choice, arguments, numbers, grounding; optional Claude judge on explanations), write `docs/results/RESULTS.md`, and make the backend deployable to Cloud Run with a full README.

**Spec:** design spec §9 and §11. **Builds on:** Plans 1–3.

## Global Constraints

- **No money and no keys needed for anything that runs automatically.**
  - The optimiser benchmark needs no LLM.
  - The agent evaluation runs on Groq's free tier only when the owner runs it with a key.
  - The Claude judge runs only with `--judge` and an `ANTHROPIC_API_KEY`; it prints its estimated cost first. The judge model is `claude-haiku-5-5`.
- Tests never call a real LLM: they use `tests/fakes.py` `ScriptedChatModel` through an `llm_factory`.
- Everything is seeded and reproducible. Results go to `docs/results/*.json` plus `docs/results/RESULTS.md`.
- The laptop is slow:
  - The full optimiser benchmark (~10–15 min) runs in the background and is announced.
  - Tests use 2–3 scenarios and `time_limit ≤ 5`. Anything over ~10 s is `@pytest.mark.slow`.
- Deployment is not executed by agents: no `gcloud`, no `docker push`, no `git push`. The scripts and docs are prepared for the owner to run.
- Keys only in `.env` and Cloud Run env vars (passed through a temp YAML file, never on a command line). Never print or commit them.
- Commit locally on `main`, with a message ending `Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>`.

## File map

```
src/crew_roster/eval/__init__.py
src/crew_roster/eval/scenarios.py      seeded random disruption scenarios
src/crew_roster/eval/optimiser.py      benchmark + sizing table -> docs/results/optimiser.json
src/crew_roster/eval/agent_dataset.py  ~40 questions with ground truth computed from the service
src/crew_roster/eval/agent_eval.py     run agent over the dataset, deterministic metrics, optional judge, optional LangSmith
src/crew_roster/eval/report.py         docs/results/RESULTS.md from the JSON files
src/crew_roster/eval/cli.py            crew-eval {optimiser,agent,report}
Dockerfile  .dockerignore  .gcloudignore  scripts/deploy_cloudrun.py  README.md
tests/test_eval_scenarios.py tests/test_eval_optimiser.py tests/test_eval_agent.py tests/test_eval_report.py
```

### Task 1: Seeded disruption scenarios
- [ ] `Scenario(id: str, size: Literal["small","medium","large"], disruptions: list[Disruption])`.
- [ ] `make_scenarios(n=50, seed=11, ruleset="dgca_current") -> list[Scenario]`:
  - About a third each of small (1 disruption), medium (2–3) and large (4–6).
  - Each disruption is chosen at random:
    - **sick:** a pilot who has a base-roster duty on `from_day ∈ 1..5`; length 1–2 days, `to_day ≤ 6`.
    - **delay:** a flight on days 1..5, minutes from {60, 120, 180, 240, 300}.
    - **cancel:** a flight on days 1..6.
  - Never two disruptions on the same pilot or the same turn.
  - Scenario ids are `S00`…`S49`.
- [ ] Tests:
  - deterministic for a given seed;
  - sizes are distributed as specified;
  - every scenario applies cleanly via `crew_roster.disrupt.apply` (no ValueError) on the base problem.

### Task 2: Optimiser benchmark and sizing table
- [ ] `run_benchmark(scenarios, methods=("cpsat","greedy","scratch"), time_limit=10.0) -> list[dict]`:
  - Uses `base_problem(ruleset)` and `replan(problem, base, disruptions, method=…)`.
  - One row per (scenario, method): `scenario, size, method, uncrewed (len uncovered), changes, breaches (len check(new_problem, roster)), seconds, status`.
- [ ] `summarise(rows) -> dict`: per method and per size, mean and median of changes, uncrewed and seconds; total breaches; and "cpsat fewer changes than scratch" / "cpsat fewer uncrewed than greedy" win counts.
- [ ] `sizing_table(time_limit=15.0) -> list[dict]`: for base in DEL/BOM × both rulesets, the `min_pilots_needed` fields.
- [ ] `run_optimiser_eval(n, time_limit, out=docs/results/optimiser.json)`:
  - Writes `{config, rows, summary, sizing}`.
  - Resumable: rows already in the file are skipped.
- [ ] Tests (fast):
  - 2 scenarios × cpsat/greedy with `time_limit=5` gives rows with the right keys and `breaches == 0` for cpsat;
  - `summarise` on hand-made rows gives the expected means and wins;
  - resume skips existing rows (write a file with one row, then run → that row is not recomputed; monkeypatch `replan` to count calls).
  - The sizing table is tested only under `@pytest.mark.slow`.

### Task 3: Agent evaluation dataset
- [ ] `AgentCase(id, category, question, ruleset, disruptions, expected_tool, expected_args: dict, expected_numbers: list[float])`.
- [ ] `build_dataset(seed=5) -> list[AgentCase]`: about 40 cases in 5 categories (~8 each). Ground truth is computed through `crew_roster.service`, never written by hand:
  1. `hours`: "How many flight hours has {pilot} flown in the 7 days up to day {d}, and how many remain?" → `pilot_status`, args `{pilot_id, day}`, numbers [used_h, remaining_h] of ft_7d.
  2. `roster`: "Who is the captain and first officer on duty {duty}?" → `get_roster`, numbers [] (answer must contain both pilot names; store them in `expected_names`, add that field).
  3. `what_if`: "If {pilot} calls in sick on days {a}–{b}, how many roster changes are needed?" → `what_if`, numbers [changes].
  4. `explain`: with one sick disruption applied as the current scenario, "Why was {old pilot name} replaced on {duty}?" → `explain_change`, numbers = time-rule values in hours from the reasons (may be empty for sick).
  5. `sizing`: "How many captains and first officers does {base} need under {ruleset label}?" → `min_pilots_needed`, numbers [CPT, FO]. Use only 4 cases (2 bases × 2 rulesets) because each takes ~15 s the first time.
- [ ] Tests: deterministic; 5 categories; every expected tool name exists in `Toolbox`; numbers are floats.

### Task 4: Agent evaluation runner and metrics
- [ ] `score(case, answer: AgentAnswer) -> dict`:
  - `tool_ok` (expected tool among `tool_calls` names);
  - `args_ok` (some call of that tool whose args contain `expected_args`);
  - `numbers_recall` (share of expected numbers found in the answer within 0.051, via `numbers.extract`; 1.0 if none expected);
  - `names_ok` (roster: all expected names present);
  - `grounded` (= `answer.verified`);
  - `n_tool_calls`; `seconds`.
- [ ] `run_agent_eval(model: str, cases, llm_factory=None, out=None, judge=False, langsmith=False)`:
  - Runs `run_agent` per case.
  - The default factory uses Groq with `answer_model=model` and no fallback: build `ChatGroq(model=model)` with `bind_tools`. Every scored answer must come from the named model.
  - Writes `docs/results/agent-<model-slug>.json` with rows and a summary (means per metric and per category).
  - Resumable per case id. Sleeps 2 s between cases to respect Groq's free rate limits, and stops cleanly on a daily-limit error, saving progress.
- [ ] Optional judge (`--judge`):
  - For the `explain` cases, and for 10 change explanations from `/replan` scenarios, ask `ChatAnthropic(model="claude-haiku-5-5")` for JSON `{"faithful": 1-5, "clear": 1-5, "why": "..."}` given the checker reasons and the sentence.
  - Print the estimated cost (tokens × price) and the number of calls before starting.
  - Requires `ANTHROPIC_API_KEY`; add `langchain-anthropic` via `uv add`.
- [ ] Optional LangSmith (`--langsmith`, needs `LANGSMITH_API_KEY`): upload the cases as dataset `crew-roster-agent` (idempotent) and log each run as an experiment with `langsmith.evaluate`, using the same `score` fields as feedback.
- [ ] Tests (no network):
  - `score` on handmade AgentAnswers (tool missing, wrong args, numbers found/missing, unverified);
  - `run_agent_eval` with a ScriptedChatModel factory on 2 cases writes the JSON and resumes;
  - the judge and LangSmith paths are not executed in tests; only their argument checks are tested (judge without a key → SystemExit with a clear message).

### Task 5: Report and CLI
- [ ] `crew-eval optimiser [--n 50] [--time-limit 10]`, `crew-eval agent --model openai/gpt-oss-120b [--limit N] [--judge] [--langsmith]`, `crew-eval report`. Register the `crew-eval` script.
- [ ] `report.py` builds `docs/results/RESULTS.md` from whatever JSON exists:
  - an optimiser table per method × size;
  - win counts and total breaches;
  - the sizing table (current vs exemption, with "proven"/"upper bound");
  - an agent table per model (tool accuracy, args accuracy, numbers recall, grounded rate, mean tool calls, mean seconds) and per category;
  - judge scores if present.
  - Sections without data say how to produce them.
- [ ] Tests: report renders with only optimiser data, and with fake agent JSON.
- [ ] **Run the real optimiser benchmark** in the background: `uv run crew-eval optimiser`, then `uv run crew-eval report`, and commit `docs/results/`.

### Task 6: Deployment files and README
- [ ] `Dockerfile`, adapted from the previous project:
  - python:3.11-slim, uv 0.13.1, `uv sync --frozen --no-dev`;
  - copy `src` (it includes the cached base rosters);
  - non-root user;
  - `CMD uv run --no-sync uvicorn crew_roster.api.main:app --host 0.0.0.0 --port ${PORT:-8080}`.
- [ ] `.dockerignore` and `.gcloudignore` exclude `.env`, `.venv`, `frontend/node_modules`, `frontend/dist`, `.superpowers`, `tests`, `docs/superpowers`.
- [ ] `scripts/deploy_cloudrun.py`, adapted from the previous project:
  - service `crew-roster-copilot`, default project `annual-report-rag-krtiin`, region `us-central1`;
  - `--memory 1Gi --cpu 2 --min-instances 0 --max-instances 2 --concurrency 4 --timeout 120`;
  - env vars through a temp YAML file: GROQ_API_KEY, ANSWER_MODEL, FAST_MODEL, ALLOWED_ORIGINS (localhost + the given Pages origin), LANGSMITH_* if set;
  - prints the URL and the GitHub variable to set.
  - The script is not executed.
- [ ] `README.md`:
  - **What and why:** fictional Skyline Air, with the December 2025 Indian crew-rostering disruption and the IIT Delhi AI-for-disruption partnership as motivation, plus a not-affiliated note.
  - **Architecture diagram** (Mermaid): data → duties (CP-SAT) → roster (CP-SAT) → checker; disruptions → re-plan; agent tools → LangGraph → number check; API → React.
  - **DGCA rules table** with values and CAR references, plus a "Rule assumptions and simplifications" list. Take it from `.superpowers/sdd/progress.md` README notes:
    - flat 8 h flight time;
    - weekly rest as 2 free calendar days;
    - FDP measured to release, including 30 min post-flight;
    - night rules apply to any duty touching 00–06;
    - no once-per-168 h consecutive-night exception;
    - no +1 h extension;
    - exemption night landings as reported;
    - cancelled duties produce no Change;
    - one duty per pilot per day;
    - out-and-back duties only.
  - **Why 80 pilots:** 60 was provably uncrewable.
  - **Results:** link to and summarise RESULTS.md.
  - **Quick start:** `uv sync`, `uv run crew-solve`, `uv run crew-serve`, frontend `npm ci && npm run dev`, tests.
  - **"Before going live" checklist for the owner:**
    1. Copy `.env.example` → `.env`, add GROQ (and optionally LANGSMITH/ANTHROPIC) keys.
    2. `uv run pytest -m live`.
    3. `uv run crew-eval agent --model openai/gpt-oss-120b` (and `openai/gpt-oss-20b`), then optionally `--judge` (≈ cost printed first).
    4. Create the GitHub repo `crew-roster-copilot`, then `git remote add origin …` and `git push -u origin main`.
    5. `uv run python scripts/deploy_cloudrun.py --origins https://krtiinsharma.github.io`.
    6. Set the repo variable `API_URL` and enable Pages (GitHub Actions source).
  - **Tech stack and skills shown.**
- [ ] Commit "docs: README, Dockerfile and Cloud Run deploy script".
