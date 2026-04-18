#!/usr/bin/env python3
# encoding: utf-8

from importlib import resources

from playsound3 import playsound  # type: ignore[import-not-found]


def play_notification_sound() -> None:
    try:
        sound_path = resources.files("downloadImages").joinpath("assets/completion.wav")
        playsound(str(sound_path), block=True)
    except Exception:
        return
