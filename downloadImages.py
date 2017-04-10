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
'''

import sys
import os
import datetime
import shutil
import traceback

from argparse import ArgumentParser
from argparse import RawDescriptionHelpFormatter

__all__ = []
__version__ = 0.1
__date__ = '2017-04-06'
__updated__ = '2017-04-06'

DEBUG = 1
TESTRUN = 0
PROFILE = 0

downloadPrefix="/Users/jwd/Image Edit"
platform = "Mac"

class CLIError(Exception):
    '''Generic exception to raise and log different fatal errors.'''
    def __init__(self, msg):
        super(CLIError).__init__(type(self))
        self.msg = "E: %s" % msg
    def __str__(self):
        return self.msg
    def __unicode__(self):
        return self.msg

# Find potential source DCF volumes.  Return a list of (name, path) tuples.
def findSourceVolume():
    vollist = []
    for d in os.listdir("/Volumes"):
        if not os.path.isdir(os.path.join("/Volumes", d)):
            continue
        tp = os.path.join(os.path.join("/Volumes", d), "DCIM")
        if os.path.isdir(tp):
            vollist.append((d, tp))
    return vollist;

# Create the destination directory and return a path to it.
def createDestinationDir(name):
    d = os.path.join(downloadPrefix, name)
    
    # If the destination directory already exists, accept that silently.
    if os.path.isdir(d):
        return d
    
    os.makedirs(d)
    return d

# Return a dictionary describing all of the image files on the source..
def findSourceImages(src):
    images = {}
    jpegCnt = 0

    # Ennumerate the image files on the source volume.
    for dirpath, dirs, files in os.walk(src):
        for f in files:
            
            # Ignore files that don't look like camera image files,
            # including hidden files.
            if f.startswith("."):
                continue
            fparts = f.split(".")
            if len(fparts) != 2:
                continue
            name = fparts[0].upper()
            extension = fparts[-1].upper()
            if extension not in ['JPG', 'NEF']:
                continue
            
            # Dictionary "images" is indexed by the image name.  Its entries are themselves
            # disctionaries, containing keys "srcNEF" and/or "srcJPG".  The contents of those
            # entries is a sequence of the patchname followed by the filename.
            if name in images:
                nameentry = images[name]
            else:
                nameentry = {}
            
            nameentry["src" + extension] = (dirpath, f)

            images[name] = nameentry;
            
            if extension == 'JPG':
                jpegCnt += 1

            print(os.path.join(dirpath, f))
        
    if jpegCnt > 0:
         print("WARNING:  {0} JPEG files found!".format(jpegCnt))
    return images

# Look for files already in the destination directory.
def lookForDuplicates(images, dst):
    existingCnt = 0
    
    for name in iter(images):
        for kind in ['srcNEF', 'srcJPG']:
            if kind in images[name]:
                filename = images[name][kind][1]
                dstpath = os.path.join(dst, filename)
                if os.path.exists(dstpath):
                    srcpath = os.path.join(images[name][kind][0], filename)
                    if (os.stat(dstpath).st_size == os.stat(srcpath).st_size):
                        existingCnt += 1
                        images[name]["duplicate"] = True
    
    if existingCnt > 0:
        print("%d image files already exist. " % (existingCnt))    

# Copy the image files from the source to the destination and create the sidecar file.
def copyImageFiles(images, destinationDir, description):

    for name in iter(images):
        if 'duplicate' not in images[name]:
            for kind in ['srcNEF', 'srcJPG']:
                if kind in images[name]:
                    filename = images[name][kind][1]
                    srcpath = os.path.join(images[name][kind][0], filename)
                    dstpath = os.path.join(destinationDir, filename)
                    print "Copying from {0} to {1}.".format(srcpath, dstpath)
                    shutil.copy2(srcpath, dstpath)
            
            # Create the sidecar file.
            sidecar = open(os.path.join(destinationDir, name+".XMP"), "w")
            sidecar.write("<x:xmpmeta xmlns:x=\"adobe:ns:meta/\">\n")
            sidecar.write("<rdf:RDF xmlns:rdf=\"http://www.w3.org/1999/02/22-rdf-syntax-ns#\">\n")
            sidecar.write("\n")
            sidecar.write("  <rdf:Description rdf:about=\"\" xmlns:dc=\"http://purl.org/dc/elements/1.1/\">\n")
            sidecar.write("    <dc:description>\n")
            sidecar.write("      <rdf:Alt>\n")
            sidecar.write("        <rdf:li xml:lang=\"x-default\">{0}&#xA;</rdf:li>\n".format(description))
            sidecar.write("      </rdf:Alt>\n")
            sidecar.write("    </dc:description>\n")
            sidecar.write("  </rdf:Description>\n")
            sidecar.write("\n")
            sidecar.write("</rdf:RDF>\n")
            sidecar.write("</x:xmpmeta>\n")
            sidecar.close()
            
# Programmatic API
def doDownload(tag, description, delete=False, verbose=False):
    
    #  Find the source volume.  We can only handle one.
    sourceVols = findSourceVolume()
    if (len(sourceVols) < 1):
        raise CLIError("Could not find a DCF volume.")
    if (len(sourceVols) > 1):
        raise CLIError("More than one DCF volume found.")
    sourceVol=sourceVols[0]
    print "Downloading images from {0}.".format(sourceVol[0])

    #  Find image files on the source volume.
    images = findSourceImages(sourceVol[1])
    print("Found %d image files." % (len(images)))
    
    # Create the destination directory, if necessary.
    today = datetime.date.today()
    dirName = str(today.month) + "-" + str(today.day) + " " + tag
    destinationDir = createDestinationDir(dirName)
    
    # Look for duplicate image files on the destination.
    lookForDuplicates(images, destinationDir)
    
    # Copy the image files from the source to the destination and create the sidecar files.
    copyImageFiles(images, destinationDir, description)
        
        
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

    try:
        # Setup argument parser
        parser = ArgumentParser(description=program_license, formatter_class=RawDescriptionHelpFormatter)
        parser.add_argument("-v", "--verbose", dest="verbose", action="count", help="set verbosity level [default: %(default)s]")
        parser.add_argument("-t", "--tag", dest="tag", default="Downloaded Images", help="Tag used as destination directory name. [default: %(default)s]" )
        parser.add_argument("-d", "--delete", dest="delete", action='store_true', help="Delete files from card after successful download.")
        parser.add_argument('-V', '--version', action='version', version=program_version_message)
        parser.add_argument("description", default="", help="Description saved in each photo's sidecar.")

        # Process arguments
        args = parser.parse_args()
        if args.verbose > 0:
            print("Verbose mode on")
       
        doDownload(args.tag, args.description, args.delete, args.verbose)
        
        return 0
    
    except KeyboardInterrupt:
        ### handle keyboard interrupt ###
        return 0
    except Exception, e:
        traceback.print_tb(sys.exc_info()[2])
        if DEBUG or TESTRUN:
            raise(e)
        indent = len(program_name) * " "
        sys.stderr.write(program_name + ": " + repr(e) + "\n")
        sys.stderr.write(indent + "  for help use --help\n")
        return 2

if __name__ == "__main__":
    if DEBUG:
        sys.argv.append("-v")
    if TESTRUN:
        import doctest
        doctest.testmod()
    if PROFILE:
        import cProfile
        import pstats
        profile_filename = 'downloadImages_profile.txt'
        cProfile.run('main()', profile_filename)
        statsfile = open("profile_stats.txt", "wb")
        p = pstats.Stats(profile_filename, stream=statsfile)
        stats = p.strip_dirs().sort_stats('cumulative')
        stats.print_stats()
        statsfile.close()
        sys.exit(0)
    sys.exit(main())