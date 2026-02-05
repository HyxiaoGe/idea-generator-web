"""
Favorite models for bookmarking generated images.
"""

from typing import TYPE_CHECKING
from uuid import UUID, uuid4

from sqlalchemy import ForeignKey, Index, String, Text
from sqlalchemy.dialects.postgresql import UUID as PG_UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from .base import Base, TimestampMixin

if TYPE_CHECKING:
    from .image import GeneratedImage
    from .user import User


class FavoriteFolder(Base, TimestampMixin):
    """
    Folder for organizing favorites.

    Users can create multiple folders to organize their bookmarked images.
    """

    __tablename__ = "favorite_folders"

    # Primary key
    id: Mapped[UUID] = mapped_column(
        PG_UUID(as_uuid=True),
        primary_key=True,
        default=uuid4,
    )

    # Owner
    user_id: Mapped[UUID] = mapped_column(
        PG_UUID(as_uuid=True),
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )

    # Folder name
    name: Mapped[str] = mapped_column(
        String(100),
        nullable=False,
    )

    # Optional description
    description: Mapped[str | None] = mapped_column(
        Text,
        nullable=True,
    )

    # Relationships
    user: Mapped["User"] = relationship(
        "User",
        back_populates="favorite_folders",
    )
    favorites: Mapped[list["Favorite"]] = relationship(
        "Favorite",
        back_populates="folder",
        cascade="all, delete-orphan",
    )

    def __repr__(self) -> str:
        return f"<FavoriteFolder(id={self.id}, name={self.name})>"


class Favorite(Base, TimestampMixin):
    """
    Favorite record linking users to bookmarked images.
    """

    __tablename__ = "favorites"

    # Primary key
    id: Mapped[UUID] = mapped_column(
        PG_UUID(as_uuid=True),
        primary_key=True,
        default=uuid4,
    )

    # Owner
    user_id: Mapped[UUID] = mapped_column(
        PG_UUID(as_uuid=True),
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )

    # Reference to generated image
    image_id: Mapped[UUID] = mapped_column(
        PG_UUID(as_uuid=True),
        ForeignKey("generated_images.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )

    # Optional folder
    folder_id: Mapped[UUID | None] = mapped_column(
        PG_UUID(as_uuid=True),
        ForeignKey("favorite_folders.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )

    # Optional note
    note: Mapped[str | None] = mapped_column(
        Text,
        nullable=True,
    )

    # Relationships
    user: Mapped["User"] = relationship(
        "User",
        back_populates="favorites",
    )
    image: Mapped["GeneratedImage"] = relationship(
        "GeneratedImage",
        back_populates="favorites",
    )
    folder: Mapped["FavoriteFolder | None"] = relationship(
        "FavoriteFolder",
        back_populates="favorites",
    )

    def __repr__(self) -> str:
        return f"<Favorite(id={self.id}, user_id={self.user_id}, image_id={self.image_id})>"


# Indexes
Index("idx_favorite_folders_user_id", FavoriteFolder.user_id)
Index("idx_favorites_user_id", Favorite.user_id)
Index("idx_favorites_image_id", Favorite.image_id)
Index("idx_favorites_folder_id", Favorite.folder_id)
# Unique constraint: user can only favorite an image once
Index("idx_favorites_user_image_unique", Favorite.user_id, Favorite.image_id, unique=True)
