.. image:: https://travis-ci.org/jelmer/xandikos.png?branch=master
   :target: https://travis-ci.org/jelmer/xandikos
   :alt: Build Status

Xandikos is a CardDAV/CalDAV server that backs onto a Git repository.

Xandikos (Ξανδικός or Ξανθικός) takes its name from the name of the March month
in the ancient Macedonian calendar, used in Macedon in the first millennium BC.

Implemented standards
=====================

The following standards are implemented:

- `RFC4918 <http://www.rfc-base.org/rfc-4918.html>`_/`RFC2518 <http://www.rfc-base.org/rfc-2518.html>`_ (Core WebDAV) - *implemented, except for COPY/MOVE/LOCK operations*
- `RFC4791 <http://www.rfc-base.org/rfc-4791.html>`_ (CalDAV) - *fully implemented*
- `RFC6352 <http://www.rfc-base.org/rfc-6352.html>`_ (CardDAV) - *fully implemented*
- `RFC5397 <http://www.rfc-base.org/rfc-5397.html>`_ (Current Principal) - *fully implemented*
- `RFC3253 <http://www.rfc-base.org/rfc-3253.html>`_ (Versioning Extensions) - *partially implemented, only the REPORT method and {DAV:}expand-property property*
- `RFC3744 <http://www.rfc-base.org/rfc-3744.html>`_ (Access Control) - *partially implemented*
- `RFC5995 <http://www.rfc-base.org/rfc-5995.html>`_ (POST to create members) - *fully implemented*
- `RFC5689 <http://www.rfc-base.org/rfc-5689.html>`_ (Extended MKCOL) - *fully implemented*

The following standards are not implemented:

- `RFC6638 <http://www.rfc-base.org/rfc-6638.html>`_ (CalDAV Scheduling Extensions) - *not implemented*
- `RFC7809 <http://www.rfc-base.org/rfc-7809.html>`_ (CalDAV Time Zone Extensions) - *not implemented*
- `RFC7529 <http://www.rfc-base.org/rfc-7529.html>`_ (WebDAV Quota) - *not implemented*
- `RFC4709 <http://www.rfc-base.org/rfc-4709.html>`_ (WebDAV Mount) - *not implemented*
- `RFC5546 <http://www.rfc-base.org/rfc-5546.html>`_ (iCal iTIP) - *not implemented*
- `RFC4324 <http://www.rfc-base.org/rfc-4324.html>`_ (iCAL CAP) - *not implemented*
- `RFC7953 <http://www.rfc-base.org/rfc-7953.html>`_ (iCal AVAILABILITY) - *not implemented*

See `DAV compliance <notes/dav-compliance.md>`_ for more detail on specification compliancy.

Limitations
-----------

- No multi-user support
- No support for CalDAV scheduling extensions

Supported clients
=================

Xandikos has been tested and works with the following CalDAV/CardDAV clients:

- `Vdirsyncer <https://github.com/pimutils/vdirsyncer>`_
- `caldavzap <https://www.inf-it.com/open-source/clients/caldavzap/>`_/`carddavmate <https://www.inf-it.com/open-source/clients/carddavmate/>`_
- `evolution <https://wiki.gnome.org/Apps/Evolution>`_
- `DAVdroid <https://davdroid.bitfire.at/>`_
- `sogo connector for Icedove/Thunderbird <http://v2.sogo.nu/english/downloads/frontends.html>`_
- `aCALdav syncer for Android <https://play.google.com/store/apps/details?id=de.we.acaldav&hl=en>`_
- `pycardsyncer <https://github.com/geier/pycarddav>`_
- `akonadi <https://community.kde.org/KDE_PIM/Akonadi>`_

CalDAV/CardDAV clients that are known not to work:

- `CalDAV-Sync <https://dmfs.org/caldav/>`_
- `CardDAV-Sync <https://dmfs.org/carddav/>`_

Dependencies
============

At the moment, Xandikos supports Python 3.3 and higher as well as Pypy 3. It
also uses `Dulwich <https://github.com/jelmer/dulwich>`_,
`Jinja2 <http://jinja.pocoo.org/>`_,
`icalendar <https://github.com/collective/icalendar>`_, and
`defusedxml <https://github.com/tiran/defusedxml>`_.

E.g. to install those dependencies on Debian:

.. code:: shell

  sudo apt install python3-dulwich python3-defusedxml python3-icalendar python3-jinja2

Or to install them using pip:

.. code:: shell

  python setup.py develop

Running
=======

Testing
-------

To run a standalone (low-performance, no authentication) instance of Xandikos,
with a pre-created calendar and addressbook (storing data in *$HOME/dav*):

.. code:: shell

  ./bin/xandikos --defaults -d $HOME/dav

A server should now be listening on `localhost:8080 <http://localhost:8080/>`_.

Note that Xandikos does not create any collections by default. You can either
create collections from your CalDAV/CardDAV client, or by creating git
repositories under the *contacts* or *calendars* directories it has created.

Production
----------

The easiest way to run Xandikos in production is using
`uWSGI <https://uwsgi-docs.readthedocs.io/en/latest/>`_.

One option is to setup uWSGI with a server like
`Apache <http://uwsgi-docs.readthedocs.io/en/latest/Apache.html>`_,
`Nginx <http://uwsgi-docs.readthedocs.io/en/latest/Nginx.html>`_ or another web
server that can authenticate users and forward authorized requests to
Xandikos in uWSGI. See `examples/uwsgi.ini <examples/uwsgi.ini>`_ for an
example uWSGI configuration.

Alternatively, you can run uWSGI standalone and have it authenticate and
directly serve HTTP traffic. An example configuration for this can be found in
`examples/uwsgi-standalone.ini <examples/uwsgi-standalone.ini>`_.

This will start a server on `localhost:8080 <http://localhost:8080/>`_ with username *user1* and password
*password1*.

.. code:: shell

  mkdir -p $HOME/dav
  uwsgi examples/uwsgi-standalone.ini

Help
====

There is a *#xandikos* IRC channel on the `Freenode <https://www.freenode.net/>`_
IRC network, and a `Xandikos <https://groups.google.com/forum/#!forum/xandikos>`_
mailing list.
