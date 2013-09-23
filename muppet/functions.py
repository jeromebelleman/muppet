#! /usr/bin/env python
# coding=utf-8

'''
Common configuration options
'''

import os
from os.path import expanduser, exists, islink
import pwd, grp
import stat
from subprocess import Popen, PIPE
import logging
import difflib
import re
import shutil
import errno
from select import select

from mako.template import Template

WARNLINK = "%s is a link, you'd be on for a lot of confusion - aborting change"
ROOT = '%s/files/root/%s'
IMPORT = 'from muppet.functions import %s'
SUDOERSD = '/etc/sudoers.d'
MODES = [stat.S_IRUSR, stat.S_IWUSR, stat.S_IXUSR, stat.S_IRGRP, stat.S_IWGRP,
         stat.S_IXGRP, stat.S_IROTH, stat.S_IWOTH, stat.S_IXOTH]
TIMEFMT = '%Y%m%d_%H%M%S'
RERES = re.compile('^mode "(\d+)x(\d+).*"$')

def resources():
    '''
    Return resources directory
    '''

    return '%s/resources' % __muppet__['_directory']

def users():
    '''
    Get users involved in configuration
    '''

    try:
        return [(pair.split(':')[0], pair.split(':')[1])
                for pair in __muppet__['_users']]
    except IndexError:
        logging.warning("Invalid user:group specification - ignoring")
        return []

def include(module):
    '''
    Execute module with common globals
    '''

    execfile('%s/%s.py' % (__muppet__['_directory'], module), __muppet__.copy())

def resolution():
    proc = Popen(['/bin/fbset'], stdout=PIPE)
    for line in proc.stdout:
        match = RERES.match(line)
        if match:
            width, height = match.groups()
            return int(width), int(height)
    else:
        logging.warning("Couldn't get resolution - defaulting to 1024×768")
        return 1024, 768

def _messages(proc):
    '''
    Log messages
    '''

    # FIXME apt-get messes up indents in stdout (not in files)

    # http://stackoverflow.com/questions/12270645
    while True:
        # Has the child exited yet?
        returncode = proc.poll()
        if returncode != None:
            return returncode

        # Check if there's data ready
        readies = select([proc.stdout.fileno(), proc.stderr.fileno()], [], [])

        # Write data
        for ready in readies[0]:
            if ready == proc.stdout.fileno():
                line = proc.stdout.readline().strip()
                if line:
                    logging.debug(line)
            elif ready == proc.stderr.fileno():
                line = proc.stderr.readline().strip()
                if line:
                    logging.warning(line)

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

    cmd = "DEBIAN_FRONTEND=noninteractive /usr/bin/apt-get -qy %s%s %s" % \
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

def adduser(user, password, shell):
    '''
    Add user
    '''

    # Create user without password, preventing him from logging in
    cmd = ['/usr/sbin/useradd', '-m', user, '-s', shell]
    logging.info(' '.join(cmd))
    if not __muppet__['_dryrun']:
        proc = Popen(cmd, stderr=PIPE)
        _, err = proc.communicate()
        for line in err.splitlines():
            logging.warning(line)

    # Set encrypted password, allowing him to log in
    cmd = ['/usr/sbin/chpasswd', '-e']
    logging.info(' '.join(cmd))
    if not __muppet__['_dryrun'] and proc.returncode == 0:
        proc = Popen(cmd, stdin=PIPE, stderr=PIPE)
        _, err = proc.communicate('%s:%s' % (user, password))
        for line in err.splitlines():
            logging.warning(line)

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

def _chmod(path, status, modestr):
    '''
    Change mode
    '''

    # Translate a human-readable mode into a machine-readable one
    if len(modestr) != 10:
        logging.warning("invalid %s mode - aborting chmod", modestr)
        return False
    mode = 0
    for i, char in enumerate(modestr[1:]):
        if char != '-':
            mode |= MODES[i]

    if mode != stat.S_IMODE(status.st_mode):
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

def _template(path, variables):
    '''
    Apply template
    '''

    identifiers = (k for k in __muppet__.keys() if k[0] != '_')
    tpt = Template(filename=path, imports=[IMPORT % ', '.join(identifiers)])
    return tpt.render(**variables) if variables else tpt.render()

def _backup(path):
    '''
    Backup config file
    '''

    components = expanduser(path).split('/')

    # Create backup directory
    time = __muppet__['_time'].strftime(TIMEFMT)
    backupdir = '%s/backups/%s' % (__muppet__['_directory'], time)
    if not exists(backupdir) and not __muppet__['_dryrun']:
        os.makedirs(backupdir)

    # Create local directories if needs be
    for i, _ in enumerate(components[1:-1], 2):
        localdir = '%s/%s' % (backupdir, '/'.join(components[1:i]))
        if not exists(localdir) and not __muppet__['_dryrun']:
            os.mkdir(localdir)

    # Write file backups
    logging.info("backing up %s to %s", path, localdir)
    localpath = '%s/%s' % (localdir, components[-1])
    if exists(localpath):
        logging.warning("%s already exists - aborting edit", localpath)
        return False
    else:
        if not __muppet__['_dryrun']:
            # Will dereference before copying
            shutil.copy2(expanduser(path), localpath)

            status = os.stat(expanduser(path))
            os.chown(localpath, status.st_uid, status.st_gid)

    # Fix directory stats
    for i, _ in enumerate(components[1:-1], 2):
        localdir = '%s/%s' % (backupdir, '/'.join(components[1:i]))
        if not __muppet__['_dryrun']:
            shutil.copystat('/'.join(components[:i]), localdir)

            status = os.stat('/'.join(components[:i]))
            os.chown(localdir, status.st_uid, status.st_gid)

    return True

def _edit(localpath, path, contents):
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
        shutil.copystat(localpath, expanduser(path))

def _contents(localpath, variables, verbatim):
    '''
    Compile config file contents
    '''

    if verbatim:
        configfile = open(localpath)
        contents = configfile.read()
        configfile.close()
    else:
        contents = _template(localpath, variables)

    return contents

def _mkdir(localpath, path):
    '''
    Make directory
    '''

    logging.info("making directory %s", path)
    if not __muppet__['_dryrun']:
        os.mkdir(expanduser(path))

    logging.info("copying stat to %s", path)
    if not __muppet__['_dryrun']:
        # Will dereference before copying stat
        shutil.copystat(localpath, expanduser(path))

def mkdir(path, owner, group, mode):
    '''
    Make directory and set attributes
    '''

    change = False

    # Get local path 
    localpath = _localpath(path)

    if islink(expanduser(path)):
        # If this directory maps to a symlink, we're on for a lot of confusion,
        # so let's not allow this
        logging.warning(WARNLINK, path)
        return

    # Make directory
    if not os.path.isdir(expanduser(path)):
        _mkdir(localpath, path)
        change = True

    # Change attributes
    if exists(expanduser(path)):
        status = os.stat(expanduser(path))

        # Change owner and group
        change |= _chown(path, status, owner, group)

        # Change mode
        change |= _chmod(path, status, mode)

    return change

def _localpath(path):
    '''
    Get local path
    '''

    for entry in pwd.getpwall():
        if entry[5] != '/' and expanduser(path).startswith(entry[5]):
            localpath = '/files/user' + expanduser(path)[len(entry[5]):]
            break
    else:
        localpath = '/files/root' + path


    return __muppet__['_directory'] + localpath

def edit(path, owner, group, mode, variables=None, verbatim=True):
    '''
    Edit config file with template
    '''

    change = False

    # Get local path 
    localpath = _localpath(path)

    if islink(expanduser(path)):
        # If our config file template maps to a symlink, we're on for a lot of
        # confusion, so let's not allow this
        logging.warning(WARNLINK, path)
        return False

    # Compile config file contents
    contents = _contents(localpath, variables, verbatim)

    # Diff
    diff = _diff(path, contents)

    if diff:
        # Back up config file
        if exists(expanduser(path)) and not _backup(path):
            return False

        # Edit config file
        _edit(localpath, path, contents)
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

def visudo(filename, variables=None, verbatim=True):
    '''
    Edit sudoers
    '''

    change = False

    path = '%s/%s' % (SUDOERSD, filename)

    # Get local path 
    localpath = _localpath(path)

    # Compile config file contents
    contents = _contents(localpath, variables, verbatim)

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
                _edit(localpath, path, contents)

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
        change |= _chmod(path, status, '-r--r-----')

    return change

__muppet__ = {
              'include':           include,
              'run':               run,
              'edit':              edit,
              'mkdir':             mkdir,
              'visudo':            visudo,
              'install':           install,
              'purge':             purge,
              'adduser':           adduser,
              'users':             users,
              'resources':         resources,
              'resolution':        resolution,
              'isjustinstalled':   isjustinstalled,
              'notjustinstalled':  notjustinstalled,
              'islaptop':          islaptop,
              'MODES':             MODES,
             }
