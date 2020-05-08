# Xandikos
# Copyright (C) 2019 Jelmer Vernooĳ <jelmer@jelmer.uk>, et al.
#
# This program is free software; you can redistribute it and/or
# modify it under the terms of the GNU General Public License
# as published by the Free Software Foundation; version 3
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

"""Support for tracking metrics.
"""

import asyncio
import time


from aiohttp import web


from prometheus_client import (
    Counter,
    Gauge,
    Histogram,
    generate_latest,
    CONTENT_TYPE_LATEST,
)


request_counter = Counter(
    'requests_total', 'Total Request Count', ['method', 'route', 'status'])

request_latency_hist = Histogram(
    'request_latency_seconds', 'Request latency', ['route'])

requests_in_progress_gauge = Gauge(
    'requests_in_progress', 'Requests currently in progress',
    ['method', 'route'])


@asyncio.coroutine
def metrics_middleware(app, handler):
    @asyncio.coroutine
    def wrapper(request):
        start_time = time.time()
        route = request.match_info.route.name
        requests_in_progress_gauge.labels(request.method, route).inc()
        response = yield from handler(request)
        resp_time = time.time() - start_time
        request_latency_hist.labels(route).observe(resp_time)
        requests_in_progress_gauge.labels(request.method, route).dec()
        request_counter.labels(
            request.method, route, response.status).inc()
        return response
    return wrapper


def setup_metrics(app: web.Application) -> None:
    app.middlewares.insert(0, metrics_middleware)
    app.router.add_get("/metrics", metrics_handler, name='metrics')


async def metrics_handler(request: web.Request) -> web.Response:
    response = web.Response(body=generate_latest())
    response.content_type = CONTENT_TYPE_LATEST
    return response
