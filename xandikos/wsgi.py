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

import logging
import os

from .web import XandikosApp, XandikosBackend

create_defaults = False

autocreate_str = os.getenv("AUTOCREATE")
if autocreate_str == "defaults":
    logging.warning("Creating default collections.")
    create_defaults = True
    autocreate = True
elif autocreate_str in ("empty", "yes"):
    autocreate = True
elif autocreate_str in (None, "no"):
    autocreate = False
else:
    logging.warning("Unknown value for AUTOCREATE: %r", autocreate_str)
    autocreate = False

backend = XandikosBackend(path=os.environ["XANDIKOSPATH"])
if not os.path.isdir(backend.path):
    if autocreate:
        os.makedirs(os.environ["XANDIKOSPATH"])
    else:
        logging.warning("%r does not exist.", backend.path)

current_user_principal = os.environ.get("CURRENT_USER_PRINCIPAL", "/user/")
if not backend.get_resource(current_user_principal):
    if autocreate:
        backend.create_principal(
            current_user_principal, create_defaults=create_defaults
        )
    else:
        logging.warning(
            "default user principal '%s' does not exist. "
            "Create directory %s or set AUTOCREATE variable?",
            current_user_principal,
            backend._map_to_file_path(current_user_principal),
        )

backend._mark_as_principal(current_user_principal)
app = XandikosApp(backend, current_user_principal)
