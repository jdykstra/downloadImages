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

from argparse import ArgumentParser
from argparse import RawDescriptionHelpFormatter

__all__ = []
__version__ = 0.1
__date__ = '2017-04-06'
__updated__ = '2017-04-06'

DEBUG = 1
TESTRUN = 0
PROFILE = 0

global args
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


def findSourceVolume():
    vollist = []
    for d in os.listdir("/Volumes"):
        if not os.path.isdir(os.path.join("/Volumes", d)):
            continue
        tp = os.path.join(os.path.join("/Volumes", d), "DCIM")
        if os.path.isdir(tp):
            vollist.append(d)
    return vollist;

def main(argv=None): # IGNORE:C0111
    '''Command line options.'''

    global args
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
        parser.add_argument("-t", "--tag", dest="tag", default="Downloaded Images", help="Tag used as destination directory name. [default: %(default)s]", metavar="TAG" )
        parser.add_argument("-d", "--description", dest="description", default="No description provided.", help="Description saved in each photo's sidecar. [default: %(default)s]", metavar="DESC" )
        parser.add_argument('-V', '--version', action='version', version=program_version_message)

        # Process arguments
        '''print "Before parse_args"
        args = parser.parse_args()
        print "After parse_args"
        if args.verbose > 0:
            print("Verbose mode on")'''
       
        sourceVols = findSourceVolume()
        if (len(sourceVols) < 1):
            raise CLIError("Could not find a DCF volume.")
        if (len(sourceVols) > 1):
            raise CLIError("More than one DCF volume found.")
        sourceVol=sourceVols[0]
        print "Downloading images from {0}.".format(sourceVol)
        return 0
    
    except KeyboardInterrupt:
        ### handle keyboard interrupt ###
        return 0
    except Exception, e:
        if DEBUG or TESTRUN:
            raise(e)
        indent = len(program_name) * " "
        sys.stderr.write(program_name + ": " + repr(e) + "\n")
        sys.stderr.write(indent + "  for help use --help")
        return 2

if __name__ == "__main__":
    if DEBUG:
        sys.argv.append("-h")
        sys.argv.append("-v")
        sys.argv.append("-r")
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