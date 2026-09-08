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
import functools
import http.server
import shutil
import socketserver
import subprocess
import sys
import tempfile
from pathlib import Path

PROJECT_DIR = Path(__file__).resolve().parent
OUTPUT_DIR = PROJECT_DIR / "build" / "web"

# pygbag names the bundle after the folder it builds from.
APP_NAME = "flappy-bird"

# Everything the game opens at runtime, and nothing else.
RUNTIME_FILES = ["main.py", "flappybirdclone.py"]
RUNTIME_DIRS = ["images"]


def trim(output_dir, app_name):
    """Strip what the embedded build never uses.

    None of this is large next to the ~10MB CPython runtime the page
    pulls from the pygbag CDN, but it removes a dead file, a request
    that 404s, and the debug terminal, which does not belong in an
    embed on a portfolio page.
    """
    # The .apk is only read when the page is hosted on itch.io; every
    # other host takes the .tar.gz. See the loader in index.html.
    apk = output_dir / f"{app_name}.apk"
    if apk.exists():
        apk.unlink()

    # pygbag's own favicon, irrelevant inside an iframe.
    favicon = output_dir / "favicon.png"
    if favicon.exists():
        favicon.unlink()

    index = output_dir / "index.html"
    html = index.read_text(encoding="utf-8")
    replacements = [
        # vtx is the xterm.js debug console (~90KB over the wire) and
        # snd is the audio shim. This game has neither a console worth
        # showing nor any sound.
        ('data-os="vtx,snd,gui"', 'data-os="gui"'),
        ('<link rel="icon" type="image/png" href="favicon.png" '
         'sizes="16x16">', ""),
        # pygbag emits this with a doubled slash and the CDN 404s it.
        ('<script src="https://pygame-web.github.io/cdn/0.9.3'
         '//browserfs.min.js"></script>', ""),
        # pygbag paints the page around the canvas a flat grey, once in
        # CSS and again from JS after boot. Both have to go transparent
        # so an iframe picks up whatever the host page is using and the
        # embed works in light and dark themes alike.
        ("background-color:powderblue;", "background-color: transparent;"),
        ('platform.document.body.style.background = "#7f7f7f"',
         'platform.document.body.style.background = "transparent"'),
    ]
    for old, new in replacements:
        if old not in html:
            print(f"  warning: could not trim, pattern not found: {old[:60]}")
        html = html.replace(old, new)
    index.write_text(html, encoding="utf-8")


def stage(staging_dir):
    """Copy the runtime files into a clean folder for pygbag to pack."""
    for name in RUNTIME_FILES:
        shutil.copy2(PROJECT_DIR / name, staging_dir / name)
    for name in RUNTIME_DIRS:
        shutil.copytree(PROJECT_DIR / name, staging_dir / name)


def build(staging_dir):
    """Run pygbag over the staged folder."""
    command = [
        sys.executable, "-m", "pygbag", "--build",
        "--title", "Flappy Bird", str(staging_dir),
    ]
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


def serve(port):
    """Serve the trimmed build, the way a real host would.

    pygbag's own test server rewrites the CDN URLs to proxy through
    itself. Serving the files as they are keeps the page pointed at the
    real CDN, which is what it will do once it is deployed.
    """
    handler = functools.partial(
        http.server.SimpleHTTPRequestHandler, directory=str(OUTPUT_DIR)
    )
    with socketserver.TCPServer(("127.0.0.1", port), handler) as httpd:
        print(f"\nServing {OUTPUT_DIR} on http://localhost:{port}/")
        print("Ctrl+C to stop.")
        httpd.serve_forever()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--serve",
        action="store_true",
        help="serve the build on http://localhost:8000 when it is done",
    )
    parser.add_argument(
        "--port", type=int, default=8000, help="port for --serve"
    )
    args = parser.parse_args()

    with tempfile.TemporaryDirectory() as tmp:
        # pygbag names the bundle after this folder.
        staging_dir = Path(tmp) / APP_NAME
        staging_dir.mkdir()
        stage(staging_dir)
        build(staging_dir)
        collect(staging_dir)

    trim(OUTPUT_DIR, APP_NAME)

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

    if args.serve:
        serve(args.port)


if __name__ == "__main__":
    main()
