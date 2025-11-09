#!/usr/bin/env python3
# encoding: utf-8

import sys
import os
import time
import subprocess

from python_get_resolve import GetResolve

""" Project preset used.  """
INGRESS_PROJECT_PRESET="JWD"

def _launchResolve():
    """
    Launch DaVinci Resolve if it's not already running and wait for it to be available.
    """

    # First check if Resolve is already available
    resolve = GetResolve()
    if resolve is not None:
        return resolve

    # Resolve is not available, launch it
    if 'darwin' in sys.platform:
        # macOS
        try:
            subprocess.Popen(['open', '-a', 'DaVinci Resolve'])
        except Exception as e:
            print(f"Error launching DaVinci Resolve on macOS: {e}")
            return False
    else:
        # Windows
        resolve_path = "C:\\Program Files\\Blackmagic Design\\DaVinci Resolve\\Resolve.exe"
        try:
            subprocess.Popen([resolve_path])
        except Exception as e:
            print(f"Error launching DaVinci Resolve on Windows: {e}")
            return False

    # Wait for Resolve to start up, retrying GetResolve() every 0.5 seconds for up to 20 seconds
    start_time = time.time()
    while time.time() - start_time < 20.0:
        resolve = GetResolve()
        if resolve is not None:
            return resolve
        time.sleep(0.5)

    # Timeout reached
    print("Error: DaVinci Resolve did not respond within 20 seconds")
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
        print(f"Could not set project to '{INGRESS_PROJECT_PRESET}'")
        return None  

    # Save project and return
    try:
        projectManager.SaveProject()
    except Exception:
        # Not critical if save fails here
        pass

    return new_project


def _ensure_timeline_exists(project, timeline_name):
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
        new_timeline = project.AddTimeline(timeline_name)
        return new_timeline
    except Exception as e:
        print(f"Error ensuring timeline '{timeline_name}' exists: {e}")
        return None


def ingestMotionClips(tag, dayStamp, description, path):
    
    resolve = _launchResolve()
    if not resolve:
        return False
    
    print(f"Ingesting video to Resolve project {tag}.")
    
    project = _find_or_create_project(resolve, tag)
    if not project:
        return False
    
    mediaPool = project.GetMediaPool()
    if not mediaPool:
        print(f"Failed to get media pool from project '{tag}'")
        return False
    
    try:
        mediaStorage = resolve.GetMediaStorage()
        if not mediaStorage:
            print(f"Failed to get media storage from Resolve")
            return False
        
        clips = mediaStorage.AddItemListToMediaPool([path])
        if not clips:
            print(f"Failed to import media files from directory: {path}")
            return False
    except Exception as e:
        print(f"Exception while importing media files: {e}")
        return False
    
    # Create or get bin/folder named after dayStamp
    try:
        rootFolder = mediaPool.GetRootFolder()
        if not rootFolder:
            print("Failed to get root folder from media pool")
            return False
        
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
                print(f"Failed to create folder '{dayStamp}'")
                return False
        
        # Move imported clips to the target folder
        if clips:
            success = mediaPool.MoveClips(clips, targetFolder)
            if not success:
                print(f"Failed to move clips to folder '{dayStamp}'")
                return False
    
    except Exception as e:
        print(f"Exception while organizing clips into folder: {e}")
        return False
    
    # Ensure a timeline exists for this day
    timeline = _ensure_timeline_exists(project, dayStamp)
    if not timeline:
        print(f"Failed to ensure timeline '{dayStamp}' exists")
        return False
    
    # Append the imported clips to the timeline
    try:
        project.SetCurrentTimeline(timeline)
        if clips:
            success = timeline.AppendToTrack(1, clips)  # Append to video track 1
            if not success:
                print(f"Failed to append clips to timeline '{dayStamp}'")
                return False
    except Exception as e:
        print(f"Exception while appending clips to timeline: {e}")
        return False
    
    return True