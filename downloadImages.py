#!/usr/local/bin/python2.7
# encoding: utf-8
'''
downloadImages -- Download images from a DCF volume such as an SD card.

It defines classes_and_methods

@author:     John Dykstra

@copyright:  2017 John Dykstra. All rights reserved.

@license:    Apache

@contact:    jdykstra72@gmail.com
@deffield    updated: Updated

??  Todo - Detect (and handle?) rollovers
           Caffeinate wasn't killed, probably after trying to delete a locked file.
           Get info via dialog
   
'''

import os
import datetime
import io
import shutil
import stat
import subprocess
import sys
import time
import traceback

from AppKit import NSWorkspace

from argparse import ArgumentParser
from argparse import RawDescriptionHelpFormatter

__all__ = []
__version__ = 1.2
__date__ = '2017-04-06'
__updated__ = '2017-11-26'

DEBUG = 1
TESTRUN = 0

platform = "Mac"
lightroom = "Adobe Lightroom Classic CC"

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
    for d in os.listdir("/Volumes"):
        if not os.path.isdir(os.path.join("/Volumes", d)):
            continue
        tp = os.path.join(os.path.join("/Volumes", d), "DCIM")
        if os.path.isdir(tp):
            vollist.append((d, tp))
    return vollist;

# Create the destination directory, returning a path to it.
def createDestinationDir(destPath, name):
    d = os.path.join(destPath, name)
    
    # If the destination directory already exists, accept that silently.
    if os.path.isdir(d):
        return d
    
    os.makedirs(d)
    return d

# Return a dictionary describing all of the image files on the source..
def findSourceImages(src):
    images = {}
    jpegCnt = 0
    movCnt = 0
    nearRollover = False

    # Enumerate the image files on the source volume.
    for dirpath, dirs, files in os.walk(src):
        for f in files:
            
            # Ignore files that are unlikely to be camera image files,
            # including hidden files.
            if f.startswith("."):
                continue
            fparts = f.split(".")
            if len(fparts) != 2:
                continue
            origName = fparts[0].upper()
            newname = origName.replace("_", "")
            extension = fparts[-1].upper()
            if extension not in ['JPG', 'NEF', 'MOV']:
                continue
            
            # Remember if the number part of the image name is getting near the rollover point.
            nearRollover |= newname[-4] == '9'
            
            # Dictionary "images" is indexed by the image name.  Its entries are themselves
            # dictionaries, containing keys "srcNEF" and/or "srcJPG".  The contents of those
            # entries is a sequence of the pathname followed by the filename.
            if newname in images:
                images[newname]["extensions"].append(extension)
            else:
                images[newname] = dict(extensions = [extension], srcPath = dirpath, origName = origName)
                        
            if extension == 'JPG':
                jpegCnt += 1
            elif extension == 'MOV':
                movCnt += 1
    if jpegCnt > 0:
        print("WARNING:  {0} JPEG files found!".format(jpegCnt))
    if movCnt > 0:
        print("{0} video files found.".format(movCnt))
    if nearRollover:
        print("WARNING:  Image numbers are nearing the rollover point!")
    return images

# Return a list of files already in the destination directory.
def lookForDuplicates(images, dst):
    duplicates =[]
    
    for name in iter(images):
        for ext in images[name]["extensions"]:
            filename = name + "." + ext
            dstpath = os.path.join(dst, filename)
            if os.path.exists(dstpath):
                srcpath = os.path.join(images[name]["srcPath"], images[name]["origName"] + "." + ext)
                if (os.stat(dstpath).st_size == os.stat(srcpath).st_size):
                    duplicates.append(name)
    
    return duplicates
    

# Copy the image files from the source to the destination and create the sidecar file.
def copyImageFiles(images, destinationDirs, skips, description, delete=False):

    progress = 0
    for name in iter(images):
        entry = images[name]
        progress += 1
        for dest, skip in zip(destinationDirs, skips):
            if name not in skip:
                writeProtect = False;
                for ext in entry["extensions"]:                    
                    srcpath = os.path.join(entry["srcPath"], entry["origName"] + "." + ext)
                    dstpath = os.path.join(dest, name + "." + ext)
                    sys.stdout.write("{0}%:  {1} to {2}.\r".format((progress * 100) / len(images), name, dstpath))
                    sys.stdout.flush()

                    # If write protect was set on an image by the camera, it will appear to us
                    # as the user-immutable flag.  FWIW, this flag can be seen using
                    # "ls -lhdO".
                    writeProtect |= os.stat(srcpath).st_flags & stat.UF_IMMUTABLE                

                    # Copy the image file.
                    shutil.copy2(srcpath, dstpath)
                
                    # If write protect was set on the source file, clear it on the destination.  We'll
                    # treat it specially below when we create the XMP sidecar file.  If we're going
                    # to delete the source file, also clear write protect on it.
                    if writeProtect:
                        os.chflags(dstpath, os.stat(dstpath).st_flags & ~stat.UF_IMMUTABLE)
                        if delete:
                            os.chflags(srcpath, os.stat(srcpath).st_flags & ~stat.UF_IMMUTABLE)

                # Create the sidecar file.
                sidecar = open(os.path.join(dest, name+".XMP"), "w")
                sidecar.write("<x:xmpmeta xmlns:x=\"adobe:ns:meta/\">\n")
                sidecar.write("<rdf:RDF xmlns:rdf=\"http://www.w3.org/1999/02/22-rdf-syntax-ns#\">\n")
                sidecar.write("\n")
                sidecar.write("  <rdf:Description rdf:about=\"\"\n")
                sidecar.write("     xmlns:xmp=\"http://ns.adobe.com/xap/1.0/\"\n")
                sidecar.write("     xmlns:dc=\"http://purl.org/dc/elements/1.1/\"\n")
                if writeProtect:
                    sidecar.write("     xmp:Label=\"Purple\"\n")
                sidecar.write("     >\n")
                sidecar.write("     <dc:description>\n")
                sidecar.write("      <rdf:Alt>\n")
                sidecar.write("        <rdf:li xml:lang=\"x-default\">{0}&#xA;</rdf:li>\n".format(description))
                sidecar.write("      </rdf:Alt>\n")
                sidecar.write("    </dc:description>\n")
                sidecar.write("  </rdf:Description>\n")
                sidecar.write("\n")
                sidecar.write("</rdf:RDF>\n")
                sidecar.write("</x:xmpmeta>\n")
                sidecar.close()
     
    sys.stdout.write("\033[K")      #  Clear to end of line
    sys.stdout.flush()      
            
# Programmatic API.  Returns name (not path) of destination directories.
def doDownload(destinationPaths, tag, description, delete=False, verbose=False):
       
    # Find the source volume.  We can only handle one.
    sourceVols = findSourceVolume()
    if (len(sourceVols) < 1):
        raise CLIError("Could not find a DCF volume.")
    if (len(sourceVols) > 1):
        raise CLIError("More than one DCF volume found.")
    sourceVol=sourceVols[0]

    # Find image files on the source volume.
    images = findSourceImages(sourceVol[1])
    print("{0} image files found on {1}.".format(len(images), sourceVol[0]))
    
    # Handle multiple possible destinations.
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
            print("%d image files already exist in \"%s\". " % (len(dups), destDir))    
        
    # Copy the image files from the source to the destinations and create the sidecar files.
    copyImageFiles(images, destinationDirs, duplicates, description, delete)
     
    # Delete the source files.
    if delete:
        print "Deleting images from {0}.\n".format(sourceVol[0])
        shutil.rmtree(sourceVol[1])
        
    # Request the Finder to eject the source volume.
    for attempt in range(1, 20):
        workspace = NSWorkspace.alloc()
        ejected = workspace.unmountAndEjectDeviceAtPath_(os.path.join("/Volumes", sourceVol[0]))
        if ejected:
            break
        print "Attempting to eject {0}...".format(sourceVol[0])
        time.sleep(1)
    if ejected:
        print "All images successfully downloaded and {0} ejected.".format(sourceVol[0])
    else:
        print "ERROR - All images successfully downloaded, but could not eject {0}!".format(sourceVol[0])
     
    return dirName
        
#  CLI Interface
def main(argv=None):

    '''Command line options.'''

    if argv is None:
        argv = sys.argv
    else:
        sys.argv.extend(argv)
        
    program_name = os.path.basename(sys.argv[0])
    program_version = "v%s" % __version__
    program_build_date = str(__updated__)
    program_version_message = '%%(prog)s %s (%s)' % (program_version, program_build_date)
    program_shortdesc = __import__('__main__').__doc__.split("\n")[1]
    program_license = '''%s

  Created by John Dykstra on %s.
  Copyright 2017 John Dykstra. All rights reserved.

  Licensed under the Apache License 2.0
  http://www.apache.org/licenses/LICENSE-2.0

  Distributed on an "AS IS" basis without warranties
  or conditions of any kind, either express or implied.

USAGE
''' % (program_shortdesc, str(__date__))

    caffeinateProcess = None
    
    try:
        # Setup argument parser
        parser = ArgumentParser(description=program_license, formatter_class=RawDescriptionHelpFormatter)
        parser.add_argument("-v", "--verbose", dest="verbose", action="count", help="set verbosity level [default: %(default)s]")
        parser.add_argument("-t", "--tag", dest="tag", default="Downloaded Images", help="Tag used as destination directory name. [default: %(default)s]" )
        parser.add_argument("-d", "--description", dest="description", help="Description saved in each photo's sidecar.")
        parser.add_argument("-D", "--delete", dest="delete", action='store_true', help="Delete files from card after successful download.")
        parser.add_argument("-a", "--automate", dest="automate", action='store_true', help="Execute deleteUnderscore and Photos.")
        parser.add_argument('-V', '--version', action='version', version=program_version_message)
        parser.add_argument("destinations", nargs='*', default=os.getcwd(), help="Destination directories for images;  Defaults to the working directory.")

        # Process arguments
        args = parser.parse_args(argv[1:])
        
        if args.verbose > 0:
            print("Verbose mode on")
    
        if 'darwin' in sys.platform:
            caffeinateProcess = subprocess.Popen(('caffeinate', '-i'))

        dirName = doDownload(args.destinations, args.tag, args.description, args.delete, args.verbose)
        
        if caffeinateProcess != None:
            caffeinateProcess.terminate()

        if args.automate:
            os.system("open -a \"" + lightroom + "\" \"" + os.path.join(args.destinations[0], dirName) + "\"")
       
        return 0
    
    except KeyboardInterrupt:
        print "Keyboard interrupt"
        if caffeinateProcess != None:
            print "Killing caffeinate"
            caffeinateProcess.terminate()
        ### handle keyboard interrupt ###
        return 2
    
    except CLIError, e:
        print e
        if caffeinateProcess != None:
            caffeinateProcess.terminate()
        return 2
    
    except Exception, e:
        print "Exception caught"
        traceback.print_tb(sys.exc_info()[2])
        if caffeinateProcess != None:
            print "Killing caffeinate"
            caffeinateProcess.terminate()
        if DEBUG or TESTRUN:
            raise(e)
        indent = len(program_name) * " "
        sys.stderr.write(program_name + ": " + repr(e) + "\n")
        sys.stderr.write(indent + "  for help use --help\n")
        return 2

if __name__ == "__main__":
    sys.exit(main())
    