#! /usr/bin/env python

import os
from os.path import exists, islink
import stat, pwd, grp
import subprocess
import logging

from mako.template import Template

WARNLINK = "%s is a link, not sure what to do and won't do anything"
FILES = '%s/files/root/%s'
IMPORT = 'from functions import %s'

def include(module):
    execfile('%s/%s.py' % \
        (__globals__['_cfg']['directory'], module), __globals__)

def run(command):
    logging.debug(command)
    if not __globals__['_cfg']['dryrun']:
        subprocess.call(command, shell=True)

def _aptget(command, args, verbose, dryrun):
    cmd = "sudo apt-get %s%s %s" % \
        ('-s ' if dryrun else '', command, ' '.join(args))
    logging.debug(cmd)
    subprocess.call(cmd, shell=True)

def install(*args):
    _aptget('install', args,
            __globals__['_cfg']['verbose'], __globals__['_cfg']['dryrun'])
 
def purge(*args):
    _aptget('purge', args,
            __globals__['_cfg']['verbose'], __globals__['_cfg']['dryrun'])

def edit(path, owner, group, mode):
    status = os.stat(path)

    # Change owner and group
    uid = pwd.getpwnam(owner).pw_uid
    gid = grp.getgrnam(group).gr_gid
    if uid != status.st_uid or gid != status.st_gid:
        # TODO To be tested
        if islink(path):
            logging.warning(WARNLINK % path)
        else:
            logging.debug("chowning %s:%s %s" % (owner, group, path))
            if not __globals__['_cfg']['dryrun']:
                # TODO To be tested
                os.chown(path, uid, gid)

    # Change mode
    if mode != stat.S_IMODE(status.st_mode):
        # TODO To be tested
        if islink(path):
            logging.warning(WARNLINK % path)
        else:
            logging.debug("chmoding %s %s" % oct(mode))
            if not __globals__['_cfg']['dryrun']:
                # TODO To be tested
                os.chmod(path, mode)

    # Apply template
    identifiers = (k for k in __globals__.keys() if k[0] != '_')
    tpt = Template(filename=FILES % \
                   (__globals__['_cfg']['directory'], path[1:]),
                   imports=[IMPORT % ', '.join(identifiers)])
    print tpt.render()

def isfreshinstall():
    return not exists(__globals__['_cfg']['directory'] + '/notjustinstalled')

def islaptop():
    return True

# FIXME Is 'globals' a proper name? How about 'cfg' here and rename 'cfg' to
# something else?
__globals__ = {
               'include':        include,
               'run':            run,
               'edit':           edit,
               'install':        install,
               'purge':          purge,
               'isfreshinstall': isfreshinstall,
               'islaptop':       islaptop,
              }

