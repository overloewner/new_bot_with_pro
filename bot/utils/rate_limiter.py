"""Ограничитель запросов."""

import asyncio
import time
from typing import Dict
from bot.core.config import RateLimitConfig
from bot.core.exceptions import RateLimitError
from bot.core.logger import get_logger

logger = get_logger(__name__)


class GlobalRateLimiter:
    """Глобальный ограничитель запросов."""
    
    def __init__(self, config: RateLimitConfig):
        self.config = config
        self._semaphore = asyncio.Semaphore(config.global_limit)
        self._last_reset = time.time()
        self._lock = asyncio.Lock()
    
    async def acquire(self) -> None:
        """Получение разрешения на выполнение запроса."""
        async with self._lock:
            elapsed = time.time() - self._last_reset
            
            if elapsed >= self.config.global_interval:
                self._last_reset = time.time()
                # Сбрасываем семафор
                self._semaphore = asyncio.Semaphore(self.config.global_limit)
        
        try:
            await asyncio.wait_for(
                self._semaphore.acquire(), 
                timeout=self.config.global_interval * 2
            )
        except asyncio.TimeoutError:
            raise RateLimitError("Global rate limit exceeded")
    
    def release(self) -> None:
        """Освобождение разрешения."""
        try:
            self._semaphore.release()
        except ValueError:
            # Семафор уже освобожден
            pass


class UserRateLimiter:
    """Ограничитель запросов для отдельных пользователей."""
    
    def __init__(self, config: RateLimitConfig):
        self.config = config
        self._user_last_message: Dict[int, float] = {}
        self._lock = asyncio.Lock()
    
    async def can_send_message(self, user_id: int) -> bool:
        """Проверка возможности отправки сообщения пользователю."""
        async with self._lock:
            current_time = time.time()
            last_message_time = self._user_last_message.get(user_id, 0)
            
            if current_time - last_message_time >= self.config.user_message_interval:
                self._user_last_message[user_id] = current_time
                return True
            
            return False
    
    async def wait_for_user(self, user_id: int) -> None:
        """Ожидание до возможности отправки сообщения пользователю."""
        while not await self.can_send_message(user_id):
            await asyncio.sleep(0.1)
    
    def cleanup_old_entries(self, max_age: int = 3600) -> None:
        """Очистка старых записей."""
        current_time = time.time()
        self._user_last_message = {
            user_id: last_time
            for user_id, last_time in self._user_last_message.items()
            if current_time - last_time < max_age
        }