---
title: Crew Roster Copilot
emoji: ✈️
colorFrom: blue
colorTo: indigo
sdk: gradio
sdk_version: 6.31.0
python_version: "3.12.12"
app_file: app.py
pinned: false
short_description: Pilot roster optimiser API with an LLM agent
---

# Crew Roster Copilot (API)

Backend for Crew Roster Copilot: a CP-SAT optimiser that builds pilot rosters for a fictional airline
under the DGCA flight duty time limits, re-plans after disruptions with as few changes as possible,
and a LangGraph agent that answers questions about the roster through tools.

- Web app: https://krtiinsharma.github.io/crew-roster-copilot/
- Source code and documentation: https://github.com/KrtiinSharma/crew-roster-copilot
- API docs: `/docs` on this Space

`app.py` serves the project's FastAPI app (the same one the Dockerfile runs) with a small Gradio
page at the root, because free accounts get Gradio Spaces on ZeroGPU hardware. Nothing needs the GPU;
the page has one "Check GPU" button because ZeroGPU requires a `@spaces.GPU` event.

This Space is synced automatically from the GitHub repository; do not edit it here.
All airline, flight and pilot data is synthetic.
