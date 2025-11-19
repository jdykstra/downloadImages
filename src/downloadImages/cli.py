#!/usr/bin/env python3
# encoding: utf-8
'''
downloadImages -- Download images from a DCF volume such as an SD card.

@author:     John Dykstra

@copyright:  2017-2024 John Dykstra. All rights reserved.

@license:    MIT

@contact:    jdykstra72@gmail.com
   
'''


'''
    We try to be filesystem-case-sensitive-agnostic.  The case of source filenames and extensions is preserved in
    the destination directory, but we don't allow multiple destination files that differ only in case.
'''

from .resolve_integration import ingestMotionClips, ResolveError
from progressbar.bar import ProgressBarMixinBase, types
from .apppaths import LIGHTROOM_APP
from progressbar import ProgressBar, GranularBar, AdaptiveTransferSpeed, AbsoluteETA
from argparse import RawDescriptionHelpFormatter
from argparse import ArgumentParser
import traceback
import sys
import subprocess
import stat
import shutil
import datetime
import os
from builtins import str
from progressbar.widgets import Data
from builtins import zip

__version__ = "2.0"
__title__ = "downloadImages"
__author__ = "John Dykstra"
__copyright__ = "2017-2025 John Dykstra. All rights reserved."
__license__ = "MIT"
__contact__ = "jdykstra72@gmail.com"


DEBUG: bool = False
if DEBUG:
    import pdb
    import traceback

# File-global source image database and summary variables
images_db: dict[str, 'Source_Image'] = {}
total_images: int = 0
file_type_count: dict[str, int] = {}
locked_file_count: int = 0
total_to_transfer: int = 0

jpeg_file_types: list[str] = ['JPG']
still_file_types: list[str] = jpeg_file_types + ['NEF']
motion_file_types: list[str] = ['MOV', 'MP4', 'NEV']

CLEOL: str = "\033[K"  # Clear to end of line ANSI escape sequence


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


class CliError(Exception):
    '''Generic exception to raise and log different fatal errors.'''

    def __init__(self, msg):
        super().__init__(type(self))
        self.msg = "ERROR: %s" % msg

    def __str__(self):
        return self.msg

    def __unicode__(self):
        return self.msg


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


# Create the destination directory, returning a path to it.
def create_destination_dir(dest_path: str, name: str) -> str:
    d = os.path.join(dest_path, name)

    # If the destination directory already exists, accept that silently.
    if not os.path.isdir(d):
        os.makedirs(d)

    return d


# Return a dictionary describing all of the image files on the source, indexed by the image name.
def find_source_images(src: str, download_locked_only: bool) -> dict[str, 'Source_Image']:
    global total_to_transfer, file_type_count, locked_file_count
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
            if ext_upper not in still_file_types + motion_file_types:
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


# Return a list of files already in a destination directory.
# ?? Too complex.  Either set a "skip" key in the per-image dictionary, or delete the per-image dictionary from
# ?? the images dictionary.
# ?? Except a file might be a duplicate in one destination directory, and not another.
# ?? Issue #3:  This doesn't properly handle source files with multiple extensions which are only partially copied.
def look_for_duplicates(images: dict[str, 'Source_Image'], dst: str) -> list[str]:
    duplicates = []

    for image_name in iter(images_db):
        for extension in images_db[image_name].extensions:
            dst_full_path = os.path.join(
                dst, images_db[image_name].dst_filename + "." + extension)
            if os.path.exists(dst_full_path):
                src_full_path = os.path.join(
                    images_db[image_name].src_path, images_db[image_name].src_filename + "." + extension)
                if (os.stat(dst_full_path).st_size == os.stat(src_full_path).st_size):
                    duplicates.append(image_name)

    return duplicates


# Tweak the AbsoluteETA widget to only show the time part of the time and date.
class CustomAbsoluteEta(AbsoluteETA):

    def __call__(self, progress, data, format=None):
        eta = super().__call__(progress, data, format)
        eta = str(data['eta'])
        return 'ETA: %s' % eta[-8:]


class ProgressTracker():

    def __init__(self, total_to_transfer):
        self.already_copied = 0
        self.bar = ProgressBar(max_value=total_to_transfer, widgets=[AdaptiveTransferSpeed(), " ", GranularBar(), " ",
                        CustomAbsoluteEta(format='ETA: %(eta)s', format_finished='ETA: %(ow)s', format_not_started='ETA: --:--')])

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        pass

    def update(self, copied):
        self.already_copied += copied
        self.bar.update(self.already_copied)


# Copy a file while updating progress on the screen.
# We originally used shutil.copy2(), which takes advantage of OS-specific optimizations,
# but doesn't provide progress feedback.
# Tests of this version on Mac OS with an external flash drive showed equivalent performance.
def copy_with_progress(src_file: str, dst_file: str, image_name: str, tracker) -> None:
    try:
        with open(src_file, 'rb') as src, open(dst_file, 'wb') as dst:
            while True:
                buf = src.read(1024 * 1024)  # Read file in chunks of 1MB
                if not buf:
                    break
                dst.write(buf)
                tracker.update(len(buf))
        shutil.copystat(src_file, dst_file)
    except Exception as e:
        print(f"Deleting suspect destination file {dst_file} due to error.")
        try:
            os.remove(dst_file)
        except Exception:
            pass  # Ignore exceptions from os.remove()
        raise e


# Copy the image files from the source to the destination and create a XMP sidecar file for each.
def copy_image_files(
    images: dict[str, 'Source_Image'],
    destination_dirs: list[str],
    skips: list[list[str]],
    description: str,
    download_locked_only: bool = False,
    delete: bool = False
) -> None:
    
    already_copied = 0
    with ProgressTracker(len(destination_dirs) * total_to_transfer) as tracker:
        for image_name in iter(images_db):
            image = images_db[image_name]
            for dest, skip in zip(destination_dirs, skips):
                for extension in image.extensions:
                    src_full_path = os.path.join(
                        image.src_path, image.src_filename + "." + extension)
                    dst_full_path = os.path.join(dest, image.dst_filename + "." + extension)

                    # Copy the image file unless it's a duplicate.  If we're only copying locked files, skip unlocked files.
                    if image_name not in skip:
                        if not download_locked_only or image.file_locked:
                            copy_with_progress(
                                src_full_path, dst_full_path, image_name, tracker)

                    # If write protect was set on the source file, clear it on the destination.  We'll
                    # treat it specially below when we create the XMP sidecar file.  If we're going
                    # to delete the source file, also clear write protect on it.
                    # ?? This is slightly unsafe, since we'll lose the locked indication on the source
                    # ?? if we crash before deleting it.
                    if image.file_locked:
                        if 'darwin' in sys.platform:
                            os.chflags(dst_full_path, os.stat(
                                dst_full_path).st_flags & ~stat.UF_IMMUTABLE)
                            if delete:
                                os.chflags(src_full_path, os.stat(
                                    src_full_path).st_flags & ~stat.UF_IMMUTABLE)
                        else:
                            os.chmod(dst_full_path, stat.S_IWRITE)
                            if delete:
                                os.chmod(src_full_path, stat.S_IWRITE)

                    # Create the sidecar file for stills only.
                    # ?? Use multi-line string constant?
                    # ?? The write protect part could be coded as:
                    # ??      file_locked and "Purple" or "None"
                    if extension.upper() in still_file_types:
                        xmp_label = "     xmp:Label=\"Purple\"\n" if image.file_locked else ""
                        xmp_content = f"""<x:xmpmeta xmlns:x=\"adobe:ns:meta/\">
<rdf:RDF xmlns:rdf=\"http://www.w3.org/1999/02/22-rdf-syntax-ns#\">

  <rdf:Description rdf:about=\"\"
     xmlns:xmp=\"http://ns.adobe.com/xap/1.0/\"
     xmlns:dc=\"http://purl.org/dc/elements/1.1/\"
{xmp_label}     >
     <dc:description>
      <rdf:Alt>
        <rdf:li xml:lang=\"x-default\">{description}&#xA;</rdf:li>
      </rdf:Alt>
    </dc:description>
  </rdf:Description>

</rdf:RDF>
</x:xmpmeta>
"""
                        with open(os.path.join(dest, image.dst_filename + ".xmp"), "w") as sidecar:
                            sidecar.write(xmp_content)
            already_copied += image.size

    sys.stdout.write("\n")      # Needed after progress bar output
    sys.stdout.flush()


# Programmatic API to this module.  Returns name (not path) of destination directories.

def do_download(
    destination_paths: list[str],
    tag: str,
    description: str,
    download_locked_only: bool = False,
    delete: bool = False,
    verbose: bool = False
) -> str:

    # Find the source volume.  We can only handle one.
    source_vols = find_source_volume()
    if (len(source_vols) < 1):
        raise CliError("Could not find a DCF volume.")
    if (len(source_vols) > 1):
        raise CliError("More than one DCF volume found.")
    source_vol = source_vols[0]

    # Find image files on the source volume.
    images = find_source_images(source_vol[1], download_locked_only)
    print(f"{len(images)} image files found on {source_vol[0]}.")

    # If we're supposed to delete the source images, make sure that we can.
    if (delete and not os.access(source_vol[1], os.W_OK)):
        raise CliError("Source volume is read-only and delete option is set.")

    # Look for existing duplicates on the destination volumes.
    # DestinationDirs and duplicates are lists in the same order as the
    # entries in destination_paths.
    destination_dirs = []
    duplicates = []
    today = datetime.date.today()
    dir_name = str(today.month) + "-" + str(today.day) + " " + tag
    for dest_path in destination_paths:

        # Create the destination directory, if necessary.
        dest_dir = create_destination_dir(dest_path, dir_name)
        destination_dirs.append(dest_dir)

        # Look for duplicate image files on the destination.
        dups = look_for_duplicates(images, dest_dir)
        duplicates.append(dups)
        if len(dups) > 0:
            print("%d image files already exist in \"%s\". " %
                  (len(dups), dest_dir))

    # Copy the image files from the source to the destinations and create the sidecar files.
    # ?? Having matching tuples of destination directories and duplicate lists seems
    # ?? unnecessarily complex.  Why not call copyImageFiles() once for each destination
    # ?? directory?
    # ?? We could also pass in the destination directory and duplicate list as a tuple.
    # On the other hand, this enables us to write all the destinations while each source
    # file is still open and in cache.
    copy_image_files(images, destination_dirs, duplicates,
                    description, download_locked_only, delete)

    # Flush Mac OS disk caches to guard against external disks being disconnected, power failures, etc.
    # We assume that Windows disks are configured to flush to hardware after every write.
    if 'darwin' in sys.platform:
        subprocess.run(["sync"], check=True)

    # Delete the source files.
    if delete:
        print(f"Deleting images from {source_vol[0]}.\n")
        shutil.rmtree(source_vol[1])

    # On Mac OS, unmount the source volume.  We assume that Windows disks are configured to
    # flush to hardware after every write.
    if 'darwin' in sys.platform:
        subprocess.run(["diskutil", "unmount", os.path.join(
            "/Volumes", source_vol[0])], check=True)
        ejected = True
        if ejected:
            print(f"All images successfully downloaded and {source_vol[0]} ejected.")
        else:
             print(
                 f"ERROR - All images successfully downloaded, but could not eject {source_vol[0]}!")
    else:
        print("All images successfully downloaded.")

    return dir_name


#  CLI Interface
def main(argv: list[str] | None = None) -> int:

    # Command line options.
    if argv is None:
        argv = sys.argv
    else:
        sys.argv.extend(argv)

    program_name = os.path.basename(sys.argv[0])
    program_version = f"v{__version__}"
    program_version_message = f"%(prog)s {program_version}"
    program_shortdesc = __doc__.split("\n")[1]
    program_license = f'''{program_shortdesc}

  Copyright 2017-2025 John Dykstra. All rights reserved.

  Licensed under the MIT License.
  Distributed on an "AS IS" basis without warranties
  or conditions of any kind, either express or implied.

USAGE
'''

    print("downloadImages v%s" % (__version__))
    caffeinateProcess = None
    if sys.platform not in ["darwin", "win32"]:
        sys.stderr.write("Only Mac OS and Windows are supported.")

    try:
        # Setup argument parser
        parser = ArgumentParser(
            description=program_license, formatter_class=RawDescriptionHelpFormatter)
        parser.add_argument("-v", "--verbose", dest="verbose", action="count",
                            default=0, help="set verbosity level [default: %(default)s]")
        parser.add_argument("-t", "--tag", dest="tag", default="Downloaded Images",
                            help="Tag used as destination directory name. [default: %(default)s]")
        parser.add_argument("-d", "--description", dest="description",
                            help="Description saved in each photo's sidecar.")
        parser.add_argument("-L", "--locked-only", dest="download_locked_only",
                            action='store_true', help="Only download locked files.")
        parser.add_argument("-D", "--delete", dest="delete", action='store_true',
                            help="Delete files from card after successful download.")
        parser.add_argument("-a", "--automate", dest="automate",
                            action='store_true', help="Import all images into Lightroom.")
        parser.add_argument("-r", "--resolve", dest="automateResolve",
                    action='store_true', help="Import all motion clips into DaVinci Resolve.")
        parser.add_argument('-V', '--version', action='version',
                            version=program_version_message)
        parser.add_argument("destinations", nargs='+',
                            help="Destination directories for images;  at least one required.")

        # Process arguments
        args = parser.parse_args(argv[1:])

        if args.verbose > 0:
            print("Verbose mode on")

        # Do sanity checks on argument values.
        # Make sure the path to each destination directory exists.  This helps prevent a misplaced tag
        # or description from being interpreter as yet another destination.
        for path in args.destinations:
            if not os.path.exists(path):
                print(
                    f"Error:  Destination path \"{path}\" doesn't exist.")
                return 2
        if args.download_locked_only and args.delete:
            print("Error:  Delete and locked-only options are mutually exclusive.")
            return 2

        if 'darwin' in sys.platform:
            caffeinateProcess = subprocess.Popen(('caffeinate', '-i'))

        dir_name = do_download(args.destinations, args.tag, args.description,
                      args.download_locked_only, args.delete, args.verbose)

        if caffeinateProcess != None:
            caffeinateProcess.terminate()

        # Launch Lightroom to ingest all image files.  This will run asynchronously.
        if args.automate:
            if 'darwin' in sys.platform:
                os.system("open -a \"" + LIGHTROOM_APP + "\" \"" +
                          os.path.join(args.destinations[0], dir_name) + "\"")
            else:
                os.system("start \"\" \"" + LIGHTROOM_APP + "\" \"" +
                          os.path.join(args.destinations[0], dir_name) + "\"")

        # Launch DaVinci Resolve to ingest all motion clips.  This will run asynchronously.
        if args.automateResolve:
            print(f"Ingesting motion to Resolve project {args.tag}...")
            today = datetime.date.today()
            dir_name = str(today.month) + "-" + str(today.day) + " " + args.tag
            day_stamp = str(today.month) + "-" + str(today.day)
            full_path = os.path.join(args.destinations[0], dir_name)
            try:
                ingestMotionClips(args.tag, day_stamp, args.description, full_path)
            except ResolveError as e:
                print("Error: Could not ingest motion files to Resolve.")
                print(f"Error: {e}")
                return 1
            print(f"Ingesting motion completed.")

        return 0
        
    except KeyboardInterrupt:
        print("Keyboard interrupt")
        if caffeinateProcess != None:
            print("Killing caffeinate")
            caffeinateProcess.terminate()
        return 2
    
    except CliError as e:
        print(e)
        if caffeinateProcess != None:
            caffeinateProcess.terminate()
        indent = len(program_name) * " "
        sys.stderr.write(program_name + ": " + repr(e) + "\n")
        sys.stderr.write(indent + "  for help use --help\n")    
        return 2
    except Exception as e:
        extrype, value, tb = sys.exc_info()
        traceback.print_exc()
        print("Exception caught")
        traceback.print_tb(sys.exc_info()[2])
        if DEBUG:
            pdb.post_mortem(tb)
        if caffeinateProcess != None:
            print("Killing caffeinate")
            caffeinateProcess.terminate()
        if DEBUG:
            raise(e)       
        return 2

if __name__ == "__main__":
    sys.exit(main())