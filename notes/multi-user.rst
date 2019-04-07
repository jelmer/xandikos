Multi-User Support
==================

Multi-user support could arguably also include sharing of
calendars/collections/etc. This is beyond the scope of this document, which
just focuses on allowing multiple users to use their own silo in a single
instance of Xandikos.

Siloed user support can be split up into three steps:

 * storage - mapping a user to a principal
 * authentication - letting a user log in
 * authorization - checking whether the user has access to a resource

Authentication
--------------

In the simplest form, a forwarding proxy provides the name of an authenticated
user. E.g. Apache or uWSGI sets the REMOTE_USER environment variable. If
REMOTE_USER is not present for an operation that requires authentication, a 401
error is returned.

Authorization
-------------

In the simplest form, users only have access to the resources under their own
principal.

As a second step, we could let users configure ACLs; one way of doing this would be
to allow adding authentication in the collection configuration. I.e. something like::

   [acl]
   read = jelmer, joe
   write = jelmer

Storage
-------

By default, the principal for a user is simply "/%(username)s".

Roadmap
=======

* Optional: Allow marking collections as principals [DONE]
* Expose username (or None, if not logged in) everywhere [DONE]
* Add function get_username_principal() for mapping username to principal path [DONE]
* Support automatic creation of principal on first login of user
* Add simple function check_path_access() for checking access ("is this user allowed to access this path?")
* Use access checking function everywhere
* Have current-user-principal setting depend on $REMOTE_USER and get_username_principal() [DONE]
