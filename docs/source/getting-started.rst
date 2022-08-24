.. _getting-started:

Getting Started
===============

Xandikos can either be run in a container (e.g. in docker or Kubernetes) or
outside of a container.

It is recommended that you run it behind a reverse proxy, since Xandikos by
itself does not provide authentication support. See :ref:`reverse-proxy` for
details.

Running from systemd
--------------------

Xandikos supports socket activation through systemd. To use systemd, run something like:

.. code-block:: shell

   cp examples/xandikos.{socket,service} /etc/systemd/system
   systemctl daemon-reload
   systemctl enable xandikos.socket

Running from docker
-------------------

There is a docker image that gets regularly updated at
``ghcr.io/jelmer/xandikos``.

If you use docker-compose, see the example configuration in
``examples/docker-compose.yml``.

To run in docker interactively, try something like:

.. code-block:: shell

   mkdir /tmp/xandikos
   docker -it run ghcr.io/jelmer/xandikos -v /tmp/xandikos:/data

The following environment variables are supported by the docker image:

 * ``CURRENT_USER_PRINCIPAL``: path to current user principal; defaults to "/$USER"
 * ``AUTOCREATE``: whether to automatically create missing directories ("yes" or "no")
 * ``DEFAULTS``: whether to create a default directory hierarch with one
     calendar and one addressbook ("yes" or "no")
 * ``ROUTE_PREFIX``: HTTP prefix under which Xandikos should run

Running from kubernetes
-----------------------

Here is an example configuration for running Xandikos in kubernetes:

.. literalinclude:: ../../examples/xandikos.k8s.yaml
   :language: yaml

If you're using the prometheus operator, you may want also want to use this service monitor:

.. literalinclude:: ../../examples/xandikos-servicemonitor.k8s.yaml
   :language: yaml
