Getting Started
===============

Xandikos can either be run in a container (e.g. in docker or Kubernetes) or
outside of a container.

It is recommended that you run it behind a reverse proxy, since Xandikos by
itself does provide authentication support.

Running from docker
-------------------

There is a docker image that gets regularly updated at
``ghcr.io/jelmer/xandikos``.

If you use docker-compose, see the example configuration in
``examples/docker-compose.yml``.

Running from kubernetes
-----------------------

Here is an example configuration for running Xandikos in kubernetes:

.. literalinclude:: ../../examples/xandikos.k8s.yaml
   :language: yaml

If you're using the prometheus operator, you may want also want to use this service monitor:

.. literalinclude:: ../../examples/xandikos-servicemonitor.k8s.yaml
   :language: yaml
