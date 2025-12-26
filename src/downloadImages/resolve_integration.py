#!/usr/bin/env python3
# encoding: utf-8

import os
import subprocess
import sys
import time

from .apppaths import RESOLVE_APP_NAME, RESOLVE_EXE_PATH
from .python_get_resolve import GetResolve

""" Project preset used.  """
INGRESS_PROJECT_PRESET="JWD"

def _launchResolve():
    """
    Launch DaVinci Resolve if it's not already running and wait for it to be available.
    """

    ATTEMPT_SECONDS = 30.0

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


def ingestMotionClips(tag, dayStamp, description, path):
    
    try:
        resolve = _launchResolve()
        if not resolve:
            raise ResolveError("Failed to launch or connect to DaVinci Resolve")
            
        project = _find_or_create_project(resolve, tag)
        if not project:
            raise ResolveError(f"Failed to find or create project '{tag}'")
        
        mediaPool = project.GetMediaPool()
        if not mediaPool:
            raise ResolveError(f"Failed to get media pool from project '{tag}'")
        
        try:
            mediaStorage = resolve.GetMediaStorage()
            if not mediaStorage:
                raise ResolveError("Failed to get media storage from Resolve")
            
            clips = mediaStorage.AddItemListToMediaPool([path])
            if not clips:
                raise ResolveError(f"Failed to import media files from directory: {path}")
        except Exception as e:
            raise ResolveError(f"Exception while importing media files: {e}")
        
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
            
            # Move imported clips to the target folder
            success = mediaPool.MoveClips(clips, targetFolder)
            if not success:
                raise ResolveError(f"Failed to move clips to folder '{dayStamp}'")
        
        except Exception as e:
            raise ResolveError(f"Exception while organizing clips into folder: {e}")
        
        # Ensure a timeline exists for this day
        timeline = _ensure_timeline_exists(mediaPool, project, dayStamp)
        if not timeline:
            raise ResolveError(f"Failed to create timeline '{dayStamp}'")
        
        # Set that timeline as the current timeline
        if not project.SetCurrentTimeline(timeline):
            raise ResolveError(f"Failed to set current timeline to '{dayStamp}'")
        
        # Sort by name
        clips = sorted(clips, key = lambda clip : clip.GetClipProperty("File Name"))

        # Append the sorted clips to the timeline
        try:
            for clip in clips:
                mediaPool.AppendToTimeline(clip)
        except Exception as e:
            raise ResolveError(f"Exception while appending clips to timeline: {e}")
        
        return
        
    except ResolveError:
        raise  # Re-raise our custom exceptions
    except Exception as e:
        raise ResolveError(f"Unexpected error in ingestMotionClips: {e}")