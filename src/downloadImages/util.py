#!/usr/bin/env python3
# encoding: utf-8

import math
import os
import struct
import tempfile
import wave
from importlib import resources

from playsound3 import playsound  # type: ignore[import-not-found]


def _play_sound_file(path: str) -> None:
    try:
        playsound(path, block=True)
    except Exception:
        return


def _write_tone_sequence(
    path: str,
    frequencies: tuple[float, ...],
    note_duration_seconds: float = 0.16,
    pause_duration_seconds: float = 0.04,
    sample_rate: int = 44100,
) -> None:
    amplitude = 12000
    fade_samples = max(1, int(sample_rate * 0.01))
    note_frames = int(sample_rate * note_duration_seconds)
    pause_frames = int(sample_rate * pause_duration_seconds)

    samples = bytearray()
    for index, frequency in enumerate(frequencies):
        for frame in range(note_frames):
            envelope = 1.0
            if frame < fade_samples:
                envelope = frame / fade_samples
            elif note_frames - frame <= fade_samples:
                envelope = (note_frames - frame) / fade_samples

            sample = int(
                amplitude
                * envelope
                * math.sin((2.0 * math.pi * frequency * frame) / sample_rate)
            )
            samples.extend(struct.pack("<h", sample))

        if index < len(frequencies) - 1:
            samples.extend(b"\x00\x00" * pause_frames)

    with wave.open(path, "wb") as wav_file:
        wav_file.setnchannels(1)
        wav_file.setsampwidth(2)
        wav_file.setframerate(sample_rate)
        wav_file.writeframes(samples)


def play_notification_sound() -> None:
    try:
        sound_path = resources.files("downloadImages").joinpath("assets/completion.wav")
        _play_sound_file(str(sound_path))
    except Exception:
        return


def play_warning_pause_sound() -> None:
    temp_path = None
    try:
        file_descriptor, temp_path = tempfile.mkstemp(suffix=".wav")
        os.close(file_descriptor)
        _write_tone_sequence(temp_path, (587.33, 493.88, 392.0))
        _play_sound_file(temp_path)
    except Exception:
        return
    finally:
        if temp_path and os.path.exists(temp_path):
            try:
                os.remove(temp_path)
            except OSError:
                pass
