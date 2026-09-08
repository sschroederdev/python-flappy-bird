# python-flappy-bird

A Flappy Bird clone written in Python with pygame.

![Python](https://img.shields.io/badge/python-3.11-blue)
![pygame](https://img.shields.io/badge/pygame-2.6-green)
[![CI](https://github.com/sschroederdev/python-flappy-bird/actions/workflows/ci.yml/badge.svg)](https://github.com/sschroederdev/python-flappy-bird/actions/workflows/ci.yml)

## Running it

```bash
python -m venv .venv
source .venv/Scripts/activate   # Windows: .venv\Scripts\activate
pip install -r requirements.txt
python flappybirdclone.py
```

## Running it in a browser

The game also compiles to WebAssembly via [pygbag](https://pypi.org/project/pygbag/),
so it runs in a browser as real CPython — not a JavaScript rewrite.

```bash
pip install pygbag
python build_web.py            # writes build/web
python build_web.py --serve    # build, then serve on localhost:8000
```

`build/web` is a static folder: drop it on any host and embed it in an
`<iframe>`. The bundle is ~77KB; the CPython and pygame runtime comes
from the pygbag CDN on first load and is cached after that.

Build it with `build_web.py` rather than by running `pygbag` against the
repo directly. pygbag packs *every* file in the folder it is given, and
its ignore filter does not catch a local `.venv` — building in place
sweeps the virtualenv into the download and turns 77KB into 12MB.

## Tests and CI

```bash
pip install -r requirements-dev.txt
pycodestyle .
python -m unittest discover -s tests -t .
```

The tests drive the state machine a frame at a time instead of running
`Game.run`, which loops until the window closes, and they run headless
under SDL's dummy video driver. They lean towards the bugs listed in
[How it works](#how-it-works) below, since those are the ones a refactor
is most likely to reintroduce.

[`ci.yml`](.github/workflows/ci.yml) runs the same two commands on every
pull request, then builds the bundle with `--strict` and checks the
output. `--strict` turns a trim that no longer matches into a build
failure: a pygbag upgrade can change the markup those patterns rewrite,
and without it the build would still succeed and ship an embed with a
grey box around it.

## Publishing

On a push to `main`, CI puts the freshly built `build/web` on a branch in
the portfolio site's repo and opens a pull request. Merging it is what
ships the new build. The demo there is an `<iframe>` served from the
site's `public/` folder so that it is same-origin, so the built files
have to live in that repo rather than on a host of their own.

The pull request is worth almost nothing to read — it is a regenerated
`.tar.gz` and an `index.html` — so review it by opening the Vercel
preview the site builds for the PR and playing the game on it.

Every run reuses one branch, `flappy-bird-build`, rebuilt from the
website's default branch and force-pushed. So a second push to `main`
updates the open pull request rather than opening another one, and the
branch is never more than one commit ahead. Nothing hand-written lives on
it; do not commit to it expecting the commit to survive.

Publishing needs three settings on this repository, under
**Settings > Secrets and variables > Actions**:

| Setting | Kind | Value |
| ------- | ---- | ----- |
| `WEBSITE_REPO` | Variable | `sschroederdev/website` |
| `WEBSITE_PATH` | Variable | `public/flappy` |
| `WEBSITE_REPO_TOKEN` | Secret | A fine-grained PAT |

The built-in `GITHUB_TOKEN` only reaches the repository it runs in, so
writing to another one needs a [fine-grained PAT](https://github.com/settings/personal-access-tokens)
scoped to the website repo alone, with **Contents: Read and write** and
**Pull requests: Read and write**. It expires on whatever date you give
it, and publishing fails until it is renewed.

Until all three are set the publish job fails on its first step, by
design — `actions/checkout` reads an empty `repository:` as *this* repo,
and the step after it deletes the target directory. Lint, tests and the
build are a separate job and keep passing either way.

## Controls

| Input          | Action                    |
| -------------- | ------------------------- |
| `Space` / tap  | Start the game / flap     |
| `R` / tap      | Restart after a game over |

Tapping works the same as the keyboard, so it plays on a touchscreen.

Score a point for every pipe pair you clear. The high score persists until
you close the window.

## How it works

The game runs a single async loop at 60 FPS with three states — `start`,
`play` and `end` — driven by the `Game` class in
[`flappybirdclone.py`](flappybirdclone.py). The same file runs natively
and in the browser; there is no separate web version.

A few implementation details worth knowing if you read the source:

- **The loop is `async` and yields every frame.** A browser tab has one
  thread driving everything, so without an `await asyncio.sleep(0)` per
  frame the page just freezes.
- **`main.py` imports pygame even though it never uses it directly.**
  pygbag scans only the entry file to decide which packages to preload
  into the browser runtime. Drop that import and pygame is never loaded,
  and the game dies on `module 'pygame' has no attribute 'sprite'`.
  Reach for `pygame.sprite.Sprite` by attribute, too — pygbag reads
  `import pygame.sprite` as a third-party package and goes looking for
  it on PyPI.

- **The bird's position is tracked as a float**, not in its `Rect`.
  `pygame.Rect` stores integers, so adding a sub-pixel velocity directly to
  `rect.y` truncates it away and makes gravity lumpy near the top of an arc.
  The float is rounded into the rect only for drawing and collision.
- **The tilt is applied to a throwaway copy of the sprite.** `self.rect`
  stays the size of an unrotated frame, so the hitbox does not grow as the
  bird rotates and the sprite never drifts away from what you can hit.
- **Flapping is driven by `KEYDOWN` events, not `key.get_pressed()`.**
  Polling the held state lets a player hold `Space` and flap automatically
  once per gravity cycle, which trivialises the game.
- **Ground tiles are spaced 528px apart, not by the image width.**
  `ground.png` is 551px wide but its texture repeats every 24px, and 551 is
  not a multiple of 24. 528 is (22 × 24), so tiling at that interval keeps
  the diagonal lines aligned across every seam.
