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

"""SQL store backend using SQLAlchemy.

Provides a CalDAV/CardDAV storage backend backed by a relational database.
Supports any database supported by SQLAlchemy (SQLite, PostgreSQL, MySQL, etc.).

Usage:
    XANDIKOS_BACKEND=sql XANDIKOS_SQL_URL=sqlite:///xandikos.db xandikos serve

    Or with PostgreSQL:
    XANDIKOS_BACKEND=sql XANDIKOS_SQL_URL=postgresql://user:pass@localhost/xandikos xandikos serve
"""

import hashlib
import os
import uuid
from collections.abc import Iterable, Iterator
from datetime import datetime, timezone
from logging import getLogger

from sqlalchemy import (
    DateTime,
    ForeignKey,
    Index,
    Integer,
    LargeBinary,
    String,
    Text,
    UniqueConstraint,
    create_engine,
    event,
    select,
)
from sqlalchemy.orm import (
    DeclarativeBase,
    Mapped,
    Session,
    mapped_column,
    relationship,
    sessionmaker,
)

from . import (
    MIMETYPES,
    VALID_STORE_TYPES,
    DuplicateUidError,
    InvalidETag,
    NoSuchItem,
    NotStoreError,
    Store,
    open_by_content_type,
    open_by_extension,
)
from .index import MemoryIndex

logger = getLogger("xandikos")

# ---------------------------------------------------------------------------
# ORM Model
# ---------------------------------------------------------------------------


class Base(DeclarativeBase):
    pass


class Collection(Base):
    """A CalDAV/CardDAV collection (calendar or address book)."""

    __tablename__ = "collections"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    path: Mapped[str] = mapped_column(String(2048), unique=True, nullable=False)
    store_type: Mapped[str | None] = mapped_column(
        String(64), nullable=True
    )  # calendar, addressbook, etc.
    displayname: Mapped[str | None] = mapped_column(String(512), nullable=True)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    color: Mapped[str | None] = mapped_column(String(32), nullable=True)
    comment: Mapped[str | None] = mapped_column(Text, nullable=True)
    source_url: Mapped[str | None] = mapped_column(String(2048), nullable=True)
    order: Mapped[str | None] = mapped_column(String(64), nullable=True)
    refreshrate: Mapped[str | None] = mapped_column(String(64), nullable=True)
    timezone: Mapped[str | None] = mapped_column(Text, nullable=True)

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(timezone.utc)
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
        onupdate=lambda: datetime.now(timezone.utc),
    )

    items: Mapped[list["Item"]] = relationship(
        "Item", back_populates="collection", cascade="all, delete-orphan"
    )

    def __repr__(self) -> str:
        return f"<Collection(path={self.path!r}, type={self.store_type!r})>"


class Item(Base):
    """A single CalDAV/CardDAV resource (e.g. a VEVENT or VCARD)."""

    __tablename__ = "items"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    collection_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("collections.id", ondelete="CASCADE"), nullable=False
    )
    name: Mapped[str] = mapped_column(
        String(512), nullable=False
    )  # filename (e.g. "event.ics")
    uid: Mapped[str | None] = mapped_column(
        String(512), nullable=True
    )  # iCalendar/vCard UID
    content_type: Mapped[str] = mapped_column(String(128), nullable=False)  # MIME type
    data: Mapped[bytes] = mapped_column(LargeBinary, nullable=False)  # raw file content
    etag: Mapped[str] = mapped_column(String(64), nullable=False)

    dtstart: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    dtend: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    summary: Mapped[str | None] = mapped_column(String(1024), nullable=True)
    rrule: Mapped[str | None] = mapped_column(Text, nullable=True)
    recurrence_end: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(timezone.utc)
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
        onupdate=lambda: datetime.now(timezone.utc),
    )

    collection: Mapped["Collection"] = relationship(
        "Collection", back_populates="items"
    )

    __table_args__ = (
        UniqueConstraint("collection_id", "name", name="uq_collection_item_name"),
        Index("ix_collection_uid", "collection_id", "uid"),
        Index("ix_collection_dtstart", "collection_id", "dtstart"),
        Index("ix_collection_dtend", "collection_id", "dtend"),
    )

    def __repr__(self) -> str:
        return f"<Item(name={self.name!r}, uid={self.uid!r}, etag={self.etag!r})>"


# ---------------------------------------------------------------------------
# Helper: session management
# ---------------------------------------------------------------------------

_engines: dict[str, object] = {}
_session_factories: dict[str, sessionmaker] = {}


def _get_session_factory(db_url: str) -> sessionmaker:
    """Get or create a session factory for the given database URL."""
    if db_url not in _session_factories:
        engine = create_engine(db_url)
        # Enable WAL mode for SQLite for better concurrent access
        if db_url.startswith("sqlite"):

            @event.listens_for(engine, "connect")
            def set_sqlite_pragma(dbapi_conn, connection_record):
                cursor = dbapi_conn.cursor()
                cursor.execute("PRAGMA journal_mode=WAL")
                cursor.execute("PRAGMA foreign_keys=ON")
                cursor.close()

        Base.metadata.create_all(engine)
        _engines[db_url] = engine
        _session_factories[db_url] = sessionmaker(bind=engine)
    return _session_factories[db_url]


def _compute_etag(data: bytes) -> str:
    """Compute an ETag from content bytes."""
    return hashlib.sha256(data).hexdigest()[:40]


# ---------------------------------------------------------------------------
# SQLStore
# ---------------------------------------------------------------------------


class SQLStore(Store):
    """A Store backed by a SQL database via SQLAlchemy."""

    def __init__(
        self,
        db_url: str,
        collection_path: str,
        *,
        check_for_duplicate_uids: bool = True,
        **kwargs,
    ) -> None:
        super().__init__(MemoryIndex(), **kwargs)
        self._db_url = db_url
        self._collection_path = collection_path
        self._check_for_duplicate_uids = check_for_duplicate_uids
        self._session_factory = _get_session_factory(db_url)

    @property
    def path(self) -> str:
        return self._collection_path

    def _session(self) -> Session:
        return self._session_factory()

    def _get_collection(self, session: Session) -> Collection | None:
        return session.execute(
            select(Collection).where(Collection.path == self._collection_path)
        ).scalar_one_or_none()

    def _require_collection(self, session: Session) -> Collection:
        col = self._get_collection(session)
        if col is None:
            raise NotStoreError(self._collection_path)
        return col

    # -- Factory classmethods --

    @classmethod
    def _get_db_url(cls) -> str:
        url = os.environ.get("XANDIKOS_SQL_URL")
        if url is None:
            raise ValueError(
                "XANDIKOS_SQL_URL environment variable must be set for the SQL backend"
            )
        return url

    @classmethod
    def open_from_path(cls, path: str, **kwargs) -> "SQLStore":
        db_url = cls._get_db_url()
        session_factory = _get_session_factory(db_url)
        with session_factory() as session:
            col = session.execute(
                select(Collection).where(Collection.path == path)
            ).scalar_one_or_none()
            if col is None:
                raise NotStoreError(path)
        return cls(db_url, path, **kwargs)

    @classmethod
    def create(cls, path: str) -> "SQLStore":
        db_url = cls._get_db_url()
        session_factory = _get_session_factory(db_url)
        with session_factory() as session:
            existing = session.execute(
                select(Collection).where(Collection.path == path)
            ).scalar_one_or_none()
            if existing is not None:
                raise FileExistsError(path)
            col = Collection(path=path)
            session.add(col)
            session.commit()
        return cls(db_url, path)

    # -- Core read/write operations --

    def iter_with_etag(self, ctag: str | None = None) -> Iterator[tuple[str, str, str]]:
        with self._session() as session:
            col = self._get_collection(session)
            if col is None:
                return
            for item in col.items:
                yield (item.name, item.content_type, item.etag)

    def _get_raw(self, name: str, etag: str | None = None) -> Iterable[bytes]:
        with self._session() as session:
            col = self._require_collection(session)
            item = session.execute(
                select(Item).where(Item.collection_id == col.id, Item.name == name)
            ).scalar_one_or_none()
            if item is None:
                raise KeyError(name)
            if etag is not None and item.etag != etag:
                raise KeyError(name)
            return [item.data]

    def import_one(
        self,
        name: str,
        content_type: str,
        data: Iterable[bytes],
        message: str | None = None,
        author: str | None = None,
        replace_etag: str | None = None,
        requester: str | None = None,
    ) -> tuple[str, str]:
        if content_type is None:
            fi = open_by_extension(data, name, self.extra_file_handlers)
        else:
            fi = open_by_content_type(data, content_type, self.extra_file_handlers)

        if name is None:
            name = str(uuid.uuid4())
            extension = MIMETYPES.guess_extension(content_type)
            if extension is not None:
                name += extension

        fi.validate()

        try:
            uid = fi.get_uid()
        except (KeyError, NotImplementedError):
            uid = None

        sf: dict[str, object] = {
            "dtstart": None,
            "dtend": None,
            "summary": None,
            "rrule": None,
            "recurrence_end": None,
        }
        if hasattr(fi, "get_structured_fields"):
            try:
                sf = fi.get_structured_fields()
            except Exception:
                logger.debug("Failed to extract structured fields from %s", name)

        sf_dtstart: datetime | None = sf["dtstart"]  # type: ignore[assignment]
        sf_dtend: datetime | None = sf["dtend"]  # type: ignore[assignment]
        sf_summary: str | None = sf["summary"]  # type: ignore[assignment]
        sf_rrule: str | None = sf["rrule"]  # type: ignore[assignment]
        sf_recurrence_end: datetime | None = sf["recurrence_end"]  # type: ignore[assignment]

        normalized_data = b"".join(fi.normalized())
        new_etag = _compute_etag(normalized_data)

        with self._session() as session:
            col = self._require_collection(session)

            # Check for duplicate UID
            if uid is not None and self._check_for_duplicate_uids:
                existing = session.execute(
                    select(Item).where(
                        Item.collection_id == col.id,
                        Item.uid == uid,
                        Item.name != name,
                    )
                ).scalar_one_or_none()
                if existing is not None:
                    raise DuplicateUidError(uid, existing.name, name)

            # Check existing item
            item = session.execute(
                select(Item).where(Item.collection_id == col.id, Item.name == name)
            ).scalar_one_or_none()

            if item is not None:
                if replace_etag is not None and item.etag != replace_etag:
                    raise InvalidETag(name, replace_etag, item.etag)
                item.data = normalized_data
                item.etag = new_etag
                item.content_type = content_type
                item.uid = uid
                item.dtstart = sf_dtstart
                item.dtend = sf_dtend
                item.summary = sf_summary
                item.rrule = sf_rrule
                item.recurrence_end = sf_recurrence_end
            else:
                if replace_etag is not None:
                    raise InvalidETag(name, replace_etag, "(no existing item)")
                item = Item(
                    collection_id=col.id,
                    name=name,
                    uid=uid,
                    content_type=content_type,
                    data=normalized_data,
                    etag=new_etag,
                    dtstart=sf_dtstart,
                    dtend=sf_dtend,
                    summary=sf_summary,
                    rrule=sf_rrule,
                    recurrence_end=sf_recurrence_end,
                )
                session.add(item)

            session.commit()

        return (name, new_etag)

    def delete_one(
        self,
        name: str,
        message: str | None = None,
        author: str | None = None,
        etag: str | None = None,
    ) -> None:
        with self._session() as session:
            col = self._require_collection(session)
            item = session.execute(
                select(Item).where(Item.collection_id == col.id, Item.name == name)
            ).scalar_one_or_none()
            if item is None:
                raise NoSuchItem(name)
            if etag is not None and item.etag != etag:
                raise InvalidETag(name, etag, item.etag)
            session.delete(item)
            session.commit()

    def get_ctag(self) -> str:
        with self._session() as session:
            col = self._require_collection(session)
            # ctag = hash of all (name, etag) pairs, deterministic
            parts = sorted(f"{item.name}:{item.etag}" for item in col.items)
            return hashlib.sha256("|".join(parts).encode()).hexdigest()[:40]

    def iter_changes(
        self, old_ctag: str, new_ctag: str
    ) -> Iterator[tuple[str, str, str, str]]:
        # SQL store doesn't track historical state per-ctag.
        # Return empty — sync-collection will fall back to full listing.
        return iter([])

    # -- Metadata operations --

    def _get_meta(self, attr: str) -> str:
        with self._session() as session:
            col = self._require_collection(session)
            val = getattr(col, attr)
            if val is None:
                raise KeyError(attr)
            return val

    def _set_meta(self, attr: str, value: str | None) -> None:
        with self._session() as session:
            col = self._require_collection(session)
            setattr(col, attr, value)
            session.commit()

    def get_description(self) -> str:
        return self._get_meta("description")

    def set_description(self, description: str) -> None:
        self._set_meta("description", description)

    def get_displayname(self) -> str:
        return self._get_meta("displayname")

    def set_displayname(self, displayname: str) -> None:
        self._set_meta("displayname", displayname)

    def get_color(self) -> str:
        return self._get_meta("color")

    def set_color(self, color: str) -> None:
        self._set_meta("color", color)

    def get_comment(self) -> str:
        return self._get_meta("comment")

    def set_comment(self, comment: str) -> None:
        self._set_meta("comment", comment)

    def set_type(self, store_type: str) -> None:
        if store_type not in VALID_STORE_TYPES:
            raise ValueError(f"Invalid store type: {store_type}")
        self._set_meta("store_type", store_type)

    def get_type(self) -> str:
        try:
            return self._get_meta("store_type")
        except KeyError:
            return super().get_type()

    def get_source_url(self) -> str:
        return self._get_meta("source_url")

    def set_source_url(self, url: str) -> None:
        self._set_meta("source_url", url)

    def destroy(self) -> None:
        with self._session() as session:
            col = self._get_collection(session)
            if col is not None:
                session.delete(col)
                session.commit()

    def subdirectories(self) -> Iterator[str]:
        # SQL store doesn't have filesystem subdirectories
        return iter([])

    @classmethod
    def has_collections_under(cls, path: str) -> bool:
        """Check if any SQL collections exist under the given path prefix."""
        try:
            db_url = cls._get_db_url()
        except ValueError:
            return False
        session_factory = _get_session_factory(db_url)
        prefix = path.rstrip("/") + "/"
        with session_factory() as session:
            return (
                session.execute(
                    select(Collection.id).where(Collection.path.like(prefix + "%"))
                ).first()
                is not None
            )

    @classmethod
    def list_children_under(cls, path: str) -> list[str]:
        """List direct child collection names under a path prefix."""
        try:
            db_url = cls._get_db_url()
        except ValueError:
            return []
        session_factory = _get_session_factory(db_url)
        prefix = path.rstrip("/") + "/"
        with session_factory() as session:
            cols = session.execute(
                select(Collection.path).where(Collection.path.like(prefix + "%"))
            ).all()
            children = set()
            for (col_path,) in cols:
                remainder = col_path[len(prefix) :]
                first_component = remainder.split("/")[0]
                if first_component:
                    children.add(first_component)
            return sorted(children)
