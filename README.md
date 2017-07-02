A fast, server-less configuration management system with full-Python manifests.

# NAME

muppet – Configuration management tool

# SYNOPSIS

See **muppet -h**.

# DESCRIPTION

Manage Debian-based system configurations from manifests written in Python.

# SUB-COMMANDS

apply
:   Apply the muppet configuration.

encrypt
:   Prompt for a password, an encrypted version of which will be printed.

build
:   Build packages specified in **/var/lib/muppet/repository.yaml**
    (or wherever the muppet directory is). This **repository.yaml** file
    looks like:

    ```
    packages:

        ~/foo:

        ~/bar-1.0-x86_64:
            package: 'bar'
            arch: 'amd64'

        ~/baz-2.0-i686:
            package: 'baz'
            architecture: 'i386'
            cmd: 'dpkg-deb -b baz-2.0 && cp *.deb {repository}/{architecture}'

    defaults:
        cmd: 'make distclean &&
            make &&
            cp -va {package}*.deb {repository}/{architecture} &&
            make distclean'
    ```

    Under **packages** is a list of paths to build the packages from.

      - Without anything otherwise specified, it is assumed packages are
        named after the directory they're build from (e.g. **foo**, here).
      - If it can't be guessed from the path, the package can be specified
        with the **package** key (e.g. **bar**, here).
      - The architecture defaults to whatever **dpkg --print-architecture**
        prints out and can be overridden with the **architecture** key
        (e.g. **bar**, here).
      - The default command run to build and deploy packages is specified
        with the **cmd** key under **defaults** and can be overridden on a
        per-package basis with the **cmd** key (e.g. **baz**, here).

# MUPPET DIRECTORY

The **/var/lib/muppet** directory – or whatever **-d** points to – contains
various files and directories:

backups/
:   Files which are backed up before they are changed.

files/
:   Static or templated files, which the **edit()** function uses.

manifests/
:   Python scripts executed to apply the configuration, having convenience
    functions in their scope. The entry point is **index.py** which typically
    refers to other ones with **include()**. Modules should have the **.py**
    extension.

    You can call **sys.exit(0)** anywhere in a manifest to interrupt applying
    the muppet configuration. Muppet will actually catch this to gracefully
    exit.

    Modules such as **sys** and **os** aren't imported by default, but you
    can do so yourself with **import** as you would do in Python.

resources/
:   Files made available to functions in manifests from the path returned
    by **resource()**.

repository/
:   DEB package repository, which can be added to **/etc/apt/sources.list.d**
    by running **addmuppetrepo()** from a manifest.

Logging messages of changes made are recorded into **/var/log/muppet.log**,
or wherever **-l** points to.

# SERVICES

enable('service', status=None)
:   Start and enable **service** for startup at boot time, either the init
    way, the Upstart way or the systemd way.

disable('service', status=None)
:   Stop and disable **service** for startup at boot time, either the init
    way, the Upstart way or the systemd way.

For init scripts, use the **status** parameter to specify part of the message
you would expect if the service wasn't in the status you want, in which case
the status change will be carried out.

# TEMPLATES

Config files can be templated in the Mako language
(http://docs.makotemplates.org/en/latest/syntax.html).  Variables look like
**${name}**, conditionals look like:

```
% if name == 'saucy':
deb cdrom:[Ubuntu 13.10 _Saucy Salamander_]/ saucy main restricted
% elif name == 'raring':
deb cdrom:[Ubuntu 13.04 _Raring Ringtail_]/ raring main restricted
```

Lines commented out start with **##**. If you need a verbatim **##**, write
**`${'##'}`**. End-of-line backslashes consume newlines. Likewise,
**`${'\\\\'}`** if you need a verbatim one.

# EDITING FUNCTIONS

edit('srcpath', 'path', 'owner', 'group', 'mode', variables=None)
:   Write file to **path** from the one in **srcpath** relative to
    **/var/lib/muppet/files**.  The **owner** and **group** parameters are
    straightforward.  The **mode** parameter looks like **-rwxr-xr-x**. Note
    in particular the leading **-**.

visudo('srcpath', 'filename', variables=None)
:   Write file to **path** from the one in **srcpath** relative to
    **/var/lib/muppet/files**.

The **variables** parameter is a dictionary mapping each variable available
in the template to a value. For instance, **variable={'name': 'foo'}**,
will cause **${name}** to evaluate to **foo** in the config file.  If empty
or **None**, which is the default, it will cause templating to be disabled.

# FILESYSTEM FUNCTIONS

mkdir('path', 'owner', 'group', 'mode')
:   Make directory at **path** setting the ownership to **owner** and
    **group**.  The **mode** parameter looks like **-rwxr-xr-x**. Note in
    particular the leading **-**.

symlink('source', 'name', 'owner', 'group')
:   Make symbolic link at **name** from **source**, belonging to **owner**
    in **group**.

mv('source', 'destination')
:   Move file at path **source** to path **destination** is it doesn't
    already exists.

rmtree('path'):
:   Recursively remove files under **path**.

chmod('path', 'modestr')
:   Change mode of file located at **path** to a **modestr** looking like
    **-rwxr-xr-x**.

resource('path')
:   Return path to resource file which is available under **resources/**.

# PACKAGE MANAGEMENT FUNCTIONS

install('package', 'package', ...)
:   Install packages whose names are passed as parameters.  Packages coming
    from repositories you don't have specified a key for beforehand will
    loudly fail to install. In fact, even **apt-get update** will grumble.
    You can specify a version to install by writing **name=version**.

purge('package', 'package', ..., [maintainer='name'])
:   Purge packages which aren't maintained by the optionally-specified
    maintainer.  For instance, to purge the **foo** and **bar** packages
    only if they're not maintained by John Doe:

    ```
    purge('foo', 'bar', maintainer='John Doe <john.doe@muppet.org>')
    ```

addmuppetrepo()
:   Add the **/var/lib/muppet/repository** (or wherever the muppet directory
    is) DEB package repository to **/etc/apt/sources.list.d**.

getselections()
:   Return a set of installed packages.

aptkey('path')
:   Run **apt-key add** against the key file at path.

# USER MANAGEMENT FUNCTIONS

adduser('user', 'password', 'shell')
:   Add user with an encrypted password which can be generated
    with **muppet encrypt**.

addgroup('group', gid=None)
:   Add group, optionally with a **gid** being an integer.

usermod('user', uid=None, group='', groups=[])
:   Modify user account identified with **user** by changing its **uid**
    integer, primary **group** and adding secondary **groups**.

users()
:   Return a list of (user, group) tuples as specified with the **--users**
    option.

# FLOW CONTROL FUNCTIONS

include('module')
:   Execute a Python module in **manifests/**. The parameter shouldn't
    include the **.py** extension.

resolution()
:   Try getting screen resolution from xrandr, then fbset, then assume
    1024×768. Return a (width, height) tuple of integers.

islaptop()
:   Return the number of power supplies. It is believed that laptops have at
    least one and fixed computer none. So if **islaptop()** evaluates to
    **True**, it's because the host has at least one power supply and is
    therefore a laptop. If **islaptop()** evaluates to **False**, it's
    because it has no power supply and is therefore a fixed computer.

hostname()
:   Return the partially qualified domain name, e.g. just 'foo', not
    'foo.muppet.org'.

release()
:   Return the release, e.g. '13.10' for Ubuntu Saucy Salamander.

# MISCELLANEOUS FUNCTIONS

run('command line')
:   Run a command line, which may include shell tricks. Log stdout and stderr.

firewall(action=None, fromhost=None, toport=None, proto=None)
:   Enable firewall and add rule with ufw. Actions are for instance **allow**.

addprinter('name', 'uri', 'ppd')
:   Add printer called **name** located at **uri**. The model can be specified
    either as a **ppd** parameter as reported by **lpinfo** or from with a
    PPD file located at **ppd**.
