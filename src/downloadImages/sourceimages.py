# File-global source image database and summary variables
import os
import stat
import sys
from dataclasses import dataclass, field

JPEG_FILE_TYPES: list[str] = ['JPG']
STILL_FILE_TYPES: list[str] = JPEG_FILE_TYPES + ['NEF']
MOTION_FILE_TYPES: list[str] = ['MOV', 'MP4', 'NEV']


class CliError(Exception):
    '''Generic exception to raise and log different fatal errors.'''

    def __init__(self, msg):
        super().__init__(type(self))
        self.msg = "ERROR: %s" % msg

    def __str__(self):
        return self.msg

    def __unicode__(self):
        return self.msg


@dataclass
class ImageDB:
    db: dict[str, 'SourceImage'] = field(default_factory=dict)
    total_images: int = 0
    file_type_count: dict[str, int] = field(default_factory=dict)
    locked_file_count: int = 0
    total_to_transfer: int = 0
    near_rollover: bool = False
    rollover_occurred: bool = False


@dataclass
class SourceImage:
    src_filename: str
    src_path: str
    extensions: list[str]
    file_locked: bool
    size: int
    dst_filename: str

    def add_file_extension(self, extension: str) -> None:
        self.extensions.append(extension)

    def contains_file_extension(self, extension: str) -> bool:
        return extension in self.extensions


# Find potential source DCF volumes, returning a list of (name, path) tuples.
def find_source_volume() -> list[tuple[str, str]]:
    vollist = []
    if 'darwin' in sys.platform:
        for d in os.listdir("/Volumes"):
            if not os.path.isdir(os.path.join("/Volumes", d)):
                continue
            tp = os.path.join(os.path.join("/Volumes", d), "DCIM")
            if os.path.isdir(tp):
                vollist.append((d, tp))
    else:
        dl = 'ABCDEFGHIJKLMNOPQRSTUVWXYZ'
        drives = ['%s:' % d for d in dl if os.path.exists('%s:' % d)]
        for d in drives:
            tp = os.path.join(d, "DCIM")
            if os.path.isdir(tp):
                vollist.append((d, tp))
    return vollist


# Return a dictionary describing all of the image files on the source, indexed by the image name.
def find_source_images(src: str, download_locked_only: bool) -> ImageDB:
    image_db = ImageDB()

    # Enumerate the image files on the source volume.
    for dirpath, _, files in os.walk(src):
        for f in files:
            # Ignore files that are unlikely to be camera image files,
            # including hidden files.
            if f.startswith("."):
                continue
            fparts = f.split(".")
            if len(fparts) != 2:
                continue
            src_filename = fparts[0]
            extension = fparts[-1]
            # Remove underscores used by Nikon
            dst_filename = src_filename.replace("_", "")
            image_name = dst_filename.upper()
            ext_upper = extension.upper()
            if ext_upper not in STILL_FILE_TYPES + MOTION_FILE_TYPES:
                continue

            # If write protect was set on an image by the camera, it will appear on
            # MacOS as the user-immutable flag.  FWIW, this flag can be seen using
            # "ls -lhdO".  On Windows, we just look for read-only.
            src_full_path = os.path.join(dirpath, src_filename + "." + extension)
            stat_info = os.stat(src_full_path)
            if 'darwin' in sys.platform:
                file_locked = stat_info.st_flags & stat.UF_IMMUTABLE
            else:
                file_locked = not os.access(src_full_path, os.W_OK)

            # Remember if the number part of the image name is getting near the rollover point.
            image_db.near_rollover |= image_name[-4] == '9'
            image_db.rollover_occurred |= image_name[-4:] == "9999"

            # If we're downloading only locked images, ignore all the rest.
            if download_locked_only and not file_locked:
                continue

            size = stat_info.st_size

            # Have we already seen a file for this image (with a different extension)?
            try:
                image = image_db.db[image_name]
                if image.contains_file_extension(extension):
                    raise CliError(
                        f"Source contains more than one {src_filename}.{extension}")
                image.add_file_extension(extension)
                image.size += size
            except KeyError:
                image_db.db[image_name] = SourceImage(
                    src_filename=src_filename, src_path=dirpath, extensions=[extension], 
                    file_locked=bool(file_locked), size=size, dst_filename=dst_filename
                    )

            image_db.total_to_transfer += size

            # Increment count for this file type (extension in upper case)
            if ext_upper not in image_db.file_type_count:
                image_db.file_type_count[ext_upper] = 0
            image_db.file_type_count[ext_upper] += 1

            if file_locked:
                image_db.locked_file_count += 1

    return image_db

