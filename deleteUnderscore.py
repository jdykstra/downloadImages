#! /usr/bin/env python

import errno, os, stat, sys, subprocess
import argparse

""" 
Delete underscores in camera image filenames.

Usage:
python deleteUnderscore.py  --remove-underscores [directory]
"""
version = "0.2"

global args

class Error:
    def __init__(self, msg, abort = True):
        self.msg = msg
        self.abort = abort

    def __repr__(self):
        return self.msg
    
    def report(self):
        if self.abort:
            fate = "abort"
        else:
            fate = "continue"
        raw_input("{0}.  Hit <enter> to {1}.".format(self.msg, fate))
        if self.abort:
            exit(1)

#  Process all files in one directory."
def doOneDirectory(dirpath, filenames):
    for leaf in filenames:
        doOneFile(dirpath, leaf)

# Do the requested processing on one file"
def doOneFile(dirpath, filename):
    #  Only touch image files and their sidecars.
    name, ext = os.path.splitext(filename)
    if not ext.lower() in {".nef", ".jpg", ".jpeg", ".tif", ".tiff", ".xmp"}:
        return
    
    # Sanity-check filenames to reduce the chance of us touching something
    # we shouldn't.
    if name[0] in {"_"} and name[1] not in {"C"}:
        return
    if name[0] in {"C"} and name[3] not in {"_"}:
        return
    
    #  Delete underscores."
    if args.delete_underscores:
        newname = filename.replace("_", "")
        newfullpath = os.path.join(dirpath, newname)
        
        # Explicitly check for the new name already existing.  Windows will throw an
        # exception if it does, but UNIX will silently delete the old file.
        if os.access(newfullpath, os.F_OK):
            raise Error(newfullpath + " already exists")
        os.rename(os.path.join(dirpath, filename), newfullpath)
        if args.progress:
            sys.stdout.write("{0} -> {1}\n".format(filename, newname))
        

def main(argv = None):    
    global args
    
    if argv is None:
        argv = sys.argv
    else:
        sys.argv.extend(argv)

    parser = argparse.ArgumentParser(description="Manage camera image files")
    parser.add_argument("--recursive", action="store_true", help="Recurse into subdirectories.")
    parser.add_argument("--delete-underscores", action="store_true", help="Remove underscores in filenames.")
    parser.add_argument("--run", help="Name of program to run, with target directory as its parameter.")
    parser.add_argument('--progress', action='store_true', help="Print what is done to each file.")
    parser.add_argument('--version', action='version', version='%(prog)s ' + version)
    parser.add_argument("dir", nargs='?', default=os.getcwd(), help="Directory containing files;  Use the working directory if not specified.")
    args = parser.parse_args(argv[1:])
    
    try:
        if args.recursive:
            dirs = os.walk(args.dir)
            for dir in dirs:
                doOneDirectory(dir[0], dir[2])
        else:
            doOneDirectory(args.dir, os.listdir(args.dir))
    except Error as e:
        e.report()
    
    #  Now run the external program, if specified.  Because this passes the start command"
    #  to the OS shell, it is Windows-specific."
    if args.run != None:
        os.system("start \"\" \""+args.run +"\" \""+args.dir+"\"")
            
if __name__ == '__main__':
    main()
    exit(0)