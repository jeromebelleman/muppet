#! /usr/bin/env python

'''
Common configuration options
'''

import os, sys
from os.path import exists, islink
import pwd, grp
from stat import S_IMODE, S_IRUSR, S_IWUSR, S_IXUSR, S_IRGRP, S_IROTH
from datetime import datetime
import subprocess
import logging
import difflib
import shutil

from mako.template import Template

WARNLINK = "%s is a link, you'd be on for a lot of confusion - aborting edit"
FILES = '%s/files/root/%s'
IMPORT = 'from functions import %s'
SUDOERSD = '/etc/sudoers.d'
MODES = {'-rw-r--r--': S_IRUSR | S_IWUSR | S_IRGRP | S_IROTH,
         '-rwxr--r--': S_IRUSR | S_IWUSR | S_IXUSR | S_IRGRP | S_IROTH,
         '-r--r-----': S_IRUSR | S_IRGRP,
        }

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

def _chown(path, status, owner, group):
    '''
    Change owner
    '''

    uid = pwd.getpwnam(owner).pw_uid
    gid = grp.getgrnam(group).gr_gid
    if uid != status.st_uid or gid != status.st_gid:
        logging.debug("chowning %s:%s %s", owner, group, path)
        if not __muppet__['_dryrun']:
            os.chown(path, uid, gid)
        return True
    else:
        return False

def _chmod(path, status, mode):
    '''
    Change mode
    '''

    if mode != S_IMODE(status.st_mode):
        logging.debug("chmoding %s %s", oct(mode), path)
        if not __muppet__['_dryrun']:
            os.chmod(path, mode)
        return True
    else:
        return False

def _diff(path, contents):
    '''
    Diff config files
    '''

    try:
        configfile = open(path)
        diff = list(difflib.unified_diff(configfile.read().splitlines(True),
                                         contents.splitlines(True),
                                         path, '<new>'))
        configfile.close()
        if __muppet__['_verbose']:
            sys.stdout.writelines(diff)

        return diff
    except IOError:
        return True

def _template(path):
    '''
    Apply template
    '''

    identifiers = (k for k in __muppet__.keys() if k[0] != '_')
    tpt = Template(filename=FILES % (__muppet__['_directory'], path[1:]),
                   imports=[IMPORT % ', '.join(identifiers)])
    return tpt.render()

def _backup(path):
    '''
    Backup config file
    '''

    moved = '%s-%s~' % (path, datetime.now().strftime('%Y%m%d_%H%M%S'))
    logging.debug("backing up %s to %s", path, moved)
    if exists(moved):
        logging.warning("%s already exists - aborting edit", moved)
        return False
    else:
        if not __muppet__['_dryrun']:
            shutil.copy2(path, moved) # Will dereference before copying
        return True

def _edit(path, contents):
    '''
    Edit config file
    '''

    if not __muppet__['_dryrun']:
        logging.debug("editing %s", path)
        configfile = open(path, 'w')
        configfile.write(contents)
        configfile.close()

        logging.debug("copying stat to %s", path)
        # Will dereference before copying stat
        shutil.copystat(FILES % (__muppet__['_directory'], path[1:]), path)

def edit(path, owner, group, mode):
    '''
    Edit config file with template
    '''

    change = False

    if islink(path):
        # If our config file template maps to a symlink, we're on for a lot of
        # confusion, so let's not allow this
        logging.warning(WARNLINK, path)
        return

    # Apply template
    contents = _template(path)

    # Diff
    diff = _diff(path, contents)

    if diff:
        # Back up config file
        if exists(path) and not _backup(path):
            return

        # Edit config file
        _edit(path, contents)
        change = True

    # Change attributes
    if exists(path):
        status = os.stat(path)

        # Change owner and group
        change |= _chown(path, status, owner, group)

        # Change mode
        change |= _chmod(path, status, mode)

    return change
        
def isfreshinstall():
    '''
    Check if OS was freshly installed
    '''

    isfi = not exists(__muppet__['_directory'] + '/notjustinstalled')
    open(__muppet__['_directory'] + '/notjustinstalled', 'w').close()

    return isfi

def islaptop():
    '''
    Check if hardware is laptop
    '''

    return len(os.listdir('/sys/class/power_supply'))

def visudo(filename):
    '''
    Edit sudoers
    '''

    change = False

    path = '%s/%s' % (SUDOERSD, filename)

    # Apply template
    contents = _template(path)

    # Diff
    diff = _diff(path, contents)

    if diff:
        # Edit sudoers file
        try:
            # Check syntax
            args = ['/usr/sbin/visudo', '-c', '-f', '-']
            devnull = open(os.devnull, 'w')
            process = subprocess.Popen(args, stdin=subprocess.PIPE,
                                       stdout=devnull, stderr=subprocess.PIPE)
            _, err = process.communicate(contents)
            devnull.close()
            if process.returncode == 0:
                # Back up sudoers file
                if exists(path) and not _backup(path):
                    return

                # Create lockfile
                lockfile = os.open(path + '.tmp', os.O_CREAT | os.O_EXCL)

                # Edit sudoers file
                _edit(path, contents)

                # Remove lockfile
                os.close(lockfile)
                os.remove(path + '.tmp')

                change = True
            else:
                logging.warning(err.strip())

        except OSError:
            logging.warning("%s busy - aborting edit", path)

    # Change attributes
    if exists(path):
        status = os.stat(path)

        # Change owner and group
        change |= _chown(path, status, 'root', 'root')

        # Change mode
        change |= _chmod(path, status, MODES['-r--r-----'])

__muppet__ = {
           'include':        include,
           'run':            run,
           'edit':           edit,
           'visudo':         visudo,
           'install':        install,
           'purge':          purge,
           'isfreshinstall': isfreshinstall,
           'islaptop':       islaptop,
           'MODES':          MODES,
          }
