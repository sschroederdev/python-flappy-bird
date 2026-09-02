"""Entry point for the WebAssembly build.

pygbag looks for a ``main.py`` at the root of the folder it is pointed
at, so this hands off to the game module. Run ``flappybirdclone.py``
directly for the desktop version.

The pygame import matters even though the game module does its own.
pygbag scans *only this file* to decide which packages to preload into
the browser runtime, so without it pygame is never properly loaded and
importing the game module dies on "module 'pygame' has no attribute
'sprite'".
"""

import asyncio

import pygame

from flappybirdclone import main

pygame.init()
asyncio.run(main())
