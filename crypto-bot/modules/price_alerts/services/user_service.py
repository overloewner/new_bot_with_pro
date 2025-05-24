"""Сервис для работы с пользователями."""

from typing import Dict, Any, Optional
from bot.db.repositories.user_repository import UserRepository
from bot.core.exceptions import UserNotFoundError, DatabaseError
from bot.core.logger import get_logger

logger = get_logger(__name__)


class UserService:
    """Сервис для управления пользователями."""
    
    def __init__(self, user_repository: UserRepository):
        self.user_repository = user_repository
    
    async def get_user_data(self, user_id: int) -> Dict[str, Any]:
        """Получение данных пользователя с ленивой инициализацией."""
        try:
            user = await self.user_repository.get_by_user_id(user_id)
            
            if not user:
                # Создаем нового пользователя
                logger.info(f"Creating new user {user_id}")
                user = await self.user_repository.create_user(user_id)
                
                return {
                    "active_presets": set(),
                    "presets": {},
                    "is_running": False
                }
            
            return {
                "active_presets": set(),  # Будет заполнено из preset_service
                "presets": {},  # Будет заполнено из preset_service
                "is_running": user.is_running
            }
        except DatabaseError:
            logger.error(f"Database error getting user data for {user_id}")
            raise
        except Exception as e:
            logger.error(f"Unexpected error getting user data for {user_id}: {e}")
            raise DatabaseError(f"Failed to get user data: {e}")
    
    async def update_running_status(self, user_id: int, is_running: bool) -> bool:
        """Обновление статуса запуска для пользователя."""
        try:
            if not await self.user_repository.user_exists(user_id):
                raise UserNotFoundError(f"User {user_id} not found")
            
            success = await self.user_repository.update_running_status(user_id, is_running)
            if success:
                logger.info(f"Updated running status for user {user_id}: {is_running}")
            return success
        except UserNotFoundError:
            raise
        except DatabaseError:
            logger.error(f"Database error updating running status for user {user_id}")
            raise
        except Exception as e:
            logger.error(f"Unexpected error updating running status for user {user_id}: {e}")
            raise DatabaseError(f"Failed to update running status: {e}")
    
    async def user_exists(self, user_id: int) -> bool:
        """Проверка существования пользователя."""
        try:
            return await self.user_repository.user_exists(user_id)
        except DatabaseError:
            logger.error(f"Database error checking if user {user_id} exists")
            raise
        except Exception as e:
            logger.error(f"Unexpected error checking if user {user_id} exists: {e}")
            raise DatabaseError(f"Failed to check user existence: {e}")
    
    async def create_user_if_not_exists(self, user_id: int) -> bool:
        """Создание пользователя, если он не существует."""
        try:
            if not await self.user_exists(user_id):
                await self.user_repository.create_user(user_id)
                logger.info(f"Created new user {user_id}")
                return True
            return False
        except DatabaseError:
            logger.error(f"Database error creating user {user_id}")
            raise
        except Exception as e:
            logger.error(f"Unexpected error creating user {user_id}: {e}")
            raise DatabaseError(f"Failed to create user: {e}")
    
    async def get_all_users_data(self) -> Dict[int, Dict[str, Any]]:
        """Получение данных всех пользователей."""
        try:
            return await self.user_repository.get_all_users_data()
        except DatabaseError:
            logger.error("Database error getting all users data")
            raise
        except Exception as e:
            logger.error(f"Unexpected error getting all users data: {e}")
            raise DatabaseError(f"Failed to get all users data: {e}")