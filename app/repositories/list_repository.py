from __future__ import annotations

import uuid
from datetime import datetime, timezone
from sqlalchemy import func, or_, select
from sqlalchemy.orm import Session

from app.models.social import MediaList, ListItem


class ListRepository:
    def __init__(self, db: Session) -> None:
        self.db = db

    def get_by_id(self, list_id: uuid.UUID) -> MediaList | None:
        stmt = select(MediaList).where(
            MediaList.id == list_id,
            MediaList.deleted_at.is_(None)
        )
        return self.db.scalar(stmt)

    def list_lists(
        self,
        user_id: uuid.UUID | None = None,
        visibility: str | None = None,
        viewer_user_id: uuid.UUID | None = None,
        limit: int = 20,
        offset: int = 0
    ) -> list[MediaList]:
        stmt = select(MediaList).where(MediaList.deleted_at.is_(None))
        if user_id:
            stmt = stmt.where(MediaList.user_id == user_id)
        if visibility:
            stmt = stmt.where(MediaList.visibility == visibility)
        if viewer_user_id:
            stmt = stmt.where(
                or_(MediaList.visibility == "public", MediaList.user_id == viewer_user_id)
            )
        stmt = stmt.order_by(MediaList.created_at.desc()).offset(offset).limit(limit)
        return list(self.db.scalars(stmt).all())

    def create(
        self,
        user_id: uuid.UUID,
        title: str,
        description: str | None = None,
        visibility: str = "public"
    ) -> MediaList:
        mlist = MediaList(
            user_id=user_id,
            title=title.strip(),
            description=description.strip() if description else None,
            visibility=visibility
        )
        self.db.add(mlist)
        self.db.flush()
        return mlist

    def update(self, mlist: MediaList, **kwargs) -> MediaList:
        for key, value in kwargs.items():
            if hasattr(mlist, key):
                val = value
                if isinstance(val, str):
                    val = val.strip()
                setattr(mlist, key, val)
        mlist.updated_at = datetime.now(timezone.utc)
        self.db.flush()
        return mlist

    def soft_delete(self, mlist: MediaList) -> None:
        mlist.deleted_at = datetime.now(timezone.utc)
        self.db.flush()

    def get_next_position(self, list_id: uuid.UUID) -> int:
        stmt = select(func.coalesce(func.max(ListItem.position), -1)).where(
            ListItem.list_id == list_id
        )
        max_pos = self.db.scalar(stmt)
        return max_pos + 1

    def add_item(self, list_id: uuid.UUID, media_id: uuid.UUID, note: str | None = None) -> ListItem:
        position = self.get_next_position(list_id)
        item = ListItem(
            list_id=list_id,
            media_id=media_id,
            position=position,
            note=note.strip() if note else None
        )
        self.db.add(item)
        self.db.flush()
        return item

    def update_item_note(self, item: ListItem, note: str | None) -> ListItem:
        item.note = note.strip() if note else None
        self.db.flush()
        return item

    def remove_item(self, list_id: uuid.UUID, media_id: uuid.UUID) -> bool:
        stmt = select(ListItem).where(
            ListItem.list_id == list_id,
            ListItem.media_id == media_id
        )
        item = self.db.scalar(stmt)
        if not item:
            return False
        
        self.db.delete(item)
        self.db.flush()

        # Re-normalize positions of remaining items
        self.normalize_positions(list_id)
        return True

    def normalize_positions(self, list_id: uuid.UUID) -> None:
        stmt = select(ListItem).where(ListItem.list_id == list_id).order_by(ListItem.position.asc())
        items = self.db.scalars(stmt).all()
        # Shift to temporary negative positions to avoid unique constraint violations
        for item in items:
            item.position = -1 - item.position
        self.db.flush()

        # Set to final normalized positions
        for idx, item in enumerate(items):
            item.position = idx
        self.db.flush()

    def reorder_items(self, list_id: uuid.UUID, media_ids: list[uuid.UUID]) -> None:
        # Load all items
        stmt = select(ListItem).where(ListItem.list_id == list_id)
        items = {item.media_id: item for item in self.db.scalars(stmt).all()}

        # Shift to temporary negative positions first to avoid unique constraint violations
        for item in items.values():
            item.position = -1 - item.position
        self.db.flush()

        # Reorder according to the media_ids list
        for position, media_id in enumerate(media_ids):
            if media_id in items:
                items[media_id].position = position
        
        # Any items not in the list should go to the end
        remaining_pos = len(media_ids)
        for media_id, item in items.items():
            if media_id not in media_ids:
                item.position = remaining_pos
                remaining_pos += 1

        self.db.flush()
