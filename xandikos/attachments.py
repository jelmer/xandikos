# Xandikos
# Copyright (C) 2025 Jelmer Vernooĳ <jelmer@jelmer.uk>, et al.
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

"""CalDAV Managed Attachments support.

This module implements RFC 8607 - CalDAV Managed Attachments.
https://datatracker.ietf.org/doc/html/rfc8607
"""

import json
import os
import uuid

from icalendar import prop


class AttachmentStore:
    """Simple file-based attachment storage."""

    def __init__(self, base_path: str):
        self.base_path = base_path
        self.attachments_dir = os.path.join(base_path, ".attachments")

    def _ensure_dir(self):
        """Ensure attachments directory exists."""
        os.makedirs(self.attachments_dir, exist_ok=True)

    def create(
        self, data: bytes, content_type: str, filename: str | None = None
    ) -> str:
        """Store a new attachment and return its managed ID."""
        self._ensure_dir()

        managed_id = str(uuid.uuid4())
        attachment_path = os.path.join(self.attachments_dir, managed_id)

        # Store attachment data
        with open(attachment_path, "wb") as f:
            f.write(data)

        # Store metadata
        metadata = {
            "content_type": content_type,
            "filename": filename,
            "size": len(data),
        }
        with open(attachment_path + ".meta", "w") as f:
            json.dump(metadata, f)

        return managed_id

    def get(self, managed_id: str) -> tuple[bytes, str, str | None]:
        """Retrieve attachment data and metadata."""
        attachment_path = os.path.join(self.attachments_dir, managed_id)
        metadata_path = attachment_path + ".meta"

        if not os.path.exists(attachment_path) or not os.path.exists(metadata_path):
            raise KeyError(f"Attachment {managed_id} not found")

        with open(attachment_path, "rb") as f:
            data = f.read()

        with open(metadata_path) as f:
            metadata = json.load(f)

        return data, metadata["content_type"], metadata.get("filename")

    def delete(self, managed_id: str):
        """Delete an attachment."""
        attachment_path = os.path.join(self.attachments_dir, managed_id)
        metadata_path = attachment_path + ".meta"

        if not os.path.exists(attachment_path):
            raise KeyError(f"Attachment {managed_id} not found")

        os.remove(attachment_path)
        if os.path.exists(metadata_path):
            os.remove(metadata_path)

    def update(
        self,
        managed_id: str,
        data: bytes,
        content_type: str,
        filename: str | None = None,
    ):
        """Update an existing attachment."""
        attachment_path = os.path.join(self.attachments_dir, managed_id)
        metadata_path = attachment_path + ".meta"

        if not os.path.exists(attachment_path):
            raise KeyError(f"Attachment {managed_id} not found")

        # Update data
        with open(attachment_path, "wb") as f:
            f.write(data)

        # Update metadata
        metadata = {
            "content_type": content_type,
            "filename": filename,
            "size": len(data),
        }
        with open(metadata_path, "w") as f:
            json.dump(metadata, f)


def create_attach_property(
    url: str,
    managed_id: str,
    size: int,
    content_type: str,
    filename: str | None = None,
):
    """Create an ATTACH property with RFC 8607 parameters."""
    attach_prop = prop.vUri(url)
    attach_prop.params["MANAGED-ID"] = managed_id
    attach_prop.params["SIZE"] = str(size)
    attach_prop.params["FMTTYPE"] = content_type
    if filename:
        attach_prop.params["FILENAME"] = filename
    return attach_prop


def find_attach_property(component, managed_id: str):
    """Find an ATTACH property by managed ID in a component."""
    attach_props = component.get("ATTACH", [])
    if not isinstance(attach_props, list):
        attach_props = [attach_props]

    for attach_prop in attach_props:
        if attach_prop.params.get("MANAGED-ID") == managed_id:
            return attach_prop
    return None


def add_attach_to_component(component, attach_prop):
    """Add an ATTACH property to a component."""
    if "ATTACH" in component:
        existing = component["ATTACH"]
        if isinstance(existing, list):
            existing.append(attach_prop)
        else:
            component["ATTACH"] = [existing, attach_prop]
    else:
        component.add("ATTACH", attach_prop)


def remove_attach_from_component(component, managed_id: str):
    """Remove an ATTACH property by managed ID."""
    attach_props = component.get("ATTACH", [])
    if not isinstance(attach_props, list):
        attach_props = [attach_props]

    updated = [ap for ap in attach_props if ap.params.get("MANAGED-ID") != managed_id]

    if updated:
        component["ATTACH"] = updated[0] if len(updated) == 1 else updated
    elif "ATTACH" in component:
        del component["ATTACH"]


def find_calendar_component(calendar, rid: str | None = None):
    """Find the target component in a calendar."""
    for component in calendar.subcomponents:
        if component.name not in ("VEVENT", "VTODO", "VJOURNAL"):
            continue

        if rid:
            # Looking for specific recurrence
            recurrence_id = component.get("RECURRENCE-ID")
            if recurrence_id and str(recurrence_id) == rid:
                return component
        else:
            # Return first matching component
            return component

    return None


async def update_calendar_with_attachment(
    resource,
    calendar,
    managed_id: str,
    url: str,
    content_type: str,
    filename: str | None,
    size: int,
    rid: str | None = None,
):
    """Add or update an attachment in a calendar resource."""
    component = find_calendar_component(calendar, rid)
    if not component:
        raise ValueError("No suitable component found for attachment")

    # Create and add the ATTACH property
    attach_prop = create_attach_property(url, managed_id, size, content_type, filename)
    add_attach_to_component(component, attach_prop)

    # Save the calendar
    await resource.set_body(calendar.to_ical(), replace_etag=True)


async def remove_attachment_from_calendar(
    resource, calendar, managed_id: str, rid: str | None = None
):
    """Remove an attachment from a calendar resource."""
    component = find_calendar_component(calendar, rid)
    if not component:
        raise ValueError("No suitable component found")

    remove_attach_from_component(component, managed_id)

    # Save the calendar
    await resource.set_body(calendar.to_ical(), replace_etag=True)
