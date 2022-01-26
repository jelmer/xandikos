# NAME

xandikos - git-backed CalDAV/CardDAV server

# DESCRIPTION

usage: ./bin/xandikos **-d** ROOT-DIR \[OPTIONS\]

## optional arguments:

**-h**, **\--help**

:   show this help message and exit

**\--version**

:   show program\'s version number and exit

**-d** DIRECTORY, **\--directory** DIRECTORY

:   Directory to serve from.

**\--current-user-principal** CURRENT_USER_PRINCIPAL

:   Path to current user principal. \[/user/\]

**\--autocreate**

:   Automatically create necessary directories.

**\--defaults**

:   Create initial calendar and address book. Implies **\--autocreate**.

**\--dump-dav-xml**

:   Print DAV XML request/responses.

**\--avahi**

:   Announce services with avahi.

**\--no-strict**

:   Enable workarounds for buggy CalDAV/CardDAV client implementations.

## Access Options:

**-l** LISTEN_ADDRESS, **\--listen-address** LISTEN_ADDRESS

:   Bind to this address. Pass in path for unix domain socket.
    \[localhost\]

**-p** PORT, **\--port** PORT

:   Port to listen on. \[8080\]

**\--route-prefix** ROUTE_PREFIX

:   Path to Xandikos. (useful when Xandikos is behind a reverse proxy)
    \[/\]

# AUTHORS

Jelmer Vernooij \<jelmer\@debian.org>
