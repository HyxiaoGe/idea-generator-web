"""
User repository for user CRUD operations.
"""

from datetime import datetime
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from database.models import User


class UserRepository:
    """Repository for User model operations."""

    def __init__(self, session: AsyncSession):
        self.session = session

    async def get_by_id(self, user_id: UUID) -> User | None:
        """Get user by ID."""
        result = await self.session.execute(select(User).where(User.id == user_id))
        return result.scalar_one_or_none()

    async def get_by_auth_id(self, auth_id: str) -> User | None:
        """Get user by auth-service ID."""
        result = await self.session.execute(select(User).where(User.auth_id == auth_id))
        return result.scalar_one_or_none()

    async def get_by_github_id(self, github_id: int) -> User | None:
        """Get user by GitHub ID (legacy)."""
        result = await self.session.execute(select(User).where(User.github_id == github_id))
        return result.scalar_one_or_none()

    async def get_by_username(self, username: str) -> User | None:
        """Get user by username."""
        result = await self.session.execute(select(User).where(User.username == username))
        return result.scalar_one_or_none()

    async def create(
        self,
        github_id: int,
        username: str,
        email: str | None = None,
        avatar_url: str | None = None,
        display_name: str | None = None,
    ) -> User:
        """Create a new user."""
        user = User(
            github_id=github_id,
            username=username,
            email=email,
            avatar_url=avatar_url,
            display_name=display_name,
            last_login_at=datetime.now(),
        )
        self.session.add(user)
        await self.session.flush()
        return user

    async def create_or_update_from_auth(
        self,
        auth_id: str,
        email: str | None = None,
        name: str | None = None,
        avatar_url: str | None = None,
    ) -> User:
        """
        Create or update user from auth-service JWT data.

        If user exists, updates their info and last login time.
        If user doesn't exist, creates a new user.
        """
        user = await self.get_by_auth_id(auth_id)

        if user:
            user.email = email
            user.display_name = name
            user.avatar_url = avatar_url
            user.last_login_at = datetime.now()
        else:
            user = User(
                auth_id=auth_id,
                github_id=None,
                username=email or auth_id,
                email=email,
                avatar_url=avatar_url,
                display_name=name,
                last_login_at=datetime.now(),
            )
            self.session.add(user)

        await self.session.flush()
        return user

    async def create_or_update_from_github(
        self,
        github_id: int,
        username: str,
        email: str | None = None,
        avatar_url: str | None = None,
        display_name: str | None = None,
    ) -> User:
        """
        Create or update user from GitHub OAuth data.

        If user exists, updates their info and last login time.
        If user doesn't exist, creates a new user.
        """
        user = await self.get_by_github_id(github_id)

        if user:
            # Update existing user
            user.username = username
            user.email = email
            user.avatar_url = avatar_url
            user.display_name = display_name
            user.last_login_at = datetime.now()
        else:
            # Create new user
            user = await self.create(
                github_id=github_id,
                username=username,
                email=email,
                avatar_url=avatar_url,
                display_name=display_name,
            )

        await self.session.flush()
        return user

    async def update_last_login(self, user_id: UUID) -> User | None:
        """Update user's last login time."""
        user = await self.get_by_id(user_id)
        if user:
            user.last_login_at = datetime.now()
            await self.session.flush()
        return user

    async def update_tier(
        self,
        user_id: UUID,
        tier: str,
        quota_multiplier: float = 1.0,
    ) -> User | None:
        """Update user's subscription tier."""
        user = await self.get_by_id(user_id)
        if user:
            user.tier = tier
            user.custom_quota_multiplier = quota_multiplier
            await self.session.flush()
        return user

    async def delete(self, user_id: UUID) -> bool:
        """Delete a user (cascades to related records)."""
        user = await self.get_by_id(user_id)
        if user:
            await self.session.delete(user)
            await self.session.flush()
            return True
        return False
