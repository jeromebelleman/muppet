#! /usr/bin/env python

'''
Common configuration options
'''

import os
from os.path import expanduser, exists, islink
import pwd, grp
from stat import S_IMODE, S_IRUSR, S_IWUSR, S_IXUSR, S_IRGRP, S_IROTH
from datetime import datetime
from subprocess import Popen, PIPE
import logging
import difflib
import shutil
import errno
from select import select

from mako.template import Template

WARNLINK = "%s is a link, you'd be on for a lot of confusion - aborting edit"
ROOT = '%s/files/root/%s'
USER = '%s/files/user/%s'
IMPORT = 'from muppet.functions import %s'
SUDOERSD = '/etc/sudoers.d'
MODES = {'-rw-r--r--': S_IRUSR | S_IWUSR | S_IRGRP | S_IROTH,
         '-rwxr--r--': S_IRUSR | S_IWUSR | S_IXUSR | S_IRGRP | S_IROTH,
         '-r--r-----': S_IRUSR | S_IRGRP,
         '-r-xr--r--': S_IRUSR | S_IXUSR | S_IRGRP | S_IROTH,
         '-rw-------': S_IRUSR | S_IWUSR,
        }

def include(module):
    '''
    Execute module with common globals
    '''

    execfile('%s/%s.py' % (__muppet__['_directory'], module), __muppet__.copy())

def _messages(proc):
    '''
    Log messages
    '''

    # http://stackoverflow.com/questions/12270645
    while True:
        readies = select([proc.stdout.fileno(), proc.stderr.fileno()], [], [])

        for ready in readies[0]:
            if ready == proc.stdout.fileno():
                logging.debug(proc.stdout.readline().strip())
            elif ready == proc.stderr.fileno():
                logging.warning(proc.stdout.readline().strip())

        if proc.poll() != None:
            break

def run(command):
    '''
    Run command
    '''

    logging.info(command)
    if not __muppet__['_dryrun']:
        proc = Popen(command, shell=True, stdout=PIPE, stderr=PIPE)
        _messages(proc)

def _aptget(command, args, dryrun):
    '''
    Run apt-get
    '''

    cmd = "DEBIAN_FRONTEND=noninteractive apt-get -qy %s%s %s" % \
        ('-s ' if dryrun else '', command, ' '.join(args))
    logging.info(cmd)
    proc = Popen(cmd, shell=True, stdout=PIPE, stderr=PIPE)
    _messages(proc)

def install(*args):
    '''
    Run apt-get install
    '''

    # TODO Compare with a list from apt-cache pkgnames
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
        logging.info("chowning %s:%s %s", owner, group, path)
        if not __muppet__['_dryrun']:
            os.chown(expanduser(path), uid, gid)
        return True
    else:
        return False

def _chmod(path, status, mode):
    '''
    Change mode
    '''

    if mode != S_IMODE(status.st_mode):
        logging.info("chmoding %s %s", oct(mode), path)
        if not __muppet__['_dryrun']:
            os.chmod(expanduser(path), mode)
        return True
    else:
        return False

def _diff(path, contents):
    '''
    Diff config files
    '''

    try:
        configfile = open(expanduser(path))
        diff = list(difflib.unified_diff(configfile.read().splitlines(True),
                                         contents.splitlines(True),
                                         path, '<new>'))
        configfile.close()
        if __muppet__['_verbose'] and diff:
            logging.debug('\n' + ''.join(diff))

        return diff
    except IOError:
        return True

def _template(path):
    '''
    Apply template
    '''

    identifiers = (k for k in __muppet__.keys() if k[0] != '_')
    tpt = Template(filename=path, imports=[IMPORT % ', '.join(identifiers)])
    return tpt.render()

def _backup(path):
    '''
    Backup config file
    '''

    moved = '%s-%s~' % (path, datetime.now().strftime('%Y%m%d_%H%M%S'))
    logging.info("backing up %s to %s", path, moved)
    if exists(expanduser(moved)):
        logging.warning("%s already exists - aborting edit", moved)
        return False
    else:
        if not __muppet__['_dryrun']:
            # Will dereference before copying
            shutil.copy2(expanduser(path), moved)
        return True

def _edit(scope, path, contents):
    '''
    Edit config file
    '''

    logging.info("editing %s", path)
    if not __muppet__['_dryrun']:
        configfile = open(expanduser(path), 'w')
        configfile.write(contents)
        configfile.close()

    logging.info("copying stat to %s", path)
    if not __muppet__['_dryrun']:
        # Will dereference before copying stat
        shutil.copystat(scope % (__muppet__['_directory'], \
                                 path.split('/', 1)[1]),
                        expanduser(path))

def _contents(scope, path, verbatim):
    '''
    Compile config file contents
    '''

    localpath = scope % (__muppet__['_directory'], path.split('/', 1)[1])

    if verbatim:
        configfile = open(localpath)
        contents = configfile.read()
        configfile.close()
    else:
        contents = _template(localpath)

    return contents

def _scope(owner, path):
    '''
    Decide between systemwide and userwide scopes
    '''

    if path[0] == '~':
        return USER, '~%s%s' % (owner, path[1:])
    else:
        return ROOT, path

def edit(path, owner, group, mode, verbatim=True):
    '''
    Edit config file with template
    '''

    change = False

    # Userwide config?
    scope, path = _scope(owner, path)

    if islink(expanduser(path)):
        # If our config file template maps to a symlink, we're on for a lot of
        # confusion, so let's not allow this
        logging.warning(WARNLINK, path)
        return

    # Compile config file contents
    contents = _contents(scope, path, verbatim)

    # Diff
    diff = _diff(path, contents)

    if diff:
        # Back up config file
        if exists(expanduser(path)) and not _backup(path):
            return

        # Edit config file
        _edit(scope, path, contents)
        change = True

    # Change attributes
    if exists(expanduser(path)):
        status = os.stat(expanduser(path))

        # Change owner and group
        change |= _chown(path, status, owner, group)

        # Change mode
        change |= _chmod(path, status, mode)

    return change
        
def isjustinstalled():
    '''
    Check if OS was freshly installed
    '''

    return not exists(__muppet__['_directory'] + '/notjustinstalled')

def notjustinstalled():
    '''
    Mark system as not just installed
    '''

    if not __muppet__['_dryrun']:
        open(__muppet__['_directory'] + '/notjustinstalled', 'w').close()

def islaptop():
    '''
    Check if hardware is laptop
    '''

    return len(os.listdir('/sys/class/power_supply'))

def visudo(filename, verbatim=True):
    '''
    Edit sudoers
    '''

    change = False

    path = '%s/%s' % (SUDOERSD, filename)

    # Compile config file contents
    contents = _contents(ROOT, path, verbatim)

    # Diff
    diff = _diff(path, contents)

    if diff:
        # Edit sudoers file
        try:
            # Check syntax
            args = ['/usr/sbin/visudo', '-c', '-f', '-']
            devnull = open(os.devnull, 'w')
            process = Popen(args, stdin=PIPE, stdout=devnull, stderr=PIPE)
            _, err = process.communicate(contents)
            devnull.close()
            if process.returncode == 0:
                # Back up sudoers file
                if exists(path) and not _backup(path):
                    return

                # Create lockfile
                lockfile = os.open(path + '.tmp', os.O_CREAT | os.O_EXCL)

                # Edit sudoers file
                _edit(ROOT, path, contents)

                # Remove lockfile
                os.close(lockfile)
                os.remove(path + '.tmp')

                change = True
            else:
                logging.warning(err.strip())

        except OSError, exc:
            if exc == errno.EEXIST:
                logging.warning("%s busy - aborting edit", path)

    # Change attributes
    if exists(path):
        status = os.stat(path)

        # Change owner and group
        change |= _chown(path, status, 'root', 'root')

        # Change mode
        change |= _chmod(path, status, MODES['-r--r-----'])

    return change

__muppet__ = {
              'include':           include,
              'run':               run,
              'edit':              edit,
              'visudo':            visudo,
              'install':           install,
              'purge':             purge,
              'isjustinstalled':   isjustinstalled,
              'notjustinstalled':  notjustinstalled,
              'islaptop':          islaptop,
              'MODES':             MODES,
             }
