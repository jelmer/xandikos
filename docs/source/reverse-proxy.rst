.. _reverse-proxy:

Running behind a reverse proxy
==============================

By default, Xandikos does not provide any authentication support. Instead, it
is recommended that it is run behind a reverse HTTP proxy that does.

The author has used both nginx and Apache in front of Xandikos, but any
reverse HTTP proxy should do.

If you expose Xandikos at the root of a domain, no further configuration is
necessary. When exposing it on a different path prefix, make sure to set the
``--route-prefix`` argument to Xandikos appropriately.

.. _reverse-proxy-x-remote-user:

Passing the authenticated user to Xandikos
------------------------------------------

Multi-user mode needs to know *which* user each request belongs to.
There are two supported ways to tell it:

1. **Set the WSGI ``REMOTE_USER`` environ key.** This is what
   authenticating WSGI middleware and uWSGI's ``router_basicauth``
   plugin do after actually verifying credentials. Xandikos always
   honors this key.

2. **Send an ``X-Remote-User`` HTTP header** and start Xandikos with
   ``--trust-x-remote-user-from=<IP or CIDR>`` naming the reverse
   proxy. Xandikos will then only honor the header when the request
   comes from one of the listed peers.

.. warning::

   ``X-Remote-User`` is trivially spoofable: it is an ordinary HTTP
   header the client can set. Without ``--trust-x-remote-user-from``
   Xandikos ignores the header entirely. When you *do* enable it, the
   fronting proxy MUST strip or overwrite any ``X-Remote-User``
   supplied by the client before forwarding the request; otherwise an
   authenticated user could impersonate any other principal by adding
   their own ``X-Remote-User: victim`` header.

   The nginx and Apache snippets below show how to inject a trusted
   ``X-Remote-User`` and clear any incoming one.

.well-known
-----------

When serving Xandikos on a prefix, you may still want to provide
the appropriate ``.well-known`` files at the root so that clients
can find the DAV server without having to specify the subprefix.

For this to work, reverse proxy the ``.well-known/carddav`` and
``.well-known/caldav`` files to Xandikos.

Example: Kubernetes ingress
---------------------------

Here is an example configuring Xandikos to listen on ``/dav`` using the
Kubernetes nginx ingress controller. Note that this relies on the
appropriate server being set up in kubernetes (see :ref:`getting-started`) and
the ``my-htpasswd`` secret being present and having a htpasswd like file in it.

.. literalinclude:: ../../examples/xandikos-ingress.k8s.yaml
   :language: yaml

Example: nginx reverse proxy
-----------------------------

Start Xandikos with ``--trust-x-remote-user-from=127.0.0.1`` (or the
address nginx connects from) so it accepts the header this config
injects.

.. code-block:: nginx

   server {
       listen 443 ssl;
       server_name dav.example.com;

       ssl_certificate /path/to/cert.pem;
       ssl_certificate_key /path/to/key.pem;

       location / {
           auth_basic "CalDAV/CardDAV";
           auth_basic_user_file /etc/nginx/htpasswd;

           proxy_pass http://localhost:8080;
           proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
           proxy_set_header X-Forwarded-Proto $scheme;
           proxy_set_header Host $host;
           # Tell Xandikos which authenticated user this request belongs to.
           # $remote_user comes from auth_basic above, so it is trustworthy.
           proxy_set_header X-Remote-User $remote_user;
           # Refuse any X-Remote-User the client might have supplied,
           # otherwise a valid basic-auth user could impersonate anyone.
           proxy_set_header X-Forwarded-User "";
       }
   }

Example: Apache reverse proxy
-----------------------------

Start Xandikos with ``--trust-x-remote-user-from=127.0.0.1`` (or the
address Apache connects from) so it accepts the header this config
injects.

.. code-block:: apache

   <VirtualHost *:443>
       ServerName dav.example.com

       SSLEngine on
       SSLCertificateFile /path/to/cert.pem
       SSLCertificateKeyFile /path/to/key.pem

       <Location />
           AuthType Digest
           AuthName "CalDAV/CardDAV"
           AuthUserFile /etc/apache2/htdigest
           Require valid-user

           # Strip any client-supplied X-Remote-User before proxying,
           # then set it from the value Apache actually authenticated.
           RequestHeader unset X-Remote-User
           RequestHeader set X-Remote-User "%{REMOTE_USER}s"

           ProxyPass http://localhost:8080/
           ProxyPassReverse http://localhost:8080/
       </Location>
   </VirtualHost>
