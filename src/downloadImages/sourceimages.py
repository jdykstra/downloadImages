# File-global source image database and summary variables
import os
import stat
import sys

images_db: dict[str, 'Source_Image'] = {}
total_images: int = 0
file_type_count: dict[str, int] = {}
locked_file_count: int = 0
total_to_transfer: int = 0

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


class Source_Image:
    def __init__(self, src_filename: str, src_path: str, extension: str, file_locked: bool, size: int, dst_filename: str) -> None:
        self.src_filename: str = src_filename
        self.src_path: str = src_path
        self.extensions: list[str] = [extension]
        self.file_locked: bool = file_locked
        self.size: int = size
        self.dst_filename: str = dst_filename

    def add_file_extension(self, extension: str) -> None:
        self.extensions.append(extension)

    def contains_file_extension(self, extension: str) -> bool:
        return extension in self.extensions

    def __str__(self) -> str:
        return (f"ImageFile: src_filename = {self.src_filename}, src_path = {self.src_path}, extensions = {self.extensions}, "
                f"file_locked = {self.file_locked}, size = {self.size}, dst_filename = {self.dst_filename}")

    def __repr__(self) -> str:
        return self.__str__()


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
def find_source_images(src: str, download_locked_only: bool) -> dict[str, 'Source_Image']:
    global total_to_transfer, file_type_count, locked_file_count, images_db, total_images
    # Reset global variables for each scan
    images_db = {}
    total_images = 0
    file_type_count = {}
    locked_file_count = 0
    total_to_transfer = 0
    nearRollover = False
    rolloverOccurred = False

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
            nearRollover |= image_name[-4] == '9'
            rolloverOccurred |= image_name[-4:] == "9999"

            # If we're downloading only locked images, ignore all the rest.
            if download_locked_only and not file_locked:
                continue

            size = stat_info.st_size

            # Have we already seen a file for this image (with a different extension)?
            try:
                image = images_db[image_name]
                if image.contains_file_extension(extension):
                    raise CliError(
                        f"Source contains more than one {src_filename}.{extension}")
                image.add_file_extension(extension)
                image.size += size
            except KeyError:
                images_db[image_name] = Source_Image(
                    src_filename, dirpath, extension, bool(file_locked), size, dst_filename)

            total_to_transfer += size

            # Increment count for this file type (extension in upper case)
            if ext_upper not in file_type_count:
                file_type_count[ext_upper] = 0
            file_type_count[ext_upper] += 1

            if file_locked:
                locked_file_count += 1

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
            nearRollover |= image_name[-4] == '9'
            rolloverOccurred |= image_name[-4:] == "9999"

    for ext, count in file_type_count.items():
        if count > 0:
            print(f"{count} {ext} files found.")
    print(f"Total size of files to transfer: {total_to_transfer / 1_073_741_824:.2f} GB.")
    if locked_file_count > 0:
        print(f"{locked_file_count} files are locked.")
    elif download_locked_only:
        print("WARNING:  Downloading locked files only, but no locked files found.")
    if rolloverOccurred:
        print("WARNING:  Image numbers rolled over!")
    elif nearRollover:
        print("WARNING:  Image numbers are nearing the rollover point!")

    return images_db

