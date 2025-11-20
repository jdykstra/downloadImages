# AI Coding Agent Instructions for downloadImages

## Project Overview
This Python application downloads images and videos from DCF volumes (SD cards) to local directories, with optional integration to DaVinci Resolve and Adobe Lightroom. It handles RAW photos, JPEGs, and video files with metadata preservation.

## Architecture & Key Components

### Core Files
- **`downloadImages/downloadImages.py`**: Main CLI application with download logic
- **`downloadImages/python_get_resolve.py`**: DaVinci Resolve API integration wrapper (**Do not modify this file; it is supplied by Blackmagic Design.**)
- **`requirements.txt`**: Single dependency (progressbar2)

### Data Flow
1. **Volume Detection**: Scans `/Volumes` (macOS) or drive letters (Windows) for DCIM directories
2. **File Discovery**: Recursively walks DCIM structure, catalogs images by base filename
3. **Duplicate Checking**: Compares file sizes to avoid re-copying existing files
4. **Copy with Progress**: Chunked file copying with visual progress bar
5. **Metadata Creation**: Generates XMP sidecar files for images with descriptions
6. **Integration**: Optional launch of Lightroom or Resolve for media ingestion

## Critical Patterns & Conventions

### File Type Handling
```python
jpegExtensions = ['JPG']
imageExtensions = jpegExtensions + ['NEF']  # RAW files
videoExtensions = ['MOV', 'MP4']
```
- Images get XMP sidecars; videos do not
- Filenames normalized by removing underscores (Nikon convention)
- Case-insensitive extension matching

### Platform-Specific Code
```python
if 'darwin' in sys.platform:
    # macOS: UF_IMMUTABLE flags, diskutil eject, caffeinate
else:
    # Windows: Read-only attributes, different Lightroom path
```

### Error Handling
- CLIError exceptions for user-facing errors
- Graceful cleanup on interruption (terminates caffeinate process)
- File locking detection via OS-specific immutable flags

### Resolve Integration
```python
resolve = GetResolve()
project = resolve.GetProjectManager().GetCurrentProject()
mediaPool = project.GetMediaPool()
mediaPool.ImportMediaFiles(path)  # Only imports to current project
```

## Development Workflows

### Testing Setup
- VSCode launch configs in `.vscode/launch.json` with test directories
- Test destination: `test_destination_directory/`
- Sample command: `python downloadImages.py -t "test" /path/to/dest`

### Build & Run
- No build step required (pure Python)
- Install dependencies: `pip install -r requirements.txt`
- Run directly: `python downloadImages/downloadImages.py [options] <destinations>`

### Cross-Platform Development
- Primary development on macOS, secondary Windows support
- Test on both platforms before commits
- Platform detection via `sys.platform` checks

## Integration Points

### DaVinci Resolve
- Requires Resolve installation with scripting enabled
- Uses Blackmagic's `DaVinciResolveScript` module
- Automatically finds module in standard installation paths
- Imports media to current project's media pool

### Lightroom Integration
- Launches Lightroom application asynchronously
- Platform-specific application paths hardcoded
- Opens destination directory for manual import

### File System Operations
- Preserves file modification times (`shutil.copystat`)
- Handles locked files (camera write-protection)
- macOS: `sync` command + `diskutil unmount` after operations
- Progress tracking with custom ETA display

## Common Development Tasks

### Adding New File Types
1. Add extension to appropriate list (`imageExtensions`, `videoExtensions`)
2. Update XMP sidecar logic if needed
3. Test duplicate detection and progress tracking

### Platform-Specific Features
1. Add platform check: `if 'darwin' in sys.platform:`
2. Implement macOS version first
3. Add Windows equivalent
4. Test on both platforms

### Resolve API Extensions
1. Import `python_get_resolve.GetResolve()`
2. Get current project and media pool
3. Use Resolve's Python API documentation
4. Handle API failures gracefully

## Code Quality Notes
- Uses `argparse` for CLI with custom help formatting
- Progress bar customization for clean ETA display
- Exception handling with proper cleanup
- No external configuration files (all hardcoded paths)
- MIT licensed, case-insensitive filesystem handling
- **Enclosed functions must be defined at the start of their enclosing function** - nested helper functions should appear immediately after the enclosing function's docstring and before any other code</content>
<parameter name="filePath">/Volumes/nobackup-cs/downloadImages/.github/copilot-instructions.md