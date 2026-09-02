"""A Flappy Bird clone built with pygame.

The loop is async so the same file runs both natively and in a browser
under pygbag, which compiles this to WebAssembly. A browser tab has one
thread driving everything, so the loop has to hand control back every
frame via ``await asyncio.sleep(0)`` or the page simply freezes.
"""

import asyncio
import random
from pathlib import Path

import pygame

IMAGE_DIR = Path(__file__).resolve().parent / "images"

WIN_WIDTH = 551
WIN_HEIGHT = 720
FPS = 60
SCROLL_SPEED = 2
TEXT_COLOR = (255, 255, 255)

BIRD_START_POS = (251, 300)
GRAVITY = 0.5
FLAP_VELOCITY = -8
MAX_FALL_SPEED = 7
ROTATION_FACTOR = -7
ANIMATION_FRAMES = 30

GROUND_Y = 520
# ground.png's texture repeats every 24px but the image is 551px wide,
# which is not a multiple of 24. Tiles therefore have to be spaced
# 528px (22 * 24) apart to keep the diagonal lines aligned; spacing them
# by the full image width would put a visible break at every seam.
GROUND_SPACING = 528

PIPE_SPAWN_X = 550
PIPE_TOP_Y_RANGE = (-620, -500)
PIPE_GAP_RANGE = (110, 150)
PIPE_INTERVAL_RANGE = (80, 120)
PIPE_DESPAWN_X = -50

# The bird dies once it falls past this line, just above the ground.
FLOOR_Y = 500

# Frames to ignore input for after a crash, so the tap or keypress that
# killed you does not immediately restart the game on a touchscreen.
RESTART_DELAY = 30


def load_image(name):
    """Load a sprite from the images directory, ready for fast blitting."""
    return pygame.image.load(IMAGE_DIR / name).convert_alpha()


def load_font(size):
    """Load the scoreboard font, falling back to whatever is available.

    pygame ships freesansbold.ttf, but the file is not guaranteed to be
    bundled into every WebAssembly build, and a missing font would
    otherwise take the whole page down on startup.
    """
    try:
        return pygame.font.Font("freesansbold.ttf", size)
    except (OSError, FileNotFoundError):
        return pygame.font.SysFont(None, size)


def load_images():
    """Load every sprite. Must run after the display mode is set."""
    return {
        "background": load_image("background.png"),
        "ground": load_image("ground.png"),
        "pipe_top": load_image("pipe_top.png"),
        "pipe_bottom": load_image("pipe_bottom.png"),
        "game_over": load_image("game_over.png"),
        "start": load_image("start.png"),
        "bird_frames": [
            load_image("bird_up.png"),
            load_image("bird_mid.png"),
            load_image("bird_down.png"),
        ],
    }


def read_input():
    """Drain the event queue for this frame.

    Returns a ``(quit_requested, keys_pressed, tapped)`` triple.
    ``keys_pressed`` holds only keys that went down on this frame, so
    holding a key does not repeat -- that is what stops the bird from
    flapping on its own. ``tapped`` covers a mouse click or a touch,
    which is the only input a phone has.
    """
    quit_requested = False
    keys_pressed = set()
    tapped = False
    for event in pygame.event.get():
        if event.type == pygame.QUIT:
            quit_requested = True
        elif event.type == pygame.KEYDOWN:
            keys_pressed.add(event.key)
        elif event.type in (pygame.MOUSEBUTTONDOWN, pygame.FINGERDOWN):
            tapped = True
    return quit_requested, keys_pressed, tapped


class Bird(pygame.sprite.Sprite):
    """The player-controlled bird."""

    def __init__(self, frames):
        super().__init__()
        self.frames = frames
        self.image = frames[0]
        self.rect = self.image.get_rect(topleft=BIRD_START_POS)
        self.y = float(self.rect.y)
        self.velocity = 0.0
        self.frame_index = 0

    def flap(self):
        """Send the bird upwards."""
        self.velocity = FLAP_VELOCITY

    def update(self):
        self.frame_index = (self.frame_index + 1) % ANIMATION_FRAMES
        frame = self.frame_index * len(self.frames) // ANIMATION_FRAMES
        self.image = self.frames[frame]

        self.velocity = min(self.velocity + GRAVITY, MAX_FALL_SPEED)
        # Track the position as a float and round it into the rect only
        # for drawing. pygame.Rect stores integers, so adding a velocity
        # of less than 1 straight onto rect.y would truncate to no
        # movement at all and make gravity lumpy near the top of an arc.
        self.y += self.velocity
        self.rect.y = round(self.y)

    def draw(self, surface):
        """Draw the bird, tilted to match how fast it is rising/falling."""
        # Rotate a copy for display only. self.rect keeps the size of an
        # unrotated frame, so the hitbox stays honest and the sprite does
        # not drift away from it as the bird tilts.
        rotated = pygame.transform.rotate(
            self.image, self.velocity * ROTATION_FACTOR
        )
        surface.blit(rotated, rotated.get_rect(center=self.rect.center))


class Pipe(pygame.sprite.Sprite):
    """One half of a pipe pair, scrolling right to left."""

    def __init__(self, x, y, image, pipe_type):
        super().__init__()
        self.image = image
        self.rect = self.image.get_rect(topleft=(x, y))
        self.pipe_type = pipe_type
        self.scored = False

    def update(self):
        self.rect.x -= SCROLL_SPEED
        if self.rect.x <= PIPE_DESPAWN_X:
            self.kill()


class Ground(pygame.sprite.Sprite):
    """A single tile of the scrolling ground."""

    def __init__(self, x, y, image):
        super().__init__()
        self.image = image
        self.rect = self.image.get_rect(topleft=(x, y))

    def update(self):
        self.rect.x -= SCROLL_SPEED
        if self.rect.right < 0:
            self.kill()


class Game:
    """Owns the sprites and the score across a whole session."""

    def __init__(self, screen, images):
        self.screen = screen
        self.images = images
        self.clock = pygame.time.Clock()
        self.font = load_font(32)
        self.high_score = 0
        self.state = "start"
        self.reset_round()

    def reset_round(self):
        """Rebuild everything that only lasts for a single attempt."""
        self.bird = Bird(self.images["bird_frames"])
        self.pipes = pygame.sprite.Group()
        self.grounds = pygame.sprite.Group()
        self.grounds.add(Ground(0, GROUND_Y, self.images["ground"]))
        self.pipe_timer = 0
        self.restart_timer = 0
        self.score = 0

    async def run(self):
        """Run the game until the player closes the window."""
        while True:
            self.clock.tick(FPS)
            quit_requested, keys, tapped = read_input()
            if quit_requested:
                return

            if self.state == "start":
                self.update_start(keys, tapped)
            elif self.state == "play":
                self.update_play(keys, tapped)
            else:
                self.update_end(keys, tapped)

            pygame.display.update()
            # Yield to the browser's event loop. On desktop this is a
            # no-op; in the browser it is what keeps the tab responsive.
            await asyncio.sleep(0)

    def update_start(self, keys, tapped):
        self.draw_scene()
        self.screen.blit(
            self.images["start"],
            (WIN_WIDTH // 2 - 100, WIN_HEIGHT // 2 - 200),
        )
        if pygame.K_SPACE in keys or tapped:
            self.state = "play"
            self.bird.flap()

    def update_play(self, keys, tapped):
        if pygame.K_SPACE in keys or tapped:
            self.bird.flap()

        self.bird.update()
        self.pipes.update()
        self.grounds.update()
        self.spawn_ground()
        self.spawn_pipes()
        self.update_score()
        self.draw_scene()

        if self.has_crashed():
            self.high_score = max(self.high_score, self.score)
            self.restart_timer = RESTART_DELAY
            self.state = "end"

    def update_end(self, keys, tapped):
        self.draw_scene()
        self.screen.blit(
            self.images["game_over"],
            (WIN_WIDTH // 2 - 100, WIN_HEIGHT // 2 - 100),
        )
        if self.restart_timer > 0:
            self.restart_timer -= 1
            return
        if pygame.K_r in keys or tapped:
            self.reset_round()
            self.state = "start"

    def spawn_ground(self):
        """Keep the ground tiled across the screen as it scrolls."""
        if self.grounds:
            rightmost = max(ground.rect.x for ground in self.grounds)
        else:
            rightmost = -GROUND_SPACING
        if rightmost <= 0:
            self.grounds.add(
                Ground(
                    rightmost + GROUND_SPACING,
                    GROUND_Y,
                    self.images["ground"],
                )
            )

    def spawn_pipes(self):
        """Drop a new pipe pair in once the spawn timer runs out."""
        if self.pipe_timer > 0:
            self.pipe_timer -= 1
            return

        top_image = self.images["pipe_top"]
        bottom_image = self.images["pipe_bottom"]
        top_y = random.randint(*PIPE_TOP_Y_RANGE)
        # The top pipe hangs off the top of the screen; the bottom one
        # starts a gap below wherever the top pipe ends.
        gap = random.randint(*PIPE_GAP_RANGE)
        bottom_y = top_y + top_image.get_height() + gap

        self.pipes.add(Pipe(PIPE_SPAWN_X, top_y, top_image, "top"))
        self.pipes.add(
            Pipe(PIPE_SPAWN_X, bottom_y, bottom_image, "bottom")
        )
        self.pipe_timer = random.randint(*PIPE_INTERVAL_RANGE)

    def update_score(self):
        """Award a point per pipe pair the bird has fully cleared."""
        for pipe in self.pipes:
            if pipe.pipe_type != "top" or pipe.scored:
                continue
            if pipe.rect.right < self.bird.rect.left:
                pipe.scored = True
                self.score += 1

    def has_crashed(self):
        """Report whether the bird hit a pipe, the ground, or the sky."""
        if pygame.sprite.spritecollideany(self.bird, self.pipes):
            return True
        if pygame.sprite.spritecollideany(self.bird, self.grounds):
            return True
        return self.bird.rect.y < 0 or self.bird.rect.y > FLOOR_Y

    def draw_scene(self):
        # Ground goes on top of the pipes so they look like they come up
        # from behind it rather than sitting over the dirt.
        self.screen.blit(self.images["background"], (0, 0))
        self.pipes.draw(self.screen)
        self.grounds.draw(self.screen)
        self.bird.draw(self.screen)
        self.draw_scores()

    def draw_scores(self):
        score_text = self.font.render(
            f"Score: {self.score}", True, TEXT_COLOR
        )
        high_score_text = self.font.render(
            f"High score: {self.high_score}", True, TEXT_COLOR
        )
        self.screen.blit(score_text, (10, 10))
        self.screen.blit(high_score_text, (10, 50))


async def main():
    pygame.init()
    screen = pygame.display.set_mode((WIN_WIDTH, WIN_HEIGHT))
    pygame.display.set_caption("Flappy Bird!")
    await Game(screen, load_images()).run()
    pygame.quit()


if __name__ == "__main__":
    asyncio.run(main())
