# Dystros
# Copyright (C) 2016 Jelmer Vernooij <jelmer@jelmer.uk>
#
# This program is free software; you can redistribute it and/or
# modify it under the terms of the GNU General Public License
# as published by the Free Software Foundation; version 2
# of the License or (at your option) any later version of
# the License.
#
# This program is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
# GNU General Public License for more details.
#
# You should have received a copy of the GNU General Public License
# along with this program; if not, write to the Free Software
# Foundation, Inc., 51 Franklin Street, Fifth Floor, Boston,
# MA  02110-1301, USA.

"""Simple CalDAV server."""

WELLKNOWN_DAV_PATHS = set(["/.well-known/caldav", "/.well-known/carddav"])

class Endpoint(object):
    """Endpoint."""

    def _allowed_methods(self):
        return [n[3:] for n in dir(self) if n.startswith('do_')]

    def __call__(self, environ, start_response):
        method = environ['REQUEST_METHOD']
        try:
            do = getattr(self, 'do_' + method.decode('utf-8'))
        except AttributeError:
            start_response('405 Method Not Allowed', [
                ('Allow', ', '.join(self._allowed_methods()))])
            return []
        else:
            return do(environ, start_response)


class DavResource(Endpoint):
    """A webdav resource."""

    # TODO(jelmer): implement do_PROPFIND


class WellknownEndpoint(DavResource):
    """End point for well known URLs."""

    def __init__(self, server_root):
        self.server_root = server_root

    def do_GET(self, environ, start_response):
        start_response('200 OK', [])
        return [self.server_root.encode('utf-8')]


class DebugEndpoint(Endpoint):

    def do_GET(self, environ, start_response):
        print('GET: ' + environ['PATH_INFO'].decode('utf-8'))
        start_response('200 OK', [])
        return []

    def do_PROPFIND(self, environ, start_response):
        print('PROPFIND: ' + environ['PATH_INFO'].decode('utf-8'))
        try:
            request_body_size = int(environ['CONTENT_LENGTH'])
        except KeyError:
            print(environ['wsgi.input'].read())
        else:
            print(environ['wsgi.input'].read(request_body_size))
        start_response('200 OK', [])
        return []


class DystrosApp(object):

    server_root = "/"

    def __call__(self, environ, start_response):
        p = environ['PATH_INFO']
        if p in WELLKNOWN_DAV_PATHS:
            ep = WellknownEndpoint(self.server_root)
        else:
            ep = DebugEndpoint()
        if ep is None:
            start_response('404 Not Found', [])
            return [b'Path ' + p.encode('utf-8') + b' not found.']
        return ep(environ, start_response)


if __name__ == '__main__':
    import optparse
    import sys
    parser = optparse.OptionParser()
    parser.add_option("-l", "--listen_address", dest="listen_address",
                      default="localhost",
                      help="Binding IP address.")
    parser.add_option("-p", "--port", dest="port", type=int,
                      default=8000,
                      help="Port to listen on.")
    options, args = parser.parse_args(sys.argv)

    from wsgiref.simple_server import make_server
    app = DystrosApp()
    server = make_server(options.listen_address, options.port, app)
    server.serve_forever()
