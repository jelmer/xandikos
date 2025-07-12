Installation
============

This guide covers various methods for installing Xandikos on different platforms.

System Requirements
-------------------

- Python 3 (check ``pyproject.toml`` for specific version requirements)
- Optional: A reverse proxy (nginx, Apache) for production deployments

Installation Methods
--------------------

Using pip
~~~~~~~~~

The simplest way to install Xandikos is using pip:

.. code-block:: bash

   pip install xandikos

For development or to get the latest features:

.. code-block:: bash

   git clone https://github.com/jelmer/xandikos.git
   cd xandikos
   pip install -e .

Using Package Managers
~~~~~~~~~~~~~~~~~~~~~~

**Debian/Ubuntu**

Xandikos is available in Debian and Ubuntu repositories:

.. code-block:: bash

   sudo apt update
   sudo apt install xandikos

To install all optional dependencies:

.. code-block:: bash

   sudo apt install python3-dulwich python3-defusedxml python3-icalendar python3-jinja2

**NetBSD**

Xandikos is available in pkgsrc:

.. code-block:: bash

   pkgin install py-xandikos

**Arch Linux (AUR)**

Xandikos is available in the Arch User Repository:

.. code-block:: bash

   yay -S xandikos
   # or using another AUR helper

**macOS (using Homebrew)**

First install Python and pip if not already available:

.. code-block:: bash

   brew install python
   pip install xandikos

**FreeBSD**

Xandikos is available in the FreeBSD ports tree:

.. code-block:: bash

   pkg install py311-xandikos

Using Docker
~~~~~~~~~~~~

Pull and run the official Docker image:

.. code-block:: bash

   docker pull ghcr.io/jelmer/xandikos:latest
   docker run -p 8080:8080 -v /path/to/data:/data ghcr.io/jelmer/xandikos

For production use with docker-compose:

.. code-block:: yaml

   version: '3'
   services:
     xandikos:
       image: ghcr.io/jelmer/xandikos:latest
       ports:
         - "8080:8080"
       volumes:
         - ./data:/data
       environment:
         - AUTOCREATE=defaults
         - CURRENT_USER_PRINCIPAL=/alice
       restart: unless-stopped

Using Kubernetes
~~~~~~~~~~~~~~~~

Deploy using the example Kubernetes configuration:

.. code-block:: bash

   kubectl apply -f examples/xandikos.k8s.yaml

From Source
~~~~~~~~~~~

To install from source with all dependencies:

.. code-block:: bash

   git clone https://github.com/jelmer/xandikos.git
   cd xandikos
   python setup.py install

Or for development:

.. code-block:: bash

   git clone https://github.com/jelmer/xandikos.git
   cd xandikos
   pip install -r requirements.txt
   python setup.py develop

Verifying Installation
----------------------

After installation, verify that Xandikos is properly installed:

.. code-block:: bash

   xandikos --version

To test the installation with a temporary instance:

.. code-block:: bash

   xandikos --defaults -d /tmp/test-dav

Then navigate to http://localhost:8080 in your browser.

Post-Installation Steps
-----------------------

1. **Set up a reverse proxy** for authentication and SSL (see :ref:`reverse-proxy`)
2. **Configure storage location** for your calendar and contact data
3. **Set up automatic backups** of your data directory
4. **Configure systemd** or another init system for automatic startup

Troubleshooting Installation
----------------------------

**Missing Dependencies**

If you encounter import errors, install the required Python packages.
See the `pyproject.toml` file for a list of required and optional
dependencies.

**Permission Issues**

Ensure the user running Xandikos has read/write access to the data directory:

.. code-block:: bash

   mkdir -p /var/lib/xandikos
   chown -R xandikos:xandikos /var/lib/xandikos

**Port Already in Use**

If port 8080 is already in use, specify a different port:

.. code-block:: bash

   xandikos --port 8090 -d /path/to/data

Next Steps
----------

- Configure your CalDAV/CardDAV clients (see :doc:`clients`)
- Set up a reverse proxy for production use (see :ref:`reverse-proxy`)
