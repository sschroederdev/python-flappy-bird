# python-flappy-bird

A Flappy Bird clone written in Python with pygame.

![Python](https://img.shields.io/badge/python-3.11-blue)
![pygame](https://img.shields.io/badge/pygame-2.6-green)

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
