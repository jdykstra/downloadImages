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
from .sourceimages import SourceImage, find_source_volume, find_source_images, STILL_FILE_TYPES, MOTION_FILE_TYPES
from .download import create_destination_dir, copy_image_files, look_for_duplicates

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


CLEOL: str = "\033[K"  # Clear to end of line ANSI escape sequence


class CliError(Exception):
    '''Generic exception to raise and log different fatal errors.'''

    def __init__(self, msg):
        super().__init__(type(self))
        self.msg = "ERROR: %s" % msg

    def __str__(self):
        return self.msg

    def __unicode__(self):
        return self.msg



# Return a list of files already in a destination directory.
# ?? Too complex.  Either set a "skip" key in the per-image dictionary, or delete the per-image dictionary from
# ?? the images dictionary.
# ?? Except a file might be a duplicate in one destination directory, and not another.
# ?? Issue #3:  This doesn't properly handle source files with multiple extensions which are only partially copied.
def look_for_duplicates(images: dict[str, 'SourceImage'], dst: str) -> list[str]:
    duplicates = []

    for image_name in iter(images):
        for extension in images[image_name].extensions:
            dst_full_path = os.path.join(
                dst, images[image_name].dst_filename + "." + extension)
            if os.path.exists(dst_full_path):
                src_full_path = os.path.join(
                    images[image_name].src_path, images[image_name].src_filename + "." + extension)
                if (os.stat(dst_full_path).st_size == os.stat(src_full_path).st_size):
                    duplicates.append(image_name)

    return duplicates


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

        # Find the source volume.  We can only handle one.
        source_vols = find_source_volume()
        if (len(source_vols) < 1):
            raise CliError("Could not find a DCF volume.")
        if (len(source_vols) > 1):
            raise CliError("More than one DCF volume found.")
        source_vol = source_vols[0]

        # Find image files on the source volume.
        image_data = find_source_images(source_vol[1], args.download_locked_only)
        images = image_data.db
        print(f"{len(images)} images (potentially in multiple files) found on {source_vol[0]}.")

        # If we're supposed to delete the source images, make sure that we can.
        if (args.delete and not os.access(source_vol[1], os.W_OK)):
            raise CliError("Source volume is read-only and delete option is set.")

        # Look for existing duplicates on the destination volumes.
        # DestinationDirs and duplicates are lists in the same order as the
        # entries in destination_paths.
        destination_dirs = []
        duplicates = []
        today = datetime.date.today()
        dir_name = str(today.month) + "-" + str(today.day) + " " + args.tag
        for dest_path in args.destinations:

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
                        args.description, image_data.total_to_transfer, args.download_locked_only, args.delete)

        # Flush Mac OS disk caches to guard against external disks being disconnected, power failures, etc.
        # We assume that Windows disks are configured to flush to hardware after every write.
        if 'darwin' in sys.platform:
            subprocess.run(["sync"], check=True)

        # Delete the source files.
        if args.delete:
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