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

"""WSGI wrapper for xandikos."""

from logging import getLogger
import os

from .web import XandikosApp, XandikosBackend
from .store.registry import get_backend as _get_backend

logger = getLogger("xandikos")

create_defaults = False

autocreate_str = os.getenv("AUTOCREATE")
if autocreate_str == "defaults":
    logger.warning("Creating default collections.")
    create_defaults = True
    autocreate = True
elif autocreate_str in ("empty", "yes"):
    autocreate = True
elif autocreate_str in (None, "no"):
    autocreate = False
else:
    logger.warning("Unknown value for AUTOCREATE: %r", autocreate_str)
    autocreate = False

backend_name = os.environ.get("XANDIKOS_BACKEND")

_backend_cls = _get_backend(backend_name)
_xandikos_path = os.environ.get("XANDIKOSPATH")
if _xandikos_path is None and _backend_cls.uses_filesystem():
    raise RuntimeError(
        f"XANDIKOSPATH environment variable must be set for the {backend_name or 'git'!r} backend"
    )

backend = XandikosBackend(path=_xandikos_path, backend=backend_name)
if _xandikos_path is not None and not os.path.isdir(_xandikos_path):
    if autocreate:
        os.makedirs(_xandikos_path)
    else:
        logger.warning("%r does not exist.", _xandikos_path)

current_user_principal = os.environ.get("CURRENT_USER_PRINCIPAL", "/user/")
if not backend.get_resource(current_user_principal):
    if autocreate:
        backend.create_principal(
            current_user_principal, create_defaults=create_defaults
        )
    else:
        logger.warning(
            "default user principal '%s' does not exist. Set AUTOCREATE variable?",
            current_user_principal,
        )

backend._mark_as_principal(current_user_principal)
app = XandikosApp(backend, current_user_principal)
