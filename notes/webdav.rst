WebDAV implementation
=====================

.. code:: python

  class DAVPropertyProvider(object):

      NAME property

      matchresource()

      # One or multiple properties?

      def proplist(self, resource, all=False):

      def getprop(self, resource, property):

      def propupdate(self, resource, updates):


  class DAVBackend(object):

      def get_resource(self, path):

      def create_collection(self, path):


  class DAVReporter(object):

  class DAVResource(object):

    def get_resource_types(self):

    def get_body(self):
      """Returns the body of the resource.

      :return: bytes representing contents
      """

    def set_body(self, body):
      """Set the body of the resource.

      :param body: body (as bytes)
      """

    def proplist(self):
      """Return list of properties.

      :return: List of property names
      """

    def propupdate(self, updates):
      """Update properties.

      :param updates: Dictionary mapping names to new values
      """

    def lock(self):

    def unlock(self):

    def members(self):
      """List members.

      :return: List tuples of (name, DAVResource)
      """

    # TODO(jelmer): COPY
    # TODO(jelmer): MOVE
    # TODO(jelmer): MKCOL
    # TODO(jelmer): LOCK/UNLOCK
    # TODO(jelmer): REPORT
