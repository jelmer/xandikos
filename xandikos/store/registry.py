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

"""Backend registry for pluggable store implementations.

Each backend class must provide:
  - open_from_path(path, **kwargs) -> Store  (classmethod)
  - create(path) -> Store  (classmethod)
"""

from __future__ import annotations

import importlib
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from . import Store

_BACKENDS: dict[str, type[Store]] = {}

DEFAULT_BACKEND = "git"

_builtins_registered = False


def register_backend(name: str, cls: type[Store]) -> None:
    """Register a backend class under a short name."""
    _BACKENDS[name] = cls


def _register_builtins() -> None:
    """Lazily register built-in backends on first use."""
    global _builtins_registered
    if _builtins_registered:
        return
    _builtins_registered = True
    from .git import GitStore
    from .vdir import VdirStore
    from .memory import MemoryStore

    register_backend("git", GitStore)
    register_backend("vdir", VdirStore)
    register_backend("memory", MemoryStore)

    try:
        from .sql import SQLStore

        register_backend("sql", SQLStore)
    except ImportError:
        pass  # sqlalchemy not installed


def get_backend(name: str | None = None) -> type[Store]:
    """Resolve a backend name to its class.

    Args:
      name: Short name ('git', 'vdir', 'memory', 'sql'), a fully-qualified
            Python class path ('mypackage.MyStore'), or None for default.
    Returns: The backend class.
    Raises: ValueError if the backend cannot be resolved.
    """
    if name is None:
        name = DEFAULT_BACKEND
    _register_builtins()
    if name in _BACKENDS:
        return _BACKENDS[name]
    # Try dotted import path: 'package.module.ClassName'
    if "." in name:
        module_path, _, class_name = name.rpartition(".")
        try:
            module = importlib.import_module(module_path)
            return getattr(module, class_name)
        except (ImportError, AttributeError) as exc:
            raise ValueError(f"Cannot import backend {name!r}: {exc}") from exc
    raise ValueError(
        f"Unknown backend {name!r}. Available: {', '.join(sorted(_BACKENDS.keys()))}"
    )
