"""Репозиторий для работы с пользователями."""

from typing import Optional, Dict, Any
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from sqlalchemy.exc import SQLAlchemyError

from bot.db.models import User
from bot.db.repositories.base import BaseRepository
from bot.core.exceptions import DatabaseError


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
        return await self.create(user_id=user_id, is_running=False)
    
    async def update_running_status(self, user_id: int, is_running: bool) -> bool:
        """Обновление статуса running для пользователя."""
        try:
            from sqlalchemy import update
            result = await self.session.execute(
                update(User)
                .where(User.user_id == user_id)
                .values(is_running=is_running)
            )
            await self.session.commit()
            return result.rowcount > 0
        except SQLAlchemyError as e:
            await self.session.rollback()
            raise DatabaseError(f"Error updating user {user_id} running status: {e}")
    
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
                    "is_running": user.is_running
                }
            
            return users_data
        except SQLAlchemyError as e:
            raise DatabaseError(f"Error loading all users data: {e}")