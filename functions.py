#! /usr/bin/env python

'''
Common configuration options
'''

import os, sys
from os.path import exists, islink
import stat, pwd, grp
import subprocess
import logging
import difflib

from mako.template import Template

import pprint

WARNLINK = "%s is a link, not sure what to do and won't do anything"
FILES = '%s/files/root/%s'
IMPORT = 'from functions import %s'

def include(module):
    '''
    Execute module with common globals
    '''

    execfile('%s/%s.py' % (__muppet__['_directory'], module), __muppet__)

def run(command):
    '''
    Run command
    '''

    logging.debug(command)
    if not __muppet__['_dryrun']:
        subprocess.call(command, shell=True)

def _aptget(command, args, dryrun):
    '''
    Run apt-get
    '''

    cmd = "sudo apt-get %s%s %s" % \
        ('-s ' if dryrun else '', command, ' '.join(args))
    logging.debug(cmd)
    subprocess.call(cmd, shell=True)

def install(*args):
    '''
    Run apt-get install
    '''

    _aptget('install', args, __muppet__['_dryrun'])
 
def purge(*args):
    '''
    Run apt-get purge
    '''

    _aptget('purge', args, __muppet__['_dryrun'])

def edit(path, owner, group, mode):
    '''
    Edit config file with template
    '''

    status = os.stat(path)

    # Change owner and group
    uid = pwd.getpwnam(owner).pw_uid
    gid = grp.getgrnam(group).gr_gid
    if uid != status.st_uid or gid != status.st_gid:
        # TODO To be tested
        if islink(path):
            logging.warning(WARNLINK, path)
        else:
            logging.debug("chowning %s:%s %s", owner, group, path)
            if not __muppet__['_dryrun']:
                # TODO To be tested
                os.chown(path, uid, gid)

    # Change mode
    if mode != stat.S_IMODE(status.st_mode):
        # TODO To be tested
        if islink(path):
            logging.warning(WARNLINK, path)
        else:
            logging.debug("chmoding %s %s", oct(mode), path)
            if not __muppet__['_dryrun']:
                # TODO To be tested
                os.chmod(path, mode)

    # Apply template
    identifiers = (k for k in __muppet__.keys() if k[0] != '_')
    tpt = Template(filename=FILES % (__muppet__['_directory'], path[1:]),
                   imports=[IMPORT % ', '.join(identifiers)])
    contents = tpt.render()

    # Diff
    configfile = open(path)
    diff = list(difflib.unified_diff(configfile.read().splitlines(True),
                                     contents.splitlines(True),
                                     path, '<new>'))
    configfile.close()
    if __muppet__['_verbose']:
        sys.stdout.writelines(diff)

    # Write config file
    if diff:
        logging.debug("editing %s", path)
        if not __muppet__['_dryrun']:
            # TODO To be tested
            os.chmod(path, mode)
            configfile = open(path, 'w')
            configfile.write(contents)
            configfile.close()
        
def isfreshinstall():
    '''
    Check if OS was freshly installed
    '''

    return not exists(__muppet__['_directory'] + '/notjustinstalled')

def islaptop():
    '''
    Check if hardware is laptop
    '''

    return True

__muppet__ = {
           'include':        include,
           'run':            run,
           'edit':           edit,
           'install':        install,
           'purge':          purge,
           'isfreshinstall': isfreshinstall,
           'islaptop':       islaptop,
          }
