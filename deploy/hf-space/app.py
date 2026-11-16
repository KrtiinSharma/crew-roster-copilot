"""Hugging Face Space entry point.

Free Hugging Face accounts get Gradio Spaces on ZeroGPU hardware (Docker Spaces are paid), so the
Space runs this file instead of the Dockerfile. It serves the same FastAPI app as the Docker image,
with a small Gradio page mounted at /ui. Nothing here uses a GPU: the optimiser and the agent run
on CPU, and the GPU function below exists only because ZeroGPU hardware expects one.
"""

import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "src"))

# ZeroGPU wants `spaces` imported before other heavy libraries, so the order here is deliberate
import spaces  # noqa: E402, I001
import gradio as gr  # noqa: E402
import uvicorn  # noqa: E402

from crew_roster.api.main import app as api  # noqa: E402

WEB_APP = "https://krtiinsharma.github.io/crew-roster-copilot/"
SOURCE = "https://github.com/KrtiinSharma/crew-roster-copilot"


@spaces.GPU
def _gpu_placeholder() -> None:
    """Never called; see the module docstring."""


with gr.Blocks(title="Crew Roster Copilot API") as demo:
    gr.Markdown(
        "# Crew Roster Copilot (API)\n"
        "Backend for a pilot-rostering demo: a CP-SAT optimiser builds rosters for a fictional "
        "airline under the DGCA flight duty time limits, re-plans after disruptions with as few "
        "changes as possible, and a LangGraph agent answers questions through tools.\n\n"
        f"- **Web app:** [{WEB_APP}]({WEB_APP})\n"
        "- **API docs:** [/docs](/docs)\n"
        f"- **Source:** [{SOURCE}]({SOURCE})\n\n"
        "All airline, flight and pilot data is synthetic."
    )

app = gr.mount_gradio_app(api, demo, path="/ui")

if __name__ == "__main__":
    uvicorn.run(app, host="0.0.0.0", port=int(os.environ.get("PORT", "7860")))
