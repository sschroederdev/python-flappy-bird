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

## Controls

| Key     | Action                        |
| ------- | ----------------------------- |
| `Space` | Start the game / flap         |
| `R`     | Restart after a game over     |

Score a point for every pipe pair you clear. The high score persists until
you close the window.

## How it works

The game runs a single loop at 60 FPS with three states — `start`, `play`
and `end` — driven by the `Game` class in
[`flappybirdclone.py`](flappybirdclone.py).

A few implementation details worth knowing if you read the source:

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
