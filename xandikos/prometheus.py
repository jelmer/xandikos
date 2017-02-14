#!/usr/bin/env python3
# Xandikos
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

from prometheus_client import make_wsgi_app

DEFAULT_PROMETHEUS_DIR = '/run/xandikos/prometheus'


class PrometheusRedirector(object):

    def __init__(self, inner_app, prometheus_registry):
        self._inner_app = inner_app
        self._prometheus_app = make_wsgi_app(prometheus_registry)

    def __call__(self, environ, start_response):
        if environ['PATH_INFO'] == '/metrics':
            return self._prometheus_app(environ, start_response)
        return self._inner_app(environ, start_response)
