#!/usr/bin/env python3
# encoding: utf-8
'''
downloadImages -- Download images from a DCF volume such as an SD card.

@author:     John Dykstra

@copyright:  2017-2024 John Dykstra. All rights reserved.

@license:    MIT

@contact:    jdykstra72@gmail.com
   
'''

__license__ = "MIT"
__contact__ = "jdykstra72@gmail.com"

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
__all__ = ['doDownload']
__version__ = "1.14"
__title__ = "downloadImages"
__author__ = "John Dykstra"
__copyright__ = "2017-2025 John Dykstra. All rights reserved."


DEBUG = False
if DEBUG:
    import pdb
    import traceback

jpegExtensions = ['JPG']
imageExtensions = jpegExtensions + ['NEF']
videoExtensions = ['MOV', 'MP4', 'NEV']

cleol = "\033[K"  # Clear to end of line ANSI escape sequence

totalToTransfer = 0


class CLIError(Exception):
    '''Generic exception to raise and log different fatal errors.'''

    def __init__(self, msg):
        super(CLIError).__init__(type(self))
        self.msg = "ERROR: %s" % msg

    def __str__(self):
        return self.msg

    def __unicode__(self):
        return self.msg


# Find potential source DCF volumes, returning a list of (name, path) tuples.
def findSourceVolume():
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
def createDestinationDir(destPath, name):
    d = os.path.join(destPath, name)

    # If the destination directory already exists, accept that silently.
    if not os.path.isdir(d):
         os.makedirs(d)

    return d


# Class representing a single image.  That image may have more than one associated image file, such as a JPEG and a RAW file.
class Image:
    def __init__(self, srcFilename, srcPath, extension, fileLocked, size, dstFilename):
        self.srcFilename = srcFilename
        self.srcPath = srcPath
        self.extensions = [extension]
        self.fileLocked = fileLocked
        self.size = size
        self.dstFilename = dstFilename

    def addFileExtension(self, extension):
        self.extensions.append(extension)

    def containsFileExtension(self, extension):
        return extension in self.extensions

    def __str__(self):
        return "ImageFile: srcFilename = {0}, srcPath = {1}, extensions = {2}, fileLocked = {3}, size = {4}, dstFilename = {5}".format(self.srcFilename, self.srcPath, self.extensions, self.fileLocked, self.size, self.dstFilename)

    def __repr__(self):
        return self.__str__()


# Return a dictionary describing all of the image files on the source, indexed by the image name.
def findSourceImages(src, downloadLockedOnly):
    images = {}
    jpegCnt = 0
    movCnt = 0
    lockedFileCnt = 0
    nearRollover = False
    rolloverOccurred = False
    global totalToTransfer

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
            srcFilename = fparts[0]
            extension = fparts[-1]
            # Remove underscores used by Nikon
            dstFilename = srcFilename.replace("_", "")
            imageName = dstFilename.upper()
            if extension.upper() not in imageExtensions + videoExtensions:
                continue

            # If write protect was set on an image by the camera, it will appear on
            # MacOS as the user-immutable flag.  FWIW, this flag can be seen using
            # "ls -lhdO".  On Windows, we just look for read-only.
            srcFullPath = os.path.join(dirpath, srcFilename + "." + extension)
            statInfo = os.stat(srcFullPath)
            if 'darwin' in sys.platform:
                fileLocked = statInfo.st_flags & stat.UF_IMMUTABLE
            else:
                fileLocked = not os.access(srcFullPath, os.W_OK)

            # Remember if the number part of the image name is getting near the rollover point.
            nearRollover |= imageName[-4] == '9'
            rolloverOccurred |= imageName[-4:] == "9999"

            # If we're downloading only locked images, ignore all the rest.
            if downloadLockedOnly and not fileLocked:
                continue

            size = statInfo.st_size

            # Have we already seen a file for this image (with a different extension)?
            try:
                image = images[imageName]
                if image.containsFileExtension(extension):
                    raise CLIError(
                        "Source contains more than one " + srcFilename + "." + extension)

                image.addFileExtension(extension)
                image.size += size
            except KeyError:
                images[imageName] = Image(
                    srcFilename, dirpath, extension, fileLocked, size, dstFilename)

            totalToTransfer += size

            if extension.upper() in jpegExtensions:
                jpegCnt += 1
            elif extension.upper() in videoExtensions:
                movCnt += 1

            if fileLocked:
                lockedFileCnt += 1

    if jpegCnt > 0:
        print("WARNING:  {0} JPEG files found!".format(jpegCnt))
    if movCnt > 0:
        print("{0} video files found.".format(movCnt))
    print(
        f"Total size of files to transfer: {totalToTransfer / 1_073_741_824:.2f} GB.")
    if lockedFileCnt > 0:
        print("{0} files are locked.".format(lockedFileCnt))
    elif downloadLockedOnly:
        print("WARNING:  Downloading locked files only, but no locked files found.")
    if rolloverOccurred:
        print("WARNING:  Image numbers rolled over!")
    elif nearRollover:
        print("WARNING:  Image numbers are nearing the rollover point!")

    return images


# Return a list of files already in a destination directory.
# ?? Too complex.  Either set a "skip" key in the per-image dictionary, or delete the per-image dictionary from
# ?? the images dictionary.
# ?? Except a file might be a duplicate in one destination directory, and not another.
# ?? Issue #3:  This doesn't properly handle source files with multiple extensions which are only partially copied.
def lookForDuplicates(images, dst):
    duplicates = []

    for imageName in iter(images):
        for ext in images[imageName].extensions:
            dstFullPath = os.path.join(
                dst, images[imageName].dstFilename + "." + ext)
            if os.path.exists(dstFullPath):
                srcFullPath = os.path.join(
                    images[imageName].srcPath, images[imageName].srcFilename + "." + ext)
                if (os.stat(dstFullPath).st_size == os.stat(srcFullPath).st_size):
                    duplicates.append(imageName)

    return duplicates


# Tweak the AbsoluteETA widget to only show the time part of the time and date.


class CustomAbsoluteETA(AbsoluteETA):

    def __call__(
        self,
        progress: ProgressBarMixinBase,
        data: Data,
        format: types.Optional[str] = None,
    ) -> str:
        eta = super().__call__(progress, data, format)
        eta = str(data['eta'])
        return 'ETA: %s' % eta[-8:]


class ProgressTracker():

    def __init__(self, totalToTransfer):
        self.alreadyCopied = 0
        self.bar = ProgressBar(max_value=totalToTransfer, widgets=[AdaptiveTransferSpeed(), " ", GranularBar(), " ",
                        CustomAbsoluteETA(format='ETA: %(eta)s', format_finished='ETA: %(ow)s', format_not_started='ETA: --:--')])

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        pass

    def update(self, copied):
        self.alreadyCopied += copied
        self.bar.update(self.alreadyCopied)


# Copy a file while updating progress on the screen.
# We originally used shutil.copy2(), which takes advantage of OS-specific optimizations,
# but doesn't provide progress feedback.
# Tests of this version on Mac OS with an external flash drive showed equivalent performance.
def copy_with_progress(src_file, dst_file, imageName, tracker):
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
        print(f"Deleting {dst_file} due to error.")
        try:
            os.remove(dst_file)
        except Exception:
            pass  # Ignore exceptions from os.remove()
        raise e


# Copy the image files from the source to the destination and create a XMP sidecar file for each.
def copyImageFiles(images, destinationDirs, skips, description, downloadLockedOnly=False, delete=False):
    global totalToTransfer

    alreadyCopied = 0
    with ProgressTracker(len(destinationDirs) * totalToTransfer) as tracker:
        for imageName in iter(images):
            image = images[imageName]
            for dest, skip in zip(destinationDirs, skips):
                for ext in image.extensions:
                    srcFullpath = os.path.join(
                        image.srcPath, image.srcFilename + "." + ext)
                    dstFullPath = os.path.join(dest, image.dstFilename + "." + ext)

                    # Copy the image file unless it's a duplicate.  If we're only copying locked files, skip unlocked files.
                    if imageName not in skip:
                        if not downloadLockedOnly or image.fileLocked:
                            copy_with_progress(
                                srcFullpath, dstFullPath, imageName, tracker)

                    # If write protect was set on the source file, clear it on the destination.  We'll
                    # treat it specially below when we create the XMP sidecar file.  If we're going
                    # to delete the source file, also clear write protect on it.
                    # ?? This is slightly unsafe, since we'll loose the locked indication on the source
                    # ?? if we crash before deleting it.
                    if image.fileLocked:
                        if 'darwin' in sys.platform:
                            os.chflags(dstFullPath, os.stat(
                                dstFullPath).st_flags & ~stat.UF_IMMUTABLE)
                            if delete:
                                os.chflags(srcFullpath, os.stat(
                                    srcFullpath).st_flags & ~stat.UF_IMMUTABLE)
                        else:
                            os.chmod(dstFullPath, stat.S_IWRITE)
                            if delete:
                                os.chmod(srcFullpath, stat.S_IWRITE)

                    # Create the sidecar file for stills only.
                    # ?? Use multi-line string constant?
                    # ?? The write protect part could be coded as:
                    # ??      fileLocked and "Purple" or "None"
                    if ext.upper() in imageExtensions:
                        sidecar = open(os.path.join(
                            dest, image.dstFilename + ".xmp"), "w")
                        sidecar.write(
                            "<x:xmpmeta xmlns:x=\"adobe:ns:meta/\">\n")
                        sidecar.write(
                            "<rdf:RDF xmlns:rdf=\"http://www.w3.org/1999/02/22-rdf-syntax-ns#\">\n")
                        sidecar.write("\n")
                        sidecar.write("  <rdf:Description rdf:about=\"\"\n")
                        sidecar.write(
                            "     xmlns:xmp=\"http://ns.adobe.com/xap/1.0/\"\n")
                        sidecar.write(
                            "     xmlns:dc=\"http://purl.org/dc/elements/1.1/\"\n")
                        if image.fileLocked:
                            sidecar.write("     xmp:Label=\"Purple\"\n")
                        sidecar.write("     >\n")
                        sidecar.write("     <dc:description>\n")
                        sidecar.write("      <rdf:Alt>\n")
                        sidecar.write(
                            "        <rdf:li xml:lang=\"x-default\">{0}&#xA;</rdf:li>\n".format(description))
                        sidecar.write("      </rdf:Alt>\n")
                        sidecar.write("    </dc:description>\n")
                        sidecar.write("  </rdf:Description>\n")
                        sidecar.write("\n")
                        sidecar.write("</rdf:RDF>\n")
                        sidecar.write("</x:xmpmeta>\n")
                        sidecar.close()
            alreadyCopied += image.size

    sys.stdout.write("\n")      # Needed after progress bar output
    sys.stdout.flush()


# Programmatic API to this module.  Returns name (not path) of destination directories.
def doDownload(destinationPaths, tag, description, downloadLockedOnly=False, delete=False, verbose=False):

    # Find the source volume.  We can only handle one.
    sourceVols = findSourceVolume()
    if (len(sourceVols) < 1):
        raise CLIError("Could not find a DCF volume.")
    if (len(sourceVols) > 1):
        raise CLIError("More than one DCF volume found.")
    sourceVol = sourceVols[0]

    # Find image files on the source volume.
    images = findSourceImages(sourceVol[1], downloadLockedOnly)
    print("{0} image files found on {1}.".format(len(images), sourceVol[0]))

    # If we're supposed to delete the source images, make sure that we can.
    if (delete and not os.access(sourceVol[1], os.W_OK)):
        raise CLIError("Source volume is read-only and delete option is set.")

    # Look for existing duplicates on the destination volumes.
    # DestinationDirs and duplicates are lists in the same order as the
    # entries in destinationPaths.
    destinationDirs = []
    duplicates = []
    today = datetime.date.today()
    dirName = str(today.month) + "-" + str(today.day) + " " + tag
    for destPath in destinationPaths:

        # Create the destination directory, if necessary.
        destDir = createDestinationDir(destPath, dirName)
        destinationDirs.append(destDir)

        # Look for duplicate image files on the destination.
        dups = lookForDuplicates(images, destDir)
        duplicates.append(dups)
        if len(dups) > 0:
            print("%d image files already exist in \"%s\". " %
                  (len(dups), destDir))

    # Copy the image files from the source to the destinations and create the sidecar files.
    # ?? Having matching tuples of destination directories and duplicate lists seems
    # ?? unnecessarily complex.  Why not call copyImageFiles() once for each destination
    # ?? directory?
    # ?? We could also pass in the destination directory and duplicate list as a tuple.
    # On the other hand, this enables us to write all the destinations while each source
    # file is still open and in cache.
    copyImageFiles(images, destinationDirs, duplicates,
                   description, downloadLockedOnly, delete)

    # Flush Mac OS disk caches to guard against external disks being disconnected, power failures, etc.
    # We assume that Windows disks are configured to flush to hardware after every write.
    if 'darwin' in sys.platform:
        subprocess.run(["sync"], check=True)

    # Delete the source files.
    if delete:
        print("Deleting images from {0}.\n".format(sourceVol[0]))
        shutil.rmtree(sourceVol[1])

    # On Mac OS, unmount the source volume.  We assume that Windows disks are configured to
    # flush to hardware after every write.
    if 'darwin' in sys.platform:
        subprocess.run(["diskutil", "unmount", os.path.join(
            "/Volumes", sourceVol[0])], check=True)
        ejected = True
        if ejected:
            print("All images successfully downloaded and {0} ejected.".format(
                sourceVol[0]))
        else:
             print(
                 "ERROR - All images successfully downloaded, but could not eject {0}!".format(sourceVol[0]))
    else:
        print("All images successfully downloaded.")

    return dirName


#  CLI Interface
def main(argv=None):

    # Command line options.
    if argv is None:
        argv = sys.argv
    else:
        sys.argv.extend(argv)

    program_name = os.path.basename(sys.argv[0])
    program_version = "v%s" % __version__
    program_version_message = '%%(prog)s %s' % (program_version)
    program_shortdesc = __doc__.split("\n")[1]
    program_license = '''%s

  Copyright 2017-2024 John Dykstra. All rights reserved.

  Licensed under the MIT License.
  Distributed on an "AS IS" basis without warranties
  or conditions of any kind, either express or implied.

USAGE
''' % (program_shortdesc)

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
        parser.add_argument("-L", "--locked-only", dest="downloadLockedOnly",
                            action='store_true', help="Only download locked files.")
        parser.add_argument("-D", "--delete", dest="delete", action='store_true',
                            help="Delete files from card after successful download.")
        parser.add_argument("-a", "--automate", dest="automate",
                            action='store_true', help="Import all images into Lightroom.")
        parser.add_argument("-r", "--resolve", dest="automateResolve",
                            action='store_true', help="Import all video clips into DaVinci Resolve.")
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
                    "Error:  Destination path \"{0}\" doesn't exist.".format(path))
                return 2
        if args.downloadLockedOnly and args.delete:
            print("Error:  Delete and locked-only options are mutually exclusive.")
            return 2

        if 'darwin' in sys.platform:
            caffeinateProcess = subprocess.Popen(('caffeinate', '-i'))

        dirName = doDownload(args.destinations, args.tag, args.description,
                             args.downloadLockedOnly, args.delete, args.verbose)

        if caffeinateProcess != None:
            caffeinateProcess.terminate()

        # Launch Lightroom to ingest all image files.  This will run asynchronously.
        if args.automate:
            if 'darwin' in sys.platform:
                os.system("open -a \"" + LIGHTROOM_APP + "\" \"" +
                          os.path.join(args.destinations[0], dirName) + "\"")
            else:
                os.system("start \"\" \"" + LIGHTROOM_APP + "\" \"" +
                          os.path.join(args.destinations[0], dirName) + "\"")

        # Launch DaVinci Resolve to ingest all motion clips.  This will run asynchronously.
        if args.automateResolve:
            print(f"Ingesting video to Resolve project {args.tag}...")
            today = datetime.date.today()
            dirName = str(today.month) + "-" + str(today.day) + " " + args.tag
            dayStamp = str(today.month) + "-" + str(today.day)
            fullPath = os.path.join(args.destinations[0], dirName)
            try:
                ingestMotionClips(args.tag, dayStamp, args.description, fullPath)
            except ResolveError as e:
                print("Error: Could not ingest motion files to Resolve.")
                print(f"Error: {e}")
                return 1
            print(f"Ingesting video completed.")

        return 0
        
    except KeyboardInterrupt:
        print("Keyboard interrupt")
        if caffeinateProcess != None:
            print("Killing caffeinate")
            caffeinateProcess.terminate()
        ### handle keyboard interrupt ###
        return 2
    
    except CLIError as e:
        print(e)
        if caffeinateProcess != None:
            caffeinateProcess.terminate()
        indent = len(program_name) * " "
        sys.stderr.write(program_name + ": " + repr(e) + "\n")
        sys.stderr.write(indent + "  for help use --help\n")    
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
