Configuration Reference
=======================

This page provides a comprehensive reference for all Xandikos configuration options.

Command-Line Options
--------------------

Basic Options
~~~~~~~~~~~~~

``-d, --directory``
    Root directory to serve DAV collections from (required).

    Example: ``--directory /var/lib/xandikos``

``-p, --port``
    Port to listen on (default: 8080).

    Example: ``--port 8090``

``-l, --listen-address``
    Address to listen on (default: localhost). Can also be a Unix socket path.

    Example: ``--listen-address 0.0.0.0``
    Example: ``--listen-address /var/run/xandikos.sock``

``--route-prefix``
    Path prefix for the application. Use this when running behind a reverse proxy on a subpath.

    Example: ``--route-prefix /dav``


Collection Management
~~~~~~~~~~~~~~~~~~~~~

``--defaults``
    Create default calendar and addressbook collections if they don't exist.
    Collections created:

    - ``calendars/calendar`` - Default calendar
    - ``contacts/addressbook`` - Default addressbook

``--autocreate``
    Automatically create missing directories when accessed.
    Options:

    - ``yes`` - Create all missing directories
    - ``no`` - Never create directories (default)

    Example: ``--autocreate yes``

Authentication and Permissions
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

``--current-user-principal``
    Path to current user principal (default: /user/).

    Example: ``--current-user-principal /alice``

Debugging Options
~~~~~~~~~~~~~~~~~

``--debug``
    Enable debug logging. Shows detailed internal operations.

``--dump-dav-xml``
    Dump all WebDAV request/response XML to stdout. Useful for debugging client issues.

``--no-strict``
    Don't be strict about WebDAV compliance. Enable workarounds for broken clients.

Service Discovery
~~~~~~~~~~~~~~~~~

``--avahi``
    Announce services with Avahi/Bonjour for automatic discovery.

``--metrics-port``
    Port to listen on for metrics endpoint.

    Example: ``--metrics-port 9090``

System Integration
~~~~~~~~~~~~~~~~~~

``--no-detect-systemd``
    Disable systemd socket activation detection.

Docker Environment Variables
----------------------------

When running in Docker, these environment variables are supported:

``CURRENT_USER_PRINCIPAL``
    Path to current user principal (default: ``/$USER``).

``AUTOCREATE``
    Whether to autocreate collections. Options: ``defaults``, ``empty``.

    * ``defaults`` - Create default collections
    * ``empty`` - Create principal without collections
    * ``no`` - Do not create collections (default)

``ROUTE_PREFIX``
    HTTP path prefix for the application.

``XANDIKOS_LISTEN_ADDRESS``
    Address to bind to (default: ``localhost``, ``0.0.0.0`` in Docker).

``XANDIKOS_PORT``
    Port to listen on (default: ``8080``).

Configuration Examples
----------------------

Basic Standalone Server
~~~~~~~~~~~~~~~~~~~~~~~

.. code-block:: bash

   xandikos \
     --directory /var/lib/xandikos \
     --defaults \
     --current-user-principal /john

Behind nginx on Subpath
~~~~~~~~~~~~~~~~~~~~~~~

.. code-block:: bash

   xandikos \
     --directory /var/lib/xandikos \
     --route-prefix /dav \
     --listen-address /var/run/xandikos.sock \
     --defaults

Production with Logging
~~~~~~~~~~~~~~~~~~~~~~~

.. code-block:: bash

   xandikos \
     --directory /var/lib/xandikos \
     --listen-address localhost \
     --port 8080 \
     --debug \
     --defaults

Docker Compose Configuration
~~~~~~~~~~~~~~~~~~~~~~~~~~~~

.. code-block:: yaml

   version: '3'
   services:
     xandikos:
       image: ghcr.io/jelmer/xandikos:latest
       environment:
         - AUTOCREATE=defaults
         - CURRENT_USER_PRINCIPAL=/alice
         - ROUTE_PREFIX=/dav
       volumes:
         - ./data:/data
       ports:
         - "127.0.0.1:8080:8080"

Systemd Socket Activation
~~~~~~~~~~~~~~~~~~~~~~~~~

Create ``/etc/systemd/system/xandikos.socket``:

.. code-block:: ini

   [Unit]
   Description=Xandikos CalDAV/CardDAV server socket

   [Socket]
   ListenStream=/var/run/xandikos.sock

   [Install]
   WantedBy=sockets.target

Create ``/etc/systemd/system/xandikos.service``:

.. code-block:: ini

   [Unit]
   Description=Xandikos CalDAV/CardDAV server
   After=network.target

   [Service]
   Type=notify
   ExecStart=/usr/bin/xandikos \
     --directory /var/lib/xandikos \
     --listen-address /var/run/xandikos.sock \
     --defaults
   User=xandikos
   Group=xandikos

   [Install]
   WantedBy=multi-user.target

Directory Structure
-------------------

Xandikos organizes data in the following directory structure:

.. code-block:: text

   /var/lib/xandikos/           # Root directory (configured with --directory)
   ├── calendars/               # Calendar collections
   │   ├── calendar/            # Default calendar
   │   │   ├── .git/            # Git repository
   │   │   └── *.ics            # iCalendar files
   │   └── tasks/               # Task list
   └── contacts/                # Addressbook collections
       └── addressbook/         # Default addressbook
           ├── .git/            # Git repository
           └── *.vcf            # vCard files

File Naming
~~~~~~~~~~~

- Calendar events: ``{UID}.ics``
- Contacts: ``{UID}.vcf``
- UIDs are automatically generated if not provided

Git Storage
~~~~~~~~~~~

Each collection is stored as a Git repository, providing:

- Version history for all changes
- Ability to revert changes
- Efficient storage of modifications
- Built-in backup mechanism
