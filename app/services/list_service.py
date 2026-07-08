from __future__ import annotations

import uuid
from datetime import datetime, timezone
from sqlalchemy.orm import Session

from app.models.social import MediaList, ListItem
from app.repositories.list_repository import ListRepository
from app.repositories.media_repository import MediaRepository


class ListService:
    def __init__(self, db: Session) -> None:
        self.db = db
        self.repo = ListRepository(db)
        self.media_repo = MediaRepository(db)

    def create_list(
        self,
        user_id: uuid.UUID,
        title: str,
        description: str | None = None,
        visibility: str = "public",
        items_data: list[dict] | None = None
    ) -> MediaList:
        # Create list first
        mlist = self.repo.create(
            user_id=user_id,
            title=title,
            description=description,
            visibility=visibility
        )

        # Add items if provided
        if items_data:
            # We sort items_data by position if provided, otherwise just position them sequentially
            sorted_items = sorted(items_data, key=lambda x: x.get("position", 0))
            for item in sorted_items:
                media_id = item["media_id"]
                # Check media exists
                media = self.media_repo.get_by_id(media_id)
                if not media:
                    raise ValueError(f"Media '{media_id}' not found")
                
                self.repo.add_item(
                    list_id=mlist.id,
                    media_id=media_id,
                    note=item.get("note")
                )

        self.db.commit()
        return mlist

    def update_list(
        self,
        list_id: uuid.UUID,
        user_id: uuid.UUID,
        **kwargs
    ) -> MediaList:
        mlist = self.repo.get_by_id(list_id)
        if not mlist:
            raise ValueError("List not found")
        if mlist.user_id != user_id:
            raise PermissionError("Insufficient permissions")

        updated_list = self.repo.update(mlist, **kwargs)
        self.db.commit()
        return updated_list

    def delete_list(self, list_id: uuid.UUID, user_id: uuid.UUID) -> None:
        mlist = self.repo.get_by_id(list_id)
        if not mlist:
            raise ValueError("List not found")
        if mlist.user_id != user_id:
            raise PermissionError("Insufficient permissions")

        self.repo.soft_delete(mlist)
        self.db.commit()

    def add_item_to_list(
        self,
        list_id: uuid.UUID,
        user_id: uuid.UUID,
        media_id: uuid.UUID,
        note: str | None = None
    ) -> ListItem:
        mlist = self.repo.get_by_id(list_id)
        if not mlist:
            raise ValueError("List not found")
        if mlist.user_id != user_id:
            raise PermissionError("Insufficient permissions")

        # Check media exists
        media = self.media_repo.get_by_id(media_id)
        if not media:
            raise ValueError("Media not found")

        # Check if item already exists in list
        for item in mlist.items:
            if item.media_id == media_id:
                raise ValueError("Media is already in the list")

        item = self.repo.add_item(list_id=list_id, media_id=media_id, note=note)
        self.db.commit()
        return item

    def remove_item_from_list(
        self,
        list_id: uuid.UUID,
        user_id: uuid.UUID,
        media_id: uuid.UUID
    ) -> None:
        mlist = self.repo.get_by_id(list_id)
        if not mlist:
            raise ValueError("List not found")
        if mlist.user_id != user_id:
            raise PermissionError("Insufficient permissions")

        success = self.repo.remove_item(list_id=list_id, media_id=media_id)
        if not success:
            raise ValueError("Item not found in list")
        
        self.db.commit()

    def reorder_list_items(
        self,
        list_id: uuid.UUID,
        user_id: uuid.UUID,
        media_ids: list[uuid.UUID]
    ) -> MediaList:
        mlist = self.repo.get_by_id(list_id)
        if not mlist:
            raise ValueError("List not found")
        if mlist.user_id != user_id:
            raise PermissionError("Insufficient permissions")

        self.repo.reorder_items(list_id, media_ids)
        self.db.commit()
        
        # Refresh from DB
        self.db.refresh(mlist)
        return mlist
