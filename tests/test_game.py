"""Headless tests for the game logic.

These drive the state machine a frame at a time rather than running
``Game.run``, which loops until the window closes. SDL's dummy driver
gives us a real display surface without a window, so sprites still
convert and blit exactly as they do on screen.

The cases here are deliberately weighted towards the bugs called out in
the README: they are the ones a refactor is most likely to reintroduce.
"""

import os
import unittest
from pathlib import Path

# Must be set before pygame initialises its video backend. CI exports the
# same values; setting them here keeps the suite runnable on a desktop.
os.environ.setdefault("SDL_VIDEODRIVER", "dummy")
os.environ.setdefault("SDL_AUDIODRIVER", "dummy")

import pygame  # noqa: E402

import flappybirdclone as game  # noqa: E402

PROJECT_DIR = Path(__file__).resolve().parent.parent


class GameTestCase(unittest.TestCase):
    """Shared display surface and sprites for the whole suite."""

    @classmethod
    def setUpClass(cls):
        pygame.init()
        cls.screen = pygame.display.set_mode(
            (game.WIN_WIDTH, game.WIN_HEIGHT)
        )
        cls.images = game.load_images()

    @classmethod
    def tearDownClass(cls):
        pygame.quit()

    def setUp(self):
        pygame.event.clear()
        self.game = game.Game(self.screen, self.images)


class TestBirdPhysics(GameTestCase):

    def test_position_accumulates_as_a_float(self):
        """Sub-pixel velocity must not be truncated away.

        pygame.Rect stores integers, so adding a velocity of less than 1
        straight onto rect.y would round to no movement at all. The first
        four frames of a fall are +0.5, +1.0, +1.5 and +2.0.
        """
        bird = self.game.bird
        start = bird.y
        for _ in range(4):
            bird.update()
        self.assertAlmostEqual(bird.y, start + 5.0)
        self.assertEqual(bird.rect.y, round(bird.y))

    def test_fall_speed_is_capped(self):
        bird = self.game.bird
        for _ in range(200):
            bird.update()
        self.assertEqual(bird.velocity, game.MAX_FALL_SPEED)

    def test_flap_reverses_the_fall(self):
        bird = self.game.bird
        for _ in range(10):
            bird.update()
        self.assertGreater(bird.velocity, 0)
        bird.flap()
        falling_y = bird.y
        bird.update()
        self.assertLess(bird.y, falling_y)

    def test_tilting_does_not_grow_the_hitbox(self):
        """The rotation is applied to a throwaway copy, not to self.rect.

        If the rotated surface were assigned back, the hitbox would swell
        as the bird tilts and the player would clip pipes they missed.
        """
        bird = self.game.bird
        unrotated = bird.rect.copy()
        bird.velocity = game.MAX_FALL_SPEED
        bird.draw(self.screen)
        self.assertEqual(bird.rect.size, unrotated.size)
        self.assertEqual(bird.rect.topleft, unrotated.topleft)


class TestInput(GameTestCase):

    def test_only_fresh_keydowns_count(self):
        """Holding a key must not flap once per gravity cycle.

        read_input reports KEYDOWN events, not the held key state, so a
        held key produces input on exactly one frame.
        """
        pygame.event.post(
            pygame.event.Event(pygame.KEYDOWN, key=pygame.K_SPACE)
        )
        _, keys, _ = game.read_input()
        self.assertIn(pygame.K_SPACE, keys)

        # Next frame the key is still physically down, but with no new
        # event to report there is nothing in the queue.
        _, keys, _ = game.read_input()
        self.assertNotIn(pygame.K_SPACE, keys)

    def test_touch_and_click_both_register_as_a_tap(self):
        for event_type in (pygame.MOUSEBUTTONDOWN, pygame.FINGERDOWN):
            with self.subTest(event_type=event_type):
                pygame.event.clear()
                pygame.event.post(pygame.event.Event(event_type))
                _, _, tapped = game.read_input()
                self.assertTrue(tapped)

    def test_quit_is_reported(self):
        pygame.event.post(pygame.event.Event(pygame.QUIT))
        quit_requested, _, _ = game.read_input()
        self.assertTrue(quit_requested)


class TestStateMachine(GameTestCase):

    def start_playing(self):
        self.game.update_start({pygame.K_SPACE}, False)

    def crash(self):
        """Let the bird fall until the round ends."""
        for _ in range(600):
            self.game.update_play(set(), False)
            if self.game.state == "end":
                return
        self.fail("the bird never crashed")

    def test_space_starts_the_game(self):
        self.assertEqual(self.game.state, "start")
        self.start_playing()
        self.assertEqual(self.game.state, "play")
        # The keypress that starts the game is also the first flap.
        self.assertEqual(self.game.bird.velocity, game.FLAP_VELOCITY)

    def test_tap_starts_the_game(self):
        self.game.update_start(set(), True)
        self.assertEqual(self.game.state, "play")

    def test_bird_stays_put_before_the_game_starts(self):
        y = self.game.bird.y
        for _ in range(30):
            self.game.update_start(set(), False)
        self.assertEqual(self.game.bird.y, y)

    def test_falling_ends_the_round(self):
        self.start_playing()
        self.crash()

    def test_restart_delay_swallows_the_fatal_input(self):
        """The tap that killed you must not also restart the round.

        On a touchscreen the crash and the next frame's input are the
        same gesture, so the end state ignores input for RESTART_DELAY
        frames.
        """
        self.start_playing()
        self.crash()

        self.game.update_end(set(), True)
        self.assertEqual(self.game.state, "end")

        for _ in range(game.RESTART_DELAY):
            self.game.update_end(set(), False)
        self.game.update_end({pygame.K_r}, False)
        self.assertEqual(self.game.state, "start")


class TestScoring(GameTestCase):

    def add_top_pipe(self, x):
        pipe = game.Pipe(x, -560, self.images["pipe_top"], "top")
        self.game.pipes.add(pipe)
        return pipe

    def cleared_x(self, image):
        """The x at which a pipe of this image sits just behind the bird."""
        return self.game.bird.rect.left - image.get_width() - 1

    def test_a_cleared_pipe_scores_once(self):
        pipe = self.add_top_pipe(self.cleared_x(self.images["pipe_top"]))
        self.assertLess(pipe.rect.right, self.game.bird.rect.left)
        self.game.update_score()
        self.game.update_score()
        self.assertEqual(self.game.score, 1)
        self.assertTrue(pipe.scored)

    def test_an_uncleared_pipe_does_not_score(self):
        self.add_top_pipe(game.PIPE_SPAWN_X)
        self.game.update_score()
        self.assertEqual(self.game.score, 0)

    def test_the_bottom_pipe_is_not_counted_separately(self):
        """A pair is worth one point, so only the top half is scored."""
        image = self.images["pipe_bottom"]
        bottom = game.Pipe(self.cleared_x(image), 400, image, "bottom")
        self.game.pipes.add(bottom)
        # Cleared on the same terms the top half would have scored on.
        self.assertLess(bottom.rect.right, self.game.bird.rect.left)
        self.game.update_score()
        self.assertEqual(self.game.score, 0)

    def test_high_score_survives_a_restart(self):
        self.game.update_start({pygame.K_SPACE}, False)
        self.game.score = 7
        for _ in range(600):
            self.game.update_play(set(), False)
            if self.game.state == "end":
                break
        self.assertEqual(self.game.state, "end")
        self.assertEqual(self.game.high_score, 7)

        for _ in range(game.RESTART_DELAY + 1):
            self.game.update_end(set(), False)
        self.game.update_end({pygame.K_r}, False)
        self.assertEqual(self.game.state, "start")
        self.assertEqual(self.game.score, 0)
        self.assertEqual(self.game.high_score, 7)


class TestGround(GameTestCase):

    def test_tiles_land_on_the_texture_repeat(self):
        """ground.png repeats every 24px but the image is 551px wide.

        Spacing tiles by the image width would put a visible break in the
        diagonal lines at every seam.
        """
        self.assertEqual(game.GROUND_SPACING % 24, 0)
        self.assertLess(game.GROUND_SPACING, game.WIN_WIDTH)

    def test_the_ground_stays_tiled_across_the_screen(self):
        frames = game.GROUND_SPACING * 2 // game.SCROLL_SPEED
        for _ in range(frames):
            self.game.grounds.update()
            self.game.spawn_ground()
            covered = max(
                (ground.rect.right for ground in self.game.grounds),
                default=0,
            )
            self.assertGreaterEqual(covered, game.WIN_WIDTH)


class TestWebEntryPoint(unittest.TestCase):
    """Guards on the two pygbag traps documented in the README."""

    def test_entry_point_imports_pygame(self):
        """pygbag scans only main.py to decide what to preload.

        Without a bare ``import pygame`` there, pygame is never properly
        loaded and the browser build dies on "module 'pygame' has no
        attribute 'sprite'".
        """
        source = (PROJECT_DIR / "main.py").read_text(encoding="utf-8")
        self.assertRegex(source, r"(?m)^import pygame$")

    def test_no_submodule_imports_of_pygame(self):
        """pygbag reads ``import pygame.x`` as a PyPI package.

        It then goes looking for it and the build fails, so submodules
        have to be reached by attribute off the top-level import.
        """
        for name in ("main.py", "flappybirdclone.py"):
            with self.subTest(name=name):
                source = (PROJECT_DIR / name).read_text(encoding="utf-8")
                self.assertNotRegex(source, r"(?m)^\s*import pygame\.")
                self.assertNotRegex(source, r"(?m)^\s*from pygame\.")


if __name__ == "__main__":
    unittest.main()
