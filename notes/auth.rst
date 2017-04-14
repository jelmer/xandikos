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
