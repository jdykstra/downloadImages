#!/usr/bin/env python3
# encoding: utf-8
"""
Application paths for external tools used by downloadImages.

This module centralizes the paths and application names for Lightroom and DaVinci Resolve
across different platforms.
"""

import sys

# Lightroom application paths
if 'darwin' in sys.platform:
    LIGHTROOM_APP = "Adobe Lightroom Classic"
else:
    LIGHTROOM_APP = r"C:\Program Files\Adobe\Adobe Lightroom Classic\Lightroom.exe"

# DaVinci Resolve application paths
if 'darwin' in sys.platform:
    RESOLVE_APP_NAME = "DaVinci Resolve"
    RESOLVE_EXE_PATH = None  # Not used on macOS
else:
    RESOLVE_APP_NAME = None  # Not used on Windows
    RESOLVE_EXE_PATH = r"C:\Program Files\Blackmagic Design\DaVinci Resolve\Resolve.exe"
