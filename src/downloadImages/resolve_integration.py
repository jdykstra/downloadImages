#!/usr/bin/env python3
# encoding: utf-8

import os
import subprocess
import sys
import time
from datetime import datetime

from .apppaths import RESOLVE_APP_NAME, RESOLVE_EXE_PATH
from .python_get_resolve import GetResolve
from .sourceimages import MOTION_FILE_TYPES
from .video_metadata import ExtractedVideoMetadata, extract_video_metadata_batch

""" Project preset used.  """
INGRESS_PROJECT_PRESET="JWD"

def _launchResolve():
    """
    Launch DaVinci Resolve if it's not already running and wait for it to be available.
    """

    ATTEMPT_SECONDS = 60.0

    while True:
        # First check if Resolve is already available
        resolve = GetResolve()
        if resolve is not None:
            return resolve

        # Resolve is not available, launch it
        if 'darwin' in sys.platform:
            # macOS
            try:
                subprocess.Popen(['open', '-a', RESOLVE_APP_NAME])
            except Exception as e:
                print(f"Error launching DaVinci Resolve on macOS: {e}")
                return False
        else:
            # Windows
            try:
                subprocess.Popen([RESOLVE_EXE_PATH])
            except Exception as e:
                print(f"Error launching DaVinci Resolve on Windows: {e}")
                return False

        # Wait for Resolve to start up, retrying GetResolve() every 0.5 seconds for up to 20 seconds
        start_time = time.time()
        while time.time() - start_time < ATTEMPT_SECONDS:
            resolve = GetResolve()
            if resolve is not None:
                return resolve
            time.sleep(0.5)

        # Timeout reached - ask user what to do
        print(f"\nDaVinci Resolve did not respond within {ATTEMPT_SECONDS} seconds.")
        while True:
            try:
                response = input("Would you like to retry (r) or abort (a)? ").strip().lower()
                if response in ['r', 'retry']:
                    print("Retrying...")
                    break  # Break inner loop to retry outer loop
                elif response in ['a', 'abort']:
                    print("Aborting Resolve launch.")
                    return None
                else:
                    print("Please enter 'r' for retry or 'a' for abort.")
            except (EOFError, KeyboardInterrupt):
                print("\nAborting Resolve launch.")
                return None


def _find_or_create_project(resolve, tag: str):
    """
    Find a Resolve project whose name is the given `tag` substring.
    If no matching project is found, create a new project named exactly as `tag`.

    Returns the project object on success, or None on failure.
    """
    def search_current_folder():
        try:
            projects = projectManager.GetProjectListInCurrentFolder()
        except Exception:
            projects = []
        for pname in projects:
            try:
                if tag == pname:
                    return projectManager.GetCurrentProject()
            except Exception:
                continue
        return None

    def visit_folder():
        # Search projects in current folder
        found = search_current_folder()
        if found:
            return found
        # Recurse into subfolders
        try:
            folders = projectManager.GetFolderListInCurrentFolder()
        except Exception:
            folders = []
        for f in folders:
            try:
                if projectManager.OpenFolder(f):
                    result = visit_folder()
                    if result:
                        return result
                    projectManager.GotoParentFolder()
            except Exception:
                # ignore folder traversal errors and continue
                try:
                    projectManager.GotoParentFolder()
                except Exception:
                    pass
        return None

    projectManager = resolve.GetProjectManager()
    if projectManager is None:
        print("Could not obtain ProjectManager from Resolve.")
        return None

    # Start from root and recursively search
    try:
        projectManager.GotoRootFolder()
    except Exception:
        pass

    project = visit_folder()
    if project is not None:
        return project

    # Not found: create a new project named as the tag
    try:
        new_project = projectManager.CreateProject(tag)
    except Exception as e:
        print(f"Failed to create project '{tag}': {e}")
        return None

    if not new_project:
        print(f"CreateProject returned falsy value for '{tag}'")
        return None

    if not new_project.SetPreset(INGRESS_PROJECT_PRESET):
        print(f"Could not set project to preset '{INGRESS_PROJECT_PRESET}'")
        return None  

    # Save project and return
    try:
        projectManager.SaveProject()
    except Exception:
        # Not critical if save fails here
        pass

    return new_project


def _ensure_timeline_exists(mediaPool, project, timeline_name):
    """
    Check if a timeline with the given name exists in the project.
    If not, create a new timeline with that name.
    
    Returns the timeline object.
    """
    try:
        timeline_count = project.GetTimelineCount()
        for i in range(1, timeline_count + 1):  # Timelines are 1-indexed
            timeline = project.GetTimelineByIndex(i)
            if timeline and timeline.GetName() == timeline_name:
                return timeline
        
        # Timeline not found, create it
        new_timeline = mediaPool.CreateEmptyTimeline(timeline_name)
        return new_timeline
    except Exception as e:
        print(f"Error ensuring timeline '{timeline_name}' exists: {e}")
        return None


class ResolveError(Exception):
    """Exception raised for DaVinci Resolve integration errors."""
    pass


def _apply_clip_metadata(clip, metadata: ExtractedVideoMetadata) -> None:
    """Best-effort metadata update for a Resolve MediaPoolItem."""

    for key, value in metadata.resolve_metadata.items():
        try:
            clip.SetMetadata(key, value)
        except Exception:
            continue

    if metadata.third_party_metadata:
        try:
            if clip.SetThirdPartyMetadata(metadata.third_party_metadata):
                return
        except Exception:
            pass

        for key, value in metadata.third_party_metadata.items():
            try:
                clip.SetThirdPartyMetadata(key, value)
            except Exception:
                continue


def _extract_motion_metadata(path: str, description: str | None) -> dict[str, ExtractedVideoMetadata]:
    motion_files = [
        entry.path
        for entry in os.scandir(path)
        if entry.is_file()
        and os.path.splitext(entry.name)[1][1:].upper() in MOTION_FILE_TYPES
    ]

    if not motion_files:
        return {}

    try:
        return extract_video_metadata_batch(motion_files, description)
    except Exception as exc:
        print(f"Warning: could not extract motion metadata with exiftool: {exc}")
        return {}


def ingestMotionClips(tag, dayStamp, description, path):

    # This properly handles the case where a previous ingest failed (e.g. because Resolve
    # displayed its "update available" dialog), but we get run again on the same target
    # directory (perhaps because a new card is downloaded).  os.scandir() will pick up
    # the motion files downloaded previously.  This means it will also pick up files
    # that may have been part of a previous successful ingress, but mediapool.ImportMedia()
    # apparently handles that gracefully.
    
    try:
        metadata_by_path = _extract_motion_metadata(path, description)

        resolve = _launchResolve()
        if not resolve:
            raise ResolveError("Failed to launch or connect to DaVinci Resolve")
            
        project = _find_or_create_project(resolve, tag)
        if not project:
            raise ResolveError(f"Failed to find or create project '{tag}'")
        
        mediaPool = project.GetMediaPool()
        if not mediaPool:
            raise ResolveError(f"Failed to get media pool from project '{tag}'")
        
        # Create or get bin/folder named after dayStamp
        try:
            rootFolder = mediaPool.GetRootFolder()
            if not rootFolder:
                raise ResolveError("Failed to get root folder from media pool")
            
            # Check if folder already exists
            targetFolder = None
            subFolders = rootFolder.GetSubFolderList()
            for folder in subFolders:
                if folder.GetName() == dayStamp:
                    targetFolder = folder
                    break
            
            # Create folder if it doesn't exist
            if not targetFolder:
                targetFolder = mediaPool.AddSubFolder(rootFolder, dayStamp)
                if not targetFolder:
                    raise ResolveError(f"Failed to create folder '{dayStamp}'")

            existing_clip_names = set()
            try:
                existing_clips = targetFolder.GetClipList() or []
                existing_clip_names = {
                    clip.GetName().upper()
                    for clip in existing_clips
                    if clip and clip.GetName()
                }
            except Exception:
                existing_clip_names = set()

            files_to_import = [
                entry.path
                for entry in os.scandir(path)
                if entry.is_file()
                and os.path.splitext(entry.name)[1][1:].upper() in MOTION_FILE_TYPES
                and entry.name.upper() not in existing_clip_names
            ]

            if not files_to_import:
                files_to_import = []
            
            # Move imported clips to the target folder
            clips = []
            if files_to_import:
                clips = mediaPool.ImportMedia(files_to_import)
                if not clips:
                    raise ResolveError(f"Resolve failed to import media files from directory: {path}")

                success = mediaPool.MoveClips(clips, targetFolder)
                if not success:
                    raise ResolveError(f"Failed to move clips to folder '{dayStamp}'")

            try:
                target_clips = targetFolder.GetClipList() or []
            except Exception:
                target_clips = clips or []

            clips_by_name = {
                clip.GetName().upper(): clip
                for clip in target_clips
                if clip and clip.GetName()
            }

            for source_path, extracted_metadata in metadata_by_path.items():
                clip_name = os.path.basename(source_path).upper()
                clip = clips_by_name.get(clip_name)
                if clip is None:
                    continue
                _apply_clip_metadata(clip, extracted_metadata)
        
        except Exception as e:
            raise ResolveError(f"Exception while organizing clips into folder: {e}")
        
        # Ensure a timeline exists for this day
        timeline = _ensure_timeline_exists(mediaPool, project, dayStamp)
        if not timeline:
            raise ResolveError(f"Failed to create timeline '{dayStamp}'")
        
        # Set that timeline as the current timeline
        if not project.SetCurrentTimeline(timeline):
            raise ResolveError(f"Failed to set current timeline to '{dayStamp}'")
        
        # Sort by start timecode, then by date created as a fallback.
        def sort_key(clip):
            date_str = clip.GetClipProperty("Date Created") or ""
            tc_str = clip.GetClipProperty("Start TC") or ""

            def parse_timecode(value):
                try:
                    hours, minutes, seconds_and_frames = value.split(":", 2)
                    seconds, frames = seconds_and_frames.split(";", 1)
                    return (int(hours), int(minutes), int(seconds), int(frames))
                except Exception:
                    return (999, 999, 999, 999)

            try:
                date_obj = datetime.strptime(date_str, "%a %b %d %Y %H:%M:%S")
            except ValueError:
                date_obj = datetime.min

            return (parse_timecode(tc_str), date_obj)
        
        sorted_clips = sorted(clips, key=sort_key)
        
        # Append all sorted clips to the new timeline
        try:
            for clip in sorted_clips:
                mediaPool.AppendToTimeline(clip)
        except Exception as e:
            raise ResolveError(f"Exception while appending clips to timeline: {e}")
        
        return
        
    except ResolveError:
        raise  # Re-raise our custom exceptions
    except Exception as e:
        raise ResolveError(f"Unexpected error in ingestMotionClips: {e}")