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

"""Filesystem-based backend base class."""

import os
import shutil

from xandikos import webdav


class FilesystemBackend(webdav.Backend):
    """A backend that stores data on the local filesystem.

    This base class handles path mapping and collection copy/move operations.
    Subclasses are responsible for resolving WebDAV resources from the
    filesystem paths.
    """

    def __init__(self, path: str) -> None:
        self.path = path

    def _map_to_file_path(self, relpath: str) -> str:
        """Map a WebDAV relative path to an absolute filesystem path."""
        return os.path.join(self.path, relpath.lstrip("/"))

    async def copy_collection(
        self, source_path: str, dest_path: str, overwrite: bool = True
    ) -> bool:
        """Copy a collection recursively.

        Args:
            source_path: WebDAV path of the source collection.
            dest_path: WebDAV path of the destination.
            overwrite: Whether to overwrite an existing destination.

        Returns:
            True if the destination already existed and was overwritten.

        Raises:
            KeyError: If the source path does not exist.
            ValueError: If the source path is not a collection.
            FileExistsError: If the destination exists and overwrite is False.
        """
        source_collection = self.get_resource(source_path)
        if source_collection is None:
            raise KeyError(source_path)

        if webdav.COLLECTION_RESOURCE_TYPE not in source_collection.resource_types:
            raise ValueError(f"Source '{source_path}' is not a collection")

        source_file_path = self._map_to_file_path(source_path)
        dest_file_path = self._map_to_file_path(dest_path)

        did_overwrite = False
        if os.path.exists(dest_file_path):
            if not overwrite:
                raise FileExistsError(f"Collection '{dest_path}' already exists")
            did_overwrite = True
            if os.path.isdir(dest_file_path):
                shutil.rmtree(dest_file_path)
            else:
                os.remove(dest_file_path)

        shutil.copytree(source_file_path, dest_file_path)
        return did_overwrite

    async def move_collection(
        self, source_path: str, dest_path: str, overwrite: bool = True
    ) -> bool:
        """Move a collection recursively.

        Args:
            source_path: WebDAV path of the source collection.
            dest_path: WebDAV path of the destination.
            overwrite: Whether to overwrite an existing destination.

        Returns:
            True if the destination already existed and was overwritten.

        Raises:
            KeyError: If the source path does not exist.
            ValueError: If the source path is not a collection.
            FileExistsError: If the destination exists and overwrite is False.
        """
        source_collection = self.get_resource(source_path)
        if source_collection is None:
            raise KeyError(source_path)

        if webdav.COLLECTION_RESOURCE_TYPE not in source_collection.resource_types:
            raise ValueError(f"Source '{source_path}' is not a collection")

        source_file_path = self._map_to_file_path(source_path)
        dest_file_path = self._map_to_file_path(dest_path)

        did_overwrite = False
        if os.path.exists(dest_file_path):
            if not overwrite:
                raise FileExistsError(f"Collection '{dest_path}' already exists")
            did_overwrite = True
            if os.path.isdir(dest_file_path):
                shutil.rmtree(dest_file_path)
            else:
                os.remove(dest_file_path)

        shutil.move(source_file_path, dest_file_path)
        return did_overwrite
