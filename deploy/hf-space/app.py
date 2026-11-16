"""Hugging Face Space entry point.

Free Hugging Face accounts get Gradio Spaces on ZeroGPU hardware (Docker Spaces are paid), so the
Space runs this file instead of the Dockerfile. It serves the same FastAPI app as the Docker image,
with a small Gradio page at the root. Nothing here needs a GPU: the optimiser and the agent run on
CPU. ZeroGPU shuts down a Space whose Gradio app has no @spaces.GPU event, so the page has one
button wired to a trivial GPU function.
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


@spaces.GPU(duration=5)
def gpu_check() -> str:
    """The Space's one GPU event (see the module docstring); it does no GPU work."""
    return "ZeroGPU is reachable. The optimiser and the agent themselves run on CPU."


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
    out = gr.Textbox(label="ZeroGPU check", interactive=False)
    gr.Button("Check GPU").click(gpu_check, outputs=out)

# The Gradio page takes the root, so drop the API's own "/" redirect to /docs; API routes stay
# first and keep precedence over the Gradio mount.
api.router.routes = [r for r in api.router.routes if getattr(r, "path", None) != "/"]
# ssr_mode=False: on Spaces Gradio otherwise starts a Node server, which takes port 7860 first
app = gr.mount_gradio_app(api, demo, path="/", ssr_mode=False)

if __name__ == "__main__":
    # Same address variables as gradio.launch(); Spaces route traffic to 7860
    host = os.environ.get("GRADIO_SERVER_NAME", "0.0.0.0")
    port = int(os.environ.get("GRADIO_SERVER_PORT") or os.environ.get("PORT") or "7860")
    print(f"Serving on {host}:{port} (GRADIO_SERVER_PORT={os.environ.get('GRADIO_SERVER_PORT')}, "
          f"PORT={os.environ.get('PORT')})", flush=True)
    if os.environ.get("SPACES_ZERO_GPU"):
        # gradio.launch() sends ZeroGPU's startup report; uvicorn.run() does not, and the
        # `spaces` version preinstalled on Spaces adds no middleware that would. Without the
        # report the platform stops the app ("No @spaces.GPU function detected during startup").
        import spaces.zero

        spaces.zero.startup()
        print("ZeroGPU startup report sent", flush=True)
    uvicorn.run(app, host=host, port=port)
