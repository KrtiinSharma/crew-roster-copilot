"""Assemble the Hugging Face Space folder: app.py, README.md, requirements.txt and src/.

    python deploy/hf-space/make_space.py <out-dir>

requirements.txt is the project's runtime dependencies from pyproject.toml plus `spaces`; Gradio
itself comes from sdk_version in the Space README, so it is not listed.
"""

import shutil
import sys
import tomllib
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]


def main() -> None:
    out = Path(sys.argv[1])
    out.mkdir(parents=True, exist_ok=True)
    for name in ("app.py", "README.md"):
        shutil.copy(HERE / name, out / name)
    shutil.copytree(ROOT / "src", out / "src", dirs_exist_ok=True,
                    ignore=shutil.ignore_patterns("__pycache__", "*.pyc"))
    deps = tomllib.loads((ROOT / "pyproject.toml").read_text(encoding="utf-8"))
    lines = [*deps["project"]["dependencies"], "spaces"]
    (out / "requirements.txt").write_text("\n".join(lines) + "\n", encoding="utf-8")
    print(f"Space folder ready in {out}")


if __name__ == "__main__":
    main()
