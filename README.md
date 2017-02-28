[![Build Status](https://travis-ci.org/jelmer/xandikos.png?branch=master)](https://travis-ci.org/jelmer/xandikos)

Xandikos is a CardDAV/CalDAV server that backs onto a Git repository.

Xandikos (Ξανδικός or Ξανθικός) takes its name from the name of the March month
in the ancient Macedonian calendar, used in Macedon in the first millennium BC.

Implemented standards
=====================

The following standards are implemented:

 - [RFC4918](http://www.rfc-base.org/rfc-4918.html)/[RFC2518](http://www.rfc-base.org/rfc-2518.html) (Core WebDAV) - *implemented, except for COPY/MOVE/LOCK operations*
 - [RFC4791](http://www.rfc-base.org/rfc-4791.html) (CalDAV) - *fully implemented*
 - [RFC6352](http://www.rfc-base.org/rfc-6352.html) (CardDAV) - *fully implemented*
 - [RFC5397](http://www.rfc-base.org/rfc-5397.html) (Current Principal) - *fully implemented*
 - [RFC3253](http://www.rfc-base.org/rfc-3253.html) (Versioning Extensions) - *partially implemented, only the REPORT method and {DAV:}expand-property property*
 - [RFC3744](http://www.rfc-base.org/rfc-3744.html) (Access Control) - *partially implemented*
 - [RFC5995](http://www.rfc-base.org/rfc-5995.html) (POST to create members) - *fully implemented*
 - [RFC7809](http://www.rfc-base.org/rfc-7809.html) (CalDAV Time Zone Extensions) - *not implemented*

See [DAV compliance](notes/dav-compliance.md) for more detail on specification compliancy.

Limitations
-----------

 - No multi-user support
 - No support for CalDAV scheduling extensions

Supported clients
=================

Xandikos has been tested and works with the following clients:

 - [vdirsyncer](https://github.com/pimutils/vdirsyncer)
 - [caldavzap](https://www.inf-it.com/open-source/clients/caldavzap/)/[carddavmate](https://www.inf-it.com/open-source/clients/carddavmate/)
 - [evolution](https://wiki.gnome.org/Apps/Evolution)
 - [davdroid](https://davdroid.bitfire.at/)
 - [sogo connector for Icedove/Thunderbird](http://v2.sogo.nu/english/downloads/frontends.html)
 - [aCALdav syncer for Android](https://play.google.com/store/apps/details?id=de.we.acaldav&hl=en)
 - [pycardsyncer](https://github.com/geier/pycarddav)

Clients that are known not to work:

 - [CalDAV-Sync](https://dmfs.org/caldav/)
 - [CardDAV-Sync](https://dmfs.org/carddav/)

Running
=======

Testing
-------

To run a standalone (low-performance, no authentication) instance of Xandikos,
simply create a directory to store your data (say *$HOME/dav*) and run it:

```shell
mkdir -p $HOME/dav
./bin/xandikos -d $HOME/dav
```

A server should now be running on _localhost:8080_.

Production
----------

The easiest way to run Xandikos in production is using
[uWSGI](https://uwsgi-docs.readthedocs.io/en/latest/).

One option is to setup uWSGI with a server like
[Apache](http://uwsgi-docs.readthedocs.io/en/latest/Apache.html),
[Nginx](http://uwsgi-docs.readthedocs.io/en/latest/Nginx.html) or another web
server that can authenticate users and forward authenticated requests to
Xandikos in uWSGI. See [examples/uwsgi.ini](examples/uwsgi.ini) for an
example uWSGI configuration.

Alternatively, you can run uWSGI standalone and have it authenticate and
directly serve HTTP traffic. An example configuration for this can be found in
[examples/uwsgi-standalone.ini](examples/uwsgi-standalone.ini).

This will start a server on _localhost:8080_ with username *user1* and password
*password1*.

```shell
mkdir -p $HOME/dav
uwsgi examples/uwsgi-standalone.ini
```

Help
====

There is a *#xandikos* IRC channel on the [Freenode](https://www.freenode.net/)
IRC network, and a [xandikos](https://groups.google.com/forum/#!forum/xandikos)
mailing list.

Dependencies
============

At the moment, Xandikos supports Python 3.5 and higher as well as Pypy 3. It
also uses [dulwich](https://github.com/jelmer/dulwich),
[icalendar](https://github.com/collective/icalendar) and
[defusedxml](https://github.com/tiran/defusedxml).
