Running Xandikos from uWSGI
===========================

In addition to running as a standalone service, Xandikos can also be run by any
service that supports the wsgi interface. An example of such a service is uWSGI.

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


