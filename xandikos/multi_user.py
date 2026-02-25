# Xandikos
# Copyright (C) 2016-2017 Jelmer Vernooĳ <jelmer@jelmer.uk>, et al.
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

"""Multi-user support for Xandikos.

This module provides the MultiUserFilesystemBackend class and related
functionality for running Xandikos in a multi-user mode where
principals are automatically created for authenticated users.
"""

import asyncio
import logging
import os
import signal

from .web import (
    SingleUserFilesystemBackend,
    XandikosApp,
    WELLKNOWN_DAV_PATHS,
    RedirectDavHandler,
    get_systemd_listen_sockets,
    systemd_imported,
)
from .webdav import ForbiddenError

__all__ = [
    "MultiUserFilesystemBackend",
    "MultiUserXandikosApp",
    "InvalidUsernameError",
    "validate_username",
    "add_parser",
    "main",
]


class InvalidUsernameError(ValueError):
    """Raised when a username contains invalid characters."""

    pass


def validate_username(username: str) -> None:
    """Validate that a username is safe for use in paths.

    Args:
        username: The username to validate

    Raises:
        InvalidUsernameError: If the username contains unsafe characters
    """
    if not username:
        raise InvalidUsernameError("Username cannot be empty")

    # Check for path traversal characters
    if "/" in username or "\\" in username:
        raise InvalidUsernameError("Username cannot contain path separators")

    if ".." in username:
        raise InvalidUsernameError("Username cannot contain '..'")

    # Check for null bytes
    if "\x00" in username:
        raise InvalidUsernameError("Username cannot contain null bytes")

    # Check for extremely long usernames (filesystem limits)
    if len(username) > 255:
        raise InvalidUsernameError("Username too long (max 255 characters)")

    # Check for usernames that are just dots
    if username in (".", ".."):
        raise InvalidUsernameError("Username cannot be '.' or '..'")


class MultiUserFilesystemBackend(SingleUserFilesystemBackend):
    """Backend that automatically creates principals for authenticated users."""

    def __init__(
        self,
        path,
        principal_path_prefix="/",
        principal_path_suffix="/",
        **kwargs,
    ):
        super().__init__(path, autocreate=True, **kwargs)
        self.principal_path_prefix = principal_path_prefix
        self.principal_path_suffix = principal_path_suffix

    def set_principal(
        self, user, principal_path_prefix=None, principal_path_suffix=None
    ):
        """Set the principal for a user, creating it if necessary.

        Args:
            user: Username (will be validated for safety)
            principal_path_prefix: Override prefix for this call
            principal_path_suffix: Override suffix for this call

        Raises:
            InvalidUsernameError: If the username is invalid or unsafe
        """
        # Validate username to prevent path traversal attacks
        validate_username(user)

        if principal_path_prefix is None:
            principal_path_prefix = self.principal_path_prefix
        if principal_path_suffix is None:
            principal_path_suffix = self.principal_path_suffix

        principal = principal_path_prefix + user + principal_path_suffix

        if not self.get_resource(principal):
            self.create_principal(principal, create_defaults=True)
        self._mark_as_principal(principal)


class MultiUserXandikosApp(XandikosApp):
    """A Xandikos app with path-based authorization for multi-user deployments.

    This app enforces that authenticated users can only access resources
    under their own principal path. For example, if the principal path
    pattern is "/<username>/", user "alice" can only access paths starting
    with "/alice/".

    The root path ("/") and well-known paths are accessible to all
    authenticated users for discovery purposes.
    """

    def __init__(
        self,
        backend: MultiUserFilesystemBackend,
        current_user_principal: str,
        strict: bool = True,
        require_auth: bool = True,
    ) -> None:
        """Initialize the multi-user app.

        Args:
            backend: The multi-user backend
            current_user_principal: Template for current user principal path
            strict: Whether to be strict about DAV compliance
            require_auth: If True, deny access to unauthenticated requests
                         (except for root and well-known paths for discovery)
        """
        super().__init__(backend, current_user_principal, strict=strict)
        self._backend = backend
        self._require_auth = require_auth

    def _get_user_principal_path(self, environ: dict) -> str | None:
        """Get the principal path for the current user.

        Returns:
            The principal path (e.g., "/alice/") or None if no user is authenticated.
        """
        remote_user = environ.get("REMOTE_USER")
        if not remote_user:
            return None

        return (
            self._backend.principal_path_prefix
            + remote_user
            + self._backend.principal_path_suffix
        )

    def _normalize_path(self, path: str) -> str:
        """Normalize a path for comparison.

        Ensures path starts with / and handles trailing slashes consistently.
        """
        if not path.startswith("/"):
            path = "/" + path
        # Remove trailing slash for comparison, but keep root as "/"
        if path != "/" and path.endswith("/"):
            path = path.rstrip("/")
        return path

    def check_access(self, environ: dict, path: str, method: str) -> None:
        """Check if the current user has access to the requested path.

        Users can only access resources under their own principal path.
        The root path and well-known discovery paths are accessible to all
        authenticated users (or unauthenticated if require_auth is False).

        Args:
            environ: The request environment
            path: The resource path being accessed
            method: The HTTP method

        Raises:
            ForbiddenError: If the user is not allowed to access the path
        """
        # Get the authenticated user
        remote_user = environ.get("REMOTE_USER")
        normalized_path = self._normalize_path(path)

        # Allow access to root for discovery (even without auth for client setup)
        if normalized_path == "/":
            return

        # Allow access to well-known paths for discovery
        for wellknown_path in WELLKNOWN_DAV_PATHS:
            if normalized_path == self._normalize_path(wellknown_path):
                return

        # If no user is authenticated
        if not remote_user:
            if self._require_auth:
                # Deny access to non-discovery paths without authentication
                # Use generic message to avoid path disclosure
                raise ForbiddenError("Authentication required")
            else:
                # Allow access if auth is not required (not recommended)
                return

        # Get the user's principal path
        user_principal = self._get_user_principal_path(environ)
        if user_principal is None:
            # This shouldn't happen if remote_user is set, but handle it
            raise ForbiddenError("Unable to determine user principal")

        normalized_principal = self._normalize_path(user_principal)

        # Check if the requested path is under the user's principal
        # The path must either be the principal itself or start with principal + "/"
        if normalized_path == normalized_principal:
            return
        if normalized_path.startswith(normalized_principal.rstrip("/") + "/"):
            return

        # Access denied - use generic message to avoid information disclosure
        raise ForbiddenError("Access denied")


def add_parser(parser):
    """Add multi-user command line arguments to an argument parser."""
    import argparse

    access_group = parser.add_argument_group(title="Access Options")
    access_group.add_argument(
        "--no-detect-systemd",
        action="store_false",
        dest="detect_systemd",
        help="Disable systemd detection and socket activation.",
        default=systemd_imported,
    )
    access_group.add_argument(
        "-l",
        "--listen-address",
        dest="listen_address",
        default="localhost",
        help=(
            "Bind to this address. Pass in path for unix domain socket. [%(default)s]"
        ),
    )
    access_group.add_argument(
        "-p",
        "--port",
        dest="port",
        type=int,
        default=8080,
        help="Port to listen on. [%(default)s]",
    )
    access_group.add_argument(
        "--socket-mode",
        dest="socket_mode",
        default=None,
        help=(
            "File mode (permissions) for unix domain socket, "
            "in octal (e.g. 660). Only used when listening on a unix socket."
        ),
    )
    access_group.add_argument(
        "--socket-group",
        dest="socket_group",
        default=None,
        help=(
            "Group ownership for unix domain socket. "
            "Only used when listening on a unix socket."
        ),
    )
    access_group.add_argument(
        "--metrics-port",
        dest="metrics_port",
        default=None,
        help="Port to listen on for metrics. [%(default)s]",
    )
    access_group.add_argument(
        "--route-prefix",
        default="/",
        help=(
            "Path to Xandikos. "
            "(useful when Xandikos is behind a reverse proxy) "
            "[%(default)s]"
        ),
    )
    parser.add_argument(
        "-d",
        "--directory",
        dest="directory",
        default=None,
        required=True,
        help="Directory to serve from.",
    )
    parser.add_argument(
        "--principal-path-prefix",
        default="/",
        help="Prefix for user principal paths. [%(default)s]",
    )
    parser.add_argument(
        "--principal-path-suffix",
        default="/",
        help="Suffix for user principal paths. [%(default)s]",
    )
    parser.add_argument(
        "--dump-dav-xml",
        action="store_true",
        dest="dump_dav_xml",
        help="Print DAV XML request/responses.",
    )
    parser.add_argument(
        "--avahi", action="store_true", help="Announce services with avahi."
    )
    parser.add_argument(
        "--no-strict",
        action="store_false",
        dest="strict",
        help=("Enable workarounds for buggy CalDAV/CardDAV client implementations."),
        default=True,
    )
    parser.add_argument("--debug", action="store_true", help="Print debug messages")
    parser.add_argument(
        "--hide-principals",
        action="store_true",
        dest="hide_principals",
        help="Hide list of principals on the root HTML page.",
        default=False,
    )
    # Hidden arguments. These may change without notice in between releases,
    # and are generally just meant for developers.
    parser.add_argument("--paranoid", action="store_true", help=argparse.SUPPRESS)
    parser.add_argument("--index-threshold", type=int, help=argparse.SUPPRESS)


async def main(options, parser):
    """Main entry point for multi-user mode."""
    from xandikos import __version__ as xandikos_version

    if options.dump_dav_xml:
        os.environ["XANDIKOS_DUMP_DAV_XML"] = "1"

    if not options.route_prefix.endswith("/"):
        options.route_prefix += "/"

    if options.debug:
        loglevel = logging.DEBUG
    else:
        loglevel = logging.INFO

    logging.basicConfig(level=loglevel, format="%(message)s")

    backend = MultiUserFilesystemBackend(
        os.path.abspath(options.directory),
        principal_path_prefix=options.principal_path_prefix,
        principal_path_suffix=options.principal_path_suffix,
        paranoid=options.paranoid,
        index_threshold=options.index_threshold,
        show_principals_on_root=not options.hide_principals,
    )

    if not os.path.isdir(options.directory):
        os.makedirs(options.directory)
        logging.info("Created data directory: %s", options.directory)

    logging.info("Xandikos %s (multi-user mode)", ".".join(map(str, xandikos_version)))

    main_app = MultiUserXandikosApp(
        backend,
        current_user_principal=(
            options.principal_path_prefix
            + "%(REMOTE_USER)s"
            + options.principal_path_suffix
        ),
        strict=options.strict,
    )

    async def xandikos_handler(request):
        return await main_app.aiohttp_handler(request, options.route_prefix)

    if options.detect_systemd and not systemd_imported:
        parser.error("systemd detection requested, but unable to find systemd_python")

    try:
        import systemd.daemon
    except ImportError:
        systemd_booted = False
    else:
        systemd_booted = systemd.daemon.booted()

    if options.detect_systemd and systemd_booted:
        listen_socks = get_systemd_listen_sockets()
        socket_path = None
        listen_address = None
        listen_port = None
        logging.info("Receiving file descriptors from systemd socket activation")
    elif "/" in options.listen_address:
        socket_path = options.listen_address
        listen_address = None
        listen_port = None
        listen_socks = []
        logging.info("Listening on unix domain socket %s", socket_path)
    else:
        listen_address = options.listen_address
        listen_port = options.port
        socket_path = None
        listen_socks = []
        logging.info("Listening on %s:%s", listen_address, options.port)

    from aiohttp import web

    if options.metrics_port == options.port:
        parser.error("Metrics port cannot be the same as the main port")

    app = web.Application()
    if options.metrics_port is not None:
        metrics_app = web.Application()
        try:
            from aiohttp_openmetrics import metrics, metrics_middleware
        except ModuleNotFoundError:
            logging.warning(
                "aiohttp-openmetrics not found; /metrics will not be available."
            )
        else:
            app.middlewares.insert(0, metrics_middleware)
            metrics_app.router.add_get("/metrics", metrics, name="metrics")

        metrics_app.router.add_get("/health", lambda r: web.Response(text="ok"))
    else:
        metrics_app = None

    for path in WELLKNOWN_DAV_PATHS:
        app.router.add_route(
            "*", path, RedirectDavHandler(options.route_prefix).__call__
        )

    if options.route_prefix.strip("/"):
        xandikos_app = web.Application()
        xandikos_app.router.add_route("*", "/{path_info:.*}", xandikos_handler)

        async def redirect_to_subprefix(request):
            return web.HTTPFound(options.route_prefix)

        app.router.add_route("*", "/", redirect_to_subprefix)
        app.add_subapp(options.route_prefix, xandikos_app)
    else:
        app.router.add_route("*", "/{path_info:.*}", xandikos_handler)

    if options.avahi:
        try:
            import avahi  # noqa: F401
            import dbus  # noqa: F401
        except ImportError:
            logging.error(
                "Please install python-avahi and python-dbus for avahi support."
            )
        else:
            from .web import avahi_register

            avahi_register(options.port, options.route_prefix)

    runner = web.AppRunner(app)
    await runner.setup()
    sites = []
    if metrics_app:
        metrics_runner = web.AppRunner(metrics_app)
        await metrics_runner.setup()
        sites.append(web.TCPSite(metrics_runner, listen_address, options.metrics_port))

    if listen_socks:
        sites.extend([web.SockSite(runner, sock) for sock in listen_socks])
    elif socket_path:
        sites.append(web.UnixSite(runner, socket_path))
    else:
        sites.append(web.TCPSite(runner, listen_address, listen_port))

    loop = asyncio.get_running_loop()
    shutdown_event = asyncio.Event()

    def signal_handler(signum, frame):
        logging.info("Received signal %s, shutting down gracefully...", signum)
        loop.call_soon_threadsafe(shutdown_event.set)

    signal.signal(signal.SIGTERM, signal_handler)
    signal.signal(signal.SIGINT, signal_handler)

    for site in sites:
        await site.start()

    if socket_path and options.socket_group is not None:
        import grp

        try:
            gid = grp.getgrnam(options.socket_group).gr_gid
            os.chown(socket_path, -1, gid)
            logging.info("Set socket group to %s", options.socket_group)
        except KeyError:
            parser.error(f"Unknown group: {options.socket_group}")
        except OSError as e:
            logging.error("Failed to set socket group: %s", e)

    if socket_path and options.socket_mode is not None:
        try:
            mode = int(options.socket_mode, 8)
            os.chmod(socket_path, mode)
            logging.info("Set socket permissions to %s", options.socket_mode)
        except ValueError:
            parser.error(f"Invalid socket mode: {options.socket_mode}")
        except OSError as e:
            logging.error("Failed to set socket permissions: %s", e)

    try:
        await shutdown_event.wait()
    except KeyboardInterrupt:
        logging.info("Received KeyboardInterrupt, shutting down gracefully...")

    logging.info("Stopping web servers...")
    for site in sites:
        await site.stop()

    await runner.cleanup()
    if metrics_app:
        await metrics_runner.cleanup()

    logging.info("Shutdown complete.")
