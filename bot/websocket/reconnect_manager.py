"""Менеджер переподключений WebSocket."""

import asyncio
import time
from typing import Optional
from bot.core.logger import get_logger

logger = get_logger(__name__)


class ReconnectManager:
    """Менеджер переподключений с экспоненциальной задержкой."""
    
    def __init__(self, base_delay: int = 5, max_delay: int = 300, max_attempts: int = 10):
        """Инициализация менеджера переподключений.
        
        Args:
            base_delay: Базовая задержка в секундах
            max_delay: Максимальная задержка в секундах
            max_attempts: Максимальное количество попыток подряд
        """
        self.base_delay = base_delay
        self.max_delay = max_delay
        self.max_attempts = max_attempts
        
        # Состояние
        self.attempt_count = 0
        self.last_success_time: Optional[float] = None
        self.consecutive_failures = 0
    
    async def wait_before_reconnect(self) -> None:
        """Ожидание перед переподключением с экспоненциальной задержкой."""
        self.attempt_count += 1
        self.consecutive_failures += 1
        
        # Вычисляем задержку
        delay = min(
            self.base_delay * (2 ** (self.consecutive_failures - 1)),
            self.max_delay
        )
        
        logger.info(
            f"Reconnect attempt {self.attempt_count} "
            f"(consecutive failures: {self.consecutive_failures}). "
            f"Waiting {delay} seconds..."
        )
        
        await asyncio.sleep(delay)
        
        # Проверяем лимит попыток
        if self.consecutive_failures >= self.max_attempts:
            logger.error(
                f"Too many consecutive failures ({self.consecutive_failures}). "
                "Consider checking connection or configuration."
            )
            # Дополнительная задержка при превышении лимита
            await asyncio.sleep(self.max_delay)
    
    def reset(self) -> None:
        """Сброс счетчиков при успешном подключении."""
        if self.consecutive_failures > 0:
            logger.info(
                f"Connection restored after {self.consecutive_failures} failures"
            )
        
        self.consecutive_failures = 0
        self.last_success_time = time.time()
    
    def should_give_up(self) -> bool:
        """Проверка, следует ли прекратить попытки переподключения."""
        return self.consecutive_failures >= self.max_attempts * 2
    
    def get_next_delay(self) -> int:
        """Получение следующей задержки без её применения."""
        return min(
            self.base_delay * (2 ** self.consecutive_failures),
            self.max_delay
        )
    
    def get_stats(self) -> dict:
        """Получение статистики переподключений."""
        current_time = time.time()
        uptime = (
            current_time - self.last_success_time 
            if self.last_success_time else 0
        )
        
        return {
            "total_attempts": self.attempt_count,
            "consecutive_failures": self.consecutive_failures,
            "last_success_time": self.last_success_time,
            "uptime_seconds": uptime,
            "next_delay": self.get_next_delay()
        }