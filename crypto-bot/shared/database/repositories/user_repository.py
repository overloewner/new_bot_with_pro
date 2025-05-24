"""Репозиторий для работы с пользователями."""

from typing import Optional, Dict, Any
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from sqlalchemy.exc import SQLAlchemyError

from shared.database.models import User  # ИСПРАВЛЕНИЕ: Изменен путь
from shared.database.repositories.base_repository import BaseRepository  # ИСПРАВЛЕНИЕ: Изменен путь
from shared.exceptions import DatabaseError  # ИСПРАВЛЕНИЕ: Изменен путь


class UserRepository(BaseRepository[User]):
    """Репозиторий для работы с пользователями."""
    
    def __init__(self, session: AsyncSession):
        super().__init__(session, User)
    
    async def get_by_user_id(self, user_id: int) -> Optional[User]:
        """Получение пользователя по user_id."""
        try:
            result = await self.session.execute(
                select(User).where(User.user_id == user_id)
            )
            return result.scalar_one_or_none()
        except SQLAlchemyError as e:
            raise DatabaseError(f"Error getting user by user_id {user_id}: {e}")
    
    async def create_user(self, user_id: int) -> User:
        """Создание нового пользователя."""
        return await self.create(user_id=user_id, is_active=True)  # ИСПРАВЛЕНИЕ: Изменено is_running на is_active
    
    async def update_active_status(self, user_id: int, is_active: bool) -> bool:  # ИСПРАВЛЕНИЕ: Переименовано
        """Обновление статуса active для пользователя."""
        try:
            from sqlalchemy import update
            result = await self.session.execute(
                update(User)
                .where(User.user_id == user_id)
                .values(is_active=is_active)  # ИСПРАВЛЕНИЕ: Изменено is_running на is_active
            )
            await self.session.commit()
            return result.rowcount > 0
        except SQLAlchemyError as e:
            await self.session.rollback()
            raise DatabaseError(f"Error updating user {user_id} active status: {e}")  # ИСПРАВЛЕНИЕ: Обновлено сообщение
    
    async def user_exists(self, user_id: int) -> bool:
        """Проверка существования пользователя."""
        user = await self.get_by_user_id(user_id)
        return user is not None
    
    async def get_all_users_data(self) -> Dict[int, Dict[str, Any]]:
        """Получение данных всех пользователей для инициализации."""
        try:
            users = await self.get_all()
            users_data = {}
            
            for user in users:
                users_data[user.user_id] = {
                    "active_presets": set(),
                    "presets": {},
                    "is_active": user.is_active  # ИСПРАВЛЕНИЕ: Изменено is_running на is_active
                }
            
            return users_data
        except SQLAlchemyError as e:
            raise DatabaseError(f"Error loading all users data: {e}")