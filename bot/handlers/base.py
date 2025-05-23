"""Базовый обработчик."""

from abc import ABC
from aiogram import Router
from bot.storage import Storage
from bot.core.logger import get_logger


class BaseHandler(ABC):
    """Базовый класс для обработчиков."""
    
    def __init__(self, storage: Storage):
        self.storage = storage
        self.router = Router()
        self.logger = get_logger(self.__class__.__name__)
        
        # Настраиваем обработчики в дочерних классах
        self._setup_handlers()
    
    def _setup_handlers(self) -> None:
        """Настройка обработчиков. Должна быть переопределена в дочерних классах."""
        pass
    
    async def _handle_error(self, error: Exception, context: str = "") -> None:
        """Обработка ошибок."""
        self.logger.error(f"Error in {context}: {error}")
    
    async def _send_error_message(self, message, text: str = "Произошла ошибка. Попробуйте позже."):
        """Отправка сообщения об ошибке пользователю."""
        try:
            await message.answer(text)
        except Exception as e:
            self.logger.error(f"Failed to send error message: {e}")