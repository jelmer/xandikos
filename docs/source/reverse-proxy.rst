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
       }
   }

Example: Apache reverse proxy
-----------------------------

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

           ProxyPass http://localhost:8080/
           ProxyPassReverse http://localhost:8080/
       </Location>
   </VirtualHost>
