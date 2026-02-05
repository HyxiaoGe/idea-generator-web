"""
Notification repository for notification CRUD operations.
"""

from datetime import datetime
from uuid import UUID

from sqlalchemy import desc, func, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from database.models import Notification


class NotificationRepository:
    """Repository for Notification model operations."""

    def __init__(self, session: AsyncSession):
        self.session = session

    async def get_by_id(self, notification_id: UUID) -> Notification | None:
        """Get notification by ID."""
        result = await self.session.execute(
            select(Notification).where(Notification.id == notification_id)
        )
        return result.scalar_one_or_none()

    async def create(
        self,
        user_id: UUID,
        type: str,
        title: str,
        message: str | None = None,
        data: dict | None = None,
    ) -> Notification:
        """Create a new notification."""
        notification = Notification(
            user_id=user_id,
            type=type,
            title=title,
            message=message,
            data=data or {},
        )
        self.session.add(notification)
        await self.session.flush()
        return notification

    async def list_by_user(
        self,
        user_id: UUID,
        is_read: bool | None = None,
        type: str | None = None,
        limit: int = 50,
        offset: int = 0,
    ) -> list[Notification]:
        """List notifications for a user."""
        query = select(Notification).where(Notification.user_id == user_id)

        if is_read is not None:
            query = query.where(Notification.is_read == is_read)

        if type:
            query = query.where(Notification.type == type)

        query = query.order_by(desc(Notification.created_at)).limit(limit).offset(offset)

        result = await self.session.execute(query)
        return list(result.scalars().all())

    async def count_by_user(
        self,
        user_id: UUID,
        is_read: bool | None = None,
    ) -> int:
        """Count notifications for a user."""
        query = (
            select(func.count()).select_from(Notification).where(Notification.user_id == user_id)
        )

        if is_read is not None:
            query = query.where(Notification.is_read == is_read)

        result = await self.session.execute(query)
        return result.scalar_one()

    async def count_unread(self, user_id: UUID) -> int:
        """Count unread notifications for a user."""
        return await self.count_by_user(user_id, is_read=False)

    async def mark_read(self, notification_id: UUID) -> Notification | None:
        """Mark a notification as read."""
        notification = await self.get_by_id(notification_id)
        if not notification:
            return None

        notification.is_read = True
        notification.read_at = datetime.now(notification.created_at.tzinfo)
        await self.session.flush()
        return notification

    async def mark_all_read(self, user_id: UUID) -> int:
        """Mark all notifications as read for a user."""
        result = await self.session.execute(
            update(Notification)
            .where(
                Notification.user_id == user_id,
                not Notification.is_read,
            )
            .values(is_read=True, read_at=func.now())
        )
        await self.session.flush()
        return result.rowcount

    async def mark_multiple_read(self, user_id: UUID, notification_ids: list[UUID]) -> int:
        """Mark multiple notifications as read."""
        result = await self.session.execute(
            update(Notification)
            .where(
                Notification.id.in_(notification_ids),
                Notification.user_id == user_id,
                not Notification.is_read,
            )
            .values(is_read=True, read_at=func.now())
        )
        await self.session.flush()
        return result.rowcount

    async def delete(self, notification_id: UUID) -> bool:
        """Delete a notification."""
        notification = await self.get_by_id(notification_id)
        if notification:
            await self.session.delete(notification)
            await self.session.flush()
            return True
        return False

    async def delete_by_user(self, user_id: UUID, notification_id: UUID) -> bool:
        """Delete a notification owned by a specific user."""
        result = await self.session.execute(
            select(Notification).where(
                Notification.id == notification_id,
                Notification.user_id == user_id,
            )
        )
        notification = result.scalar_one_or_none()
        if notification:
            await self.session.delete(notification)
            await self.session.flush()
            return True
        return False

    async def delete_all_read(self, user_id: UUID) -> int:
        """Delete all read notifications for a user."""
        result = await self.session.execute(
            select(Notification).where(
                Notification.user_id == user_id,
                Notification.is_read,
            )
        )
        notifications = list(result.scalars().all())
        for notification in notifications:
            await self.session.delete(notification)
        await self.session.flush()
        return len(notifications)

    async def bulk_create(
        self,
        user_ids: list[UUID],
        type: str,
        title: str,
        message: str | None = None,
        data: dict | None = None,
    ) -> list[Notification]:
        """Create notifications for multiple users (broadcast)."""
        notifications = []
        for user_id in user_ids:
            notification = Notification(
                user_id=user_id,
                type=type,
                title=title,
                message=message,
                data=data or {},
            )
            self.session.add(notification)
            notifications.append(notification)

        await self.session.flush()
        return notifications
