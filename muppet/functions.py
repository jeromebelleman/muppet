#! /usr/bin/env python
# coding=utf-8

'''
Common configuration options
'''

import os
from os.path import expanduser, islink, isdir
import sys
import pwd
import grp
import stat
from subprocess import Popen, PIPE, call
import logging
import difflib
import re
import shutil
import errno
from select import select
import time
import socket

WARNLINK = "%s is a link, you'd be on for a lot of confusion - aborting change"
ROOT = '%s/files/root/%s'
IMPORT = 'from muppet.functions import %s'
SUDOERSD = '/etc/sudoers.d'
MODES = [stat.S_IRUSR, stat.S_IWUSR, stat.S_IXUSR, stat.S_IRGRP, stat.S_IWGRP,
         stat.S_IXGRP, stat.S_IROTH, stat.S_IWOTH, stat.S_IXOTH]
TIMEFMT = '%Y%m%d_%H%M%S'
REFBSET = re.compile(r'^mode "(\d+)x(\d+).*"$')
REXRANDR = re.compile(r'^\s+(\d+)x(\d+).*$')
REID = re.compile(r'''^uid=(?P<uid>\d+)\([^)]+\)[ ]
                       gid=\d+\((?P<group>[^)]+)\)[ ]
                       groups=(?P<groups>.+)$''', re.VERBOSE)
REFIREWALL = re.compile(r'''^(?P<toport>\d+)(/(?P<proto>\w+))?[ ]+
                             (?P<action>\w+)[ ]+
                             (?P<fromhost>[\d\.]+(/\d+)?)''', re.VERBOSE)
STATUS, NOWHERE, RULES = range(3)

def resource(res):
    '''
    Return resource path
    '''

    return '%s/resources/%s' % (__muppet__['_directory'], res)

def users():
    '''
    Get users involved in configuration
    '''

    try:
        return [(pair.split(':')[0], pair.split(':')[1])
                for pair in __muppet__['_users']]
    except IndexError:
        logging.warning("invalid user:group specification - ignoring")
        return []

def include(module):
    '''
    Execute module with common globals
    '''

    execfile('%s/manifests/%s.py' % \
        (__muppet__['_directory'], module), __muppet__.copy())

def firewall(action=None, fromhost=None, toport=None, proto=None):
    '''
    Set up firewall
    '''

    # Check firewall status
    proc = Popen(['ufw', 'status'], stdout=PIPE, stderr=PIPE)
    out, err = proc.communicate()

    state = STATUS
    currules = set()
    for line in out.splitlines():
        if not line:
            continue
        elif state == STATUS:
            _, status = line.split()
            state = NOWHERE
        elif state == NOWHERE:
            if line[:2] == '--':
                state = RULES
        elif state == RULES:
            match = REFIREWALL.match(line)
            if match:
                currules.add((match.group('action').lower(),
                              match.group('proto'), match.group('fromhost'),
                              int(match.group('toport'))))
            else:
                logging.warn("couldn't parse ufw status: %s", line)

    if proc.returncode:
        logging.warn(err[7:-1])
        return False

    # Enable firewall if needs be
    if status != 'active':
        cmd = ['ufw', 'enable']
        logging.info(' '.join(cmd))
        if not __muppet__['_dryrun']:
            proc = Popen(cmd, stdout=PIPE, stderr=PIPE)
            _messages(proc)

    # Change firewall settings if needs be
    rule = action, proto, fromhost, toport
    if None not in (action, fromhost, toport) and rule not in currules:
        cmd = ['ufw', action]
        if proto:
            cmd.extend(['proto', proto])
        cmd.extend(['from', fromhost, 'to', 'any', 'port', str(toport)])
        logging.info(' '.join(cmd))
        if not __muppet__['_dryrun']:
            proc = Popen(cmd, stdout=PIPE, stderr=PIPE)
            _messages(proc)

def addprinter(name, uri, ppd):
    '''
    Add printer
    '''

    with open(os.devnull, 'w') as devnull:
        args = ['/usr/bin/lpstat', '-p', name]
        if call(args, stdout=devnull, stderr=devnull) != 0:
            _logrun('/usr/sbin/lpadmin',
                    '-E',
                    '-p', name,
                    '-v', uri,
                    '-P' if os.path.exists(ppd) else '-m', ppd,
                    '-E')


def resolution():
    '''
    Get screen resolution
    '''

    # Try with xrandr
    cmd = ['/usr/bin/xrandr']
    logging.debug("getting screen resolution from %s", ' '.join(cmd))
    proc = Popen(cmd, stdout=PIPE, stderr=PIPE)
    for line in proc.stdout:
        match = REXRANDR.match(line)
        if match:
            width, height = match.groups()
            return int(width), int(height)
    logging.debug("couldn't get resolution from %s", ' '.join(cmd))
    for line in proc.stderr:
        logging.debug(line.strip())

    # Try with fbset
    cmd = ['/bin/fbset']
    logging.debug("getting screen resolution from %s instead", ' '.join(cmd))
    proc = Popen(cmd, stdout=PIPE, stderr=PIPE)
    for line in proc.stdout:
        match = REFBSET.match(line)
        if match:
            width, height = match.groups()
            return int(width), int(height)
    for line in proc.stderr:
        logging.debug(line.strip())

    # Default to sensible resolution
    logging.warning("couldn't get resolution - defaulting to 1024×768")
    return 1024, 768

def _messages(proc):
    '''
    Log messages
    '''

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
                # Split lines with '\r' to take only the last chunk as these
                # lines are assumed to be used to show progress and we only
                # need the result
                line = proc.stdout.readline().rstrip().split('\r')[-1]
                if line:
                    logging.debug(line)

                    # Add carriage return that's missing with e.g. apt-get,
                    # then flush
                    print '\r',
                    sys.stdout.flush()
            elif ready == proc.stderr.fileno():
                line = proc.stderr.readline().rstrip().split('\r')[-1]
                if line:
                    logging.warning(line)
                    print >> sys.stderr, '\r',
                    sys.stderr.flush()

def _logrun(*cmd):
    '''
    Run and log messages
    '''

    logging.info(' '.join(cmd))
    if not __muppet__['_dryrun']:
        proc = Popen(cmd, stdout=PIPE, stderr=PIPE)
        _messages(proc)

def _comm(*cmd):
    '''
    Run command and return stdout, stderr
    '''

    return Popen(cmd, stdout=PIPE, stderr=PIPE).communicate()

def run(command):
    '''
    Run command
    '''

    if not __muppet__['_dryrun']:
        proc = Popen(command, shell=True, stdout=PIPE, stderr=PIPE)
        _messages(proc)

def _service(service, action, status):
    '''
    Manage services with init, Upstart and systemd
    '''

    if os.path.exists('/bin/systemctl'): # If it's systemd
        # Enable/disable service if needs be
        isenabled = _comm('/bin/systemctl', 'is-enabled', service)[0].strip()
        if isenabled not in ('enabled', 'disabled'):
            logging.warn("%s is %s, won't enable or disable",
                         service, isenabled)
        elif action not in isenabled: # E.g. 'enable' not in 'disabled'
            _logrun('/bin/systemctl', action, service)

        # Start/stop service if needs be
        isactive = _comm('/bin/systemctl', 'is-active', service)[0].strip()
        if isactive not in ('active', 'inactive'):
            logging.warn("%s is %s, won't start or stop", service, isactive)
        if action == 'enable' and isactive == 'inactive':
            _logrun('/bin/systemctl', 'start', service)
        elif action == 'disable' and isenabled == 'active':
            _logrun('/bin/systemctl', 'stop', service)
    elif os.path.exists('/etc/init/%s.conf' % service): # If it's Upstart
        # Enable/disable service if needs be
        path = '/etc/init/%s.override' % service
        if action == 'enable' and os.path.exists(path):
            logging.info("removing %s", path)
            if not __muppet__['_dryrun']:
                os.remove(path)
        elif action == 'disable' and not os.path.exists(path):
            logging.info("adding %s", path)
            if not __muppet__['_dryrun']:
                fhl = open(path, 'w')
                fhl.write('manual')
                fhl.close()

        # Start/stop service if needs be
        isactive, _ = _comm('/sbin/status', service)
        if 'start' not in isactive and 'stop' not in isactive:
            logging.warn("%s is %s, won't start or stop", service, isactive)
        if action == 'enable' and 'stop' in isactive:
            _logrun('/sbin/start', service)
        elif action == 'disable' and 'start' in isactive:
            _logrun('/sbin/stop', service)
    else: # If it's init, which still does happen with Raring
        # Enable/disable service if needs be
        for filename in os.listdir('/etc/rc2.d'):
            if service == filename[3:]:
                isenabled = 'enabled' if filename[0] == 'S' else 'disabled'
                if action not in isenabled: # E.g. 'enable' not in 'disabled'
                    _logrun('/usr/sbin/update-rc.d', service, action)

        # Start/stop service if needs be
        isactive, _ = _comm('/usr/sbin/service', service, 'status')
        if status and status in isactive:
            if action == 'enable':
                _logrun('/usr/sbin/service', service, 'start')
            elif action == 'disable':
                _logrun('/usr/sbin/service', service, 'stop')

def enable(service, status=None):
    '''
    Enable and turn on service
    '''

    _service(service, 'enable', status)

def disable(service, status=None):
    '''
    Disable and turn off service
    '''

    _service(service, 'disable', status)

def _getmaintainer(maintainer):
    '''
    Return set of custom-built packages
    '''

    cmd = ['dpkg-query', '--show', '--showformat',
           '${Package} ${Maintainer}\\n']
    proc = Popen(cmd, stdout=PIPE)
    maintained = set()
    for line in proc.stdout:
        pkg, mtr = line[:-1].split(None, 1)
        if mtr == maintainer:
            maintained.add(pkg)

    return maintained

def getselections():
    '''
    Return set of installed packages
    '''

    # Get set of already-installed packages
    # ubuntu list packages which are installed
    # -> http://askubuntu.com/questions/17823/how-to-list-all-installed-packages
    proc = Popen(['/usr/bin/dpkg', '--get-selections'], stdout=PIPE)
    installed = set()
    for line in proc.stdout:
        # Get rid of possible ':amd64'-like suffixes
        # Never seen a package name with ':' in 40k+ packages
        installed.add(line.split()[0].rsplit(':', 1)[0])

    return installed

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

    # Install packages if needs be
    toinstall = set(args) - getselections()
    if toinstall:
        _aptget('install', toinstall, __muppet__['_dryrun'])

def purge(*args, **maintainer):
    '''
    Run apt-get purge
    '''

    # Remove packages if needs be
    topurge = set(args) & getselections()
    if 'maintainer' in maintainer:
        topurge -= _getmaintainer(maintainer['maintainer'])

    if topurge:
        _aptget('purge', topurge, __muppet__['_dryrun'])

def aptkey(keyfile):
    '''
    Run apt-key add
    '''

    devnull = open(os.devnull, 'w')

    # Get fingerprint
    cmd = ['/usr/bin/gpg', '--with-fingerprint', keyfile]
    proc = Popen(cmd, stdout=PIPE, stderr=devnull)
    for line in proc.stdout:
        if 'Key fingerprint' in line:
            fingerprint = line.split('=')[1].strip()
            # Don't break lest gpg may not end

    # Do we already have a key with this fingerprint?
    cmd = ['/usr/bin/apt-key', 'fingerprint']
    proc = Popen(cmd, stdout=PIPE, stderr=devnull)
    exists = False
    for line in proc.stdout:
        if fingerprint in line:
            exists = True
            # Don't break lest gpg may not end

    # Add key if needs be
    if not exists:
        cmd = ['/usr/bin/apt-key', 'add', keyfile]
        logging.info(' '.join(cmd))
        if not __muppet__['_dryrun']:
            proc = Popen(cmd, stdout=PIPE, stderr=PIPE)
            _messages(proc)

    devnull.close()

def addmuppetrepo():
    '''
    Add muppet repository
    '''

    path = '/etc/apt/sources.list.d/muppet.list'
    if os.path.exists(path):
        return False
    else:
        logging.info("adding muppet repository")
        if not __muppet__['_dryrun']:
            with open(path, 'w') as fhl:
                fmt = 'deb [ trusted=yes ] file:%s/repository/%s ./'
                print >> fhl, fmt % (__muppet__['_directory'], architecture())

        return True

def adduser(user, password, shell):
    '''
    Add user
    '''

    # TODO Check if user is already there

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

def addgroup(group, gid=None):
    '''
    Add group
    '''

    # Does this group already exist?
    groups = open('/etc/group')
    for line in groups:
        knowngroup, _, knowngid, _ = line.split(':', 3)
        if group == knowngroup:
            if gid != int(knowngid):
                logging.warning("%s exists but with GID %s", group, knowngid)
            groups.close()
            return
    groups.close()

    # Add group
    cmd = ['/usr/sbin/groupadd']
    if gid:
        cmd.extend(['-g', str(gid)])
    cmd.append(group)
    logging.info(' '.join(cmd))
    if not __muppet__['_dryrun']:
        proc = Popen(cmd, stdout=PIPE, stderr=PIPE)
        _messages(proc)

def usermod(login, uid=None, group='', groups=[]):
    '''
    Modify user account
    '''

    # Check user and groups
    proc = Popen(['id', login], stdout=PIPE)
    match = REID.match(proc.stdout.next())
    curuid = int(match.group('uid'))
    curgid = match.group('group')
    curgroups = set([secgrp.split('(')[1][:-1]
                     for secgrp in match.group('groups').split(',')])

    # Change user and groups if needs be
    uid = ['-u', str(uid)] if uid and uid != curuid else []
    group = ['-g', group] if group and group != curgid else []
    groupstoadd = set(groups) - curgroups
    groups = ['-a', '-G', ','.join(groupstoadd)] if groupstoadd else []

    if uid or group or groups:
        cmd = ['/usr/sbin/usermod'] + uid + group + groups + [login]
        logging.info(' '.join(cmd))
        if not __muppet__['_dryrun']:
            # Kill session, because the user to mod probably has processes there
            if uid:
                if not __muppet__['_sid']:
                    logging.warning("won't run usermod without daemonising")
                    return
                call(['/usr/bin/pkill', '-s', str(__muppet__['_sid'])])
                while call(['/usr/bin/pgrep', '-s0']) == 0:
                    time.sleep(5)

            # Run usermod
            proc = Popen(cmd, stdout=PIPE, stderr=PIPE)
            _messages(proc)

def _chown(path, status, owner, group, link=False):
    '''
    Change owner
    '''

    uid = pwd.getpwnam(owner).pw_uid
    gid = grp.getgrnam(group).gr_gid
    if os.path.ismount(expanduser(path)):
        logging.warn("%s is a mountpoint - won't chown", path)
    elif uid != status.st_uid or gid != status.st_gid:
        logging.info("chowning %s:%s %s", owner, group, path)
        if not __muppet__['_dryrun']:
            if link:
                os.lchown(expanduser(path), uid, gid)
            else:
                os.chown(expanduser(path), uid, gid)
        return True
    return False

def chmod(path, modestr):
    '''
    Change mode
    '''

    try:
        status = os.stat(expanduser(path))

        # Translate a human-readable mode into a machine-readable one
        if len(modestr) != 10:
            logging.warning("invalid %s mode - aborting chmod", modestr)
            return False
        mode = 0
        for i, char in enumerate(modestr[1:]):
            if char != '-':
                mode |= MODES[i]

        if os.path.ismount(expanduser(path)):
            logging.warn("%s is a mountpoint - won't chmod", path)
        elif mode != stat.S_IMODE(status.st_mode):
            logging.info("chmoding %s %s", oct(mode), path)
            if not __muppet__['_dryrun']:
                os.chmod(expanduser(path), mode)
            return True
    except OSError, exc:
        logging.warning(exc)

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
            logging.debug('diff:\n' + ''.join(diff))

        return diff
    except IOError:
        return True

def _template(path, variables):
    '''
    Apply template
    '''
    from mako.template import Template

    identifiers = (k for k in __muppet__.keys() if k[0] != '_')
    tpt = Template(filename=path, imports=[IMPORT % ', '.join(identifiers)])
    return tpt.render(**variables) if variables else tpt.render()

def _backup(path):
    '''
    Backup config file
    '''

    components = expanduser(path).split('/')

    # Create backup directory
    now = __muppet__['_time'].strftime(TIMEFMT)
    backupdir = '%s/backups/%s' % (__muppet__['_directory'], now)
    if not os.path.exists(backupdir) and not __muppet__['_dryrun']:
        os.makedirs(backupdir)

    # Create local directories if needs be
    for i, _ in enumerate(components[1:-1], 2):
        localdir = '%s/%s' % (backupdir, '/'.join(components[1:i]))
        if not os.path.exists(localdir) and not __muppet__['_dryrun']:
            os.mkdir(localdir)

    # Write file backups
    logging.info("backing up %s to %s", path, localdir)
    localpath = '%s/%s' % (localdir, components[-1])
    if os.path.exists(localpath):
        logging.warning("%s already exists - aborting edit", localpath)
        return False
    else:
        if not __muppet__['_dryrun']:
            # Will dereference before copying
            try:
                shutil.copy2(expanduser(path), localpath)
            except IOError, exc:
                logging.warning(exc)
                return False

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

def _edit(srcpath, path, contents):
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
        shutil.copystat(srcpath, expanduser(path))

def _contents(srcpath, variables):
    '''
    Compile config file contents
    '''

    if variables:
        # TODO Gracefully skip applying template when Mako is missing,
        # and suggest it be installed
        contents = _template(srcpath, variables)
    else:
        configfile = open(srcpath)
        contents = configfile.read()
        configfile.close()

    return contents

def mkdir(path, owner, group, mode):
    '''
    Make directory and set attributes
    '''

    change = False

    try:
        # Make directory
        if not os.path.lexists(expanduser(path)):
            logging.info("making directory %s", path)
            if not __muppet__['_dryrun']:
                os.mkdir(expanduser(path))
            change |= True

        if isdir(expanduser(path)):
            # Change ownership
            change |= _chown(path, os.stat(expanduser(path)), owner, group)

            # Change mode
            change |= chmod(path, mode)
        elif not __muppet__['_dryrun']:
            logging.warn("%s isn't a directory - aborting", path)
    except OSError, exc:
        logging.warning(exc)

    return change


def symlink(source, name, owner, group):
    '''
    Make symbolic link
    '''

    change = False

    try:
        # Create link
        if not os.path.lexists(expanduser(name)):
            logging.info("symlinking %s to %s", source, name)
            if not __muppet__['_dryrun']:
                # Make link
                os.symlink(expanduser(source), expanduser(name))
            change |= True

        # Change ownership
        if islink(expanduser(name)):
            change |= _chown(expanduser(name), os.lstat(expanduser(name)),
                             owner, group, True)
        elif not __muppet__['_dryrun']:
            logging.warn("%s isn't a link - aborting", name)
    except OSError, exc:
        logging.warning(exc)

    return change

def mv(src, dst):
    '''
    Move file
    '''

    if os.path.lexists(expanduser(dst)):
        logging.warn("won't move %s to %s, file already exists", src, dst)
    else:
        logging.info("moving %s to %s", src, dst)
        if not __muppet__['_dryrun']:
            shutil.move(expanduser(src), expanduser(dst))

        return True

def rmtree(path):
    '''
    Recursively remove files
    '''

    logging.info("recursively removing %s", path)
    if not __muppet__['_dryrun']:
        shutil.rmtree(expanduser(path))
    return True

def edit(srcpath, path, owner, group, mode, variables=None):
    '''
    Edit config file with template
    '''

    change = False

    srcpath = '%s/files/%s' % (__muppet__['_directory'], srcpath)

    if islink(expanduser(path)):
        # If our config file template maps to a symlink, we're on for a lot of
        # confusion, so let's not allow this
        logging.warning(WARNLINK, path)
        return False

    try:
        # Compile config file contents
        contents = _contents(srcpath, variables)

        # Diff
        diff = _diff(path, contents)

        if diff:
            # Back up config file
            if os.path.exists(expanduser(path)) and not _backup(path):
                return False

            # Edit config file
            _edit(srcpath, path, contents)
            change = True

        # Change attributes
        if os.path.exists(expanduser(path)):
            status = os.stat(expanduser(path))

            # Change owner and group
            change |= _chown(path, status, owner, group)

            # Change mode
            change |= chmod(path, mode)
    except IOError, exc:
        logging.warning(exc)
        return False

    return change

def isjustinstalled():
    '''
    Check if OS was freshly installed
    '''

    return not os.path.exists(__muppet__['_directory'] + '/notjustinstalled')

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

def visudo(srcpath, filename, variables=None):
    '''
    Edit sudoers
    '''

    change = False

    path = '%s/%s' % (SUDOERSD, filename)
    srcpath = '%s/files/%s' % (__muppet__['_directory'], srcpath)

    # Compile config file contents
    contents = _contents(srcpath, variables)

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
                if os.path.exists(path) and not _backup(path):
                    return

                # Create lockfile
                lockfile = os.open(path + '.tmp', os.O_CREAT | os.O_EXCL)

                # Edit sudoers file
                _edit(srcpath, path, contents)

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
    if os.path.exists(path):
        status = os.stat(path)

        # Change owner and group
        change |= _chown(path, status, 'root', 'root')

        # Change mode
        change |= chmod(path, '-r--r-----')

    return change

def hostname():
    '''
    Return host name
    '''

    return socket.gethostname()

def architecture():
    '''
    Return architecture from dpkg
    '''

    proc = Popen(['/usr/bin/dpkg', '--print-architecture'], stdout=PIPE)
    out, _ = proc.communicate()
    return out.strip()

def release():
    '''
    Return Ubuntu release
    '''

    devnull = open(os.devnull, 'w')
    proc = Popen(['/usr/bin/lsb_release', '-rs'], stdout=PIPE, stderr=devnull)
    out, _, = proc.communicate()
    devnull.close()
    return out.strip()

__muppet__ = {
    # Services
    'enable':             enable,
    'disable':            disable,

    # Editing
    'edit':               edit,
    'visudo':             visudo,

    # Filesystem
    'mkdir':              mkdir,
    'symlink':            symlink,
    'mv':                 mv,
    'rmtree':             rmtree,
    'chmod':              chmod,
    'resource':           resource,

    # Package management
    'install':            install,
    'purge':              purge,
    'getselections':      getselections,
    'aptkey':             aptkey,
    'addmuppetrepo':      addmuppetrepo,

    # User management
    'adduser':            adduser,
    'addgroup':           addgroup,
    'usermod':            usermod,
    'users':              users,

    # Flow control
    'include':            include,
    'resolution':         resolution,
    'islaptop':           islaptop,
    'hostname':           hostname,
    'architecture':       architecture,
    'release':            release,
    'isjustinstalled':    isjustinstalled,
    'notjustinstalled':   notjustinstalled,

    # Miscellaneous
    'run':                run,
    'firewall':           firewall,
    'addprinter':         addprinter,
}
