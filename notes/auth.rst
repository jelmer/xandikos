Authentication
==============

Ideally, Xandikos would stay out of the business of authenticating users.
The trouble with this is that there are many flavours that need to
be supported and configured.

However, it is still necessary for Xandikos to handle authorization.

An external system authenticates the user, and then sets the REMOTE_USER
environment variable.

Per
http://wsgi.readthedocs.io/en/latest/specifications/simple_authentication.html,
Xandikos should distinguish between 401 and 403.

Never trust ``X-Remote-User`` from an unauthenticated client
------------------------------------------------------------

Xandikos also supports being told the authenticated user via an
``X-Remote-User`` HTTP header (and its WSGI translation
``HTTP_X_REMOTE_USER``). This is convenient when the fronting proxy
identifies users out of band, but by default the header is
**ignored**: the value comes straight from the HTTP request, so any
client could set it and pick their own principal.

To opt in, pass ``--trust-x-remote-user-from=<IP or CIDR>`` (repeatable)
on the command line, or set ``TRUST_X_REMOTE_USER_FROM`` when using
``xandikos.wsgi``. Xandikos then only honors ``X-Remote-User`` when the
request originates from one of the listed addresses. The upstream
reverse proxy must additionally strip or overwrite any ``X-Remote-User``
supplied by the client before forwarding the request.

The genuine ``REMOTE_USER`` WSGI environ key -- as set by
authenticating WSGI middleware or by uWSGI's ``router_basicauth``
plugin -- is always honored, regardless of this setting.
