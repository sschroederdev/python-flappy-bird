"""Build the WebAssembly version of the game into ``build/web``.

pygbag packs *every* file in the folder it is pointed at into the
archive the browser downloads, and its ignore filter does not reliably
catch a local virtualenv. Building straight from the repo root sweeps
.venv into the payload and adds around 12MB to what every visitor
downloads.

So this stages only the files the game actually needs at runtime into a
scratch folder, builds from there, and copies the result back.

Usage::

    python build_web.py            # build into build/web
    python build_web.py --serve    # build, then serve it on :8000
"""

import argparse
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

PROJECT_DIR = Path(__file__).resolve().parent
OUTPUT_DIR = PROJECT_DIR / "build" / "web"

# Everything the game opens at runtime, and nothing else.
RUNTIME_FILES = ["main.py", "flappybirdclone.py"]
RUNTIME_DIRS = ["images"]


def stage(staging_dir):
    """Copy the runtime files into a clean folder for pygbag to pack."""
    for name in RUNTIME_FILES:
        shutil.copy2(PROJECT_DIR / name, staging_dir / name)
    for name in RUNTIME_DIRS:
        shutil.copytree(PROJECT_DIR / name, staging_dir / name)


def build(staging_dir, serve):
    """Run pygbag over the staged folder."""
    command = [sys.executable, "-m", "pygbag", "--title", "Flappy Bird"]
    if not serve:
        command.append("--build")
    command.append(str(staging_dir))
    subprocess.run(command, check=True)


def collect(staging_dir):
    """Copy pygbag's output back into the project's build directory."""
    built = staging_dir / "build" / "web"
    if not built.is_dir():
        raise SystemExit(f"pygbag produced no output at {built}")
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    # Clear the old files but leave the directory itself alone: on
    # Windows a dev server running out of it holds a handle open, and
    # removing the directory would fail with a PermissionError.
    for path in OUTPUT_DIR.rglob("*"):
        if path.is_file():
            path.unlink()
    shutil.copytree(built, OUTPUT_DIR, dirs_exist_ok=True)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--serve",
        action="store_true",
        help="serve the build on http://localhost:8000 when it is done",
    )
    args = parser.parse_args()

    with tempfile.TemporaryDirectory() as tmp:
        # pygbag names the bundle after this folder.
        staging_dir = Path(tmp) / "flappy-bird"
        staging_dir.mkdir()
        stage(staging_dir)
        build(staging_dir, args.serve)
        if not args.serve:
            collect(staging_dir)

    if not args.serve:
        total = sum(
            path.stat().st_size
            for path in OUTPUT_DIR.rglob("*")
            if path.is_file()
        )
        print(f"\nBuilt {OUTPUT_DIR} ({total / 1024:.0f} KB)")
        for path in sorted(OUTPUT_DIR.rglob("*")):
            if path.is_file():
                size = path.stat().st_size / 1024
                print(f"  {path.relative_to(OUTPUT_DIR)}  {size:.0f} KB")


if __name__ == "__main__":
    main()
