Contexts
========

Currently, property get_value/set_value receive three pieces of context:

- HREF for the resource
- resource object
- Element object to update

However, some properties need WebDAV server metadata:

- supported-live-property-set needs list of properties
- supported-report-set needs list of reports
- supported-method-set needs list of methods

Some operations need access to current user information:

- current-user-principal
- current-user-privilege-set
- calendar-user-address-set

PUT/DELETE/MKCOL need access to username (for author) and possibly things like user agent
(for better commit message)

.. code:: python

  class Context(object):

      def get_current_user(self):
          return (name, principal)
