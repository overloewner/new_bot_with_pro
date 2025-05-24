# modules/price_alerts/websocket/reconnect_manager.py
"""Адаптированный менеджер переподключений."""

import asyncio
import time
from typing import Optional, Dict, Any
from shared.utils.logger import get_module_logger

logger = get_module_logger("reconnect_manager")


class ReconnectManager:
    """Менеджер переподключений с экспоненциальной задержкой."""
    
    def __init__(self, base_delay: int = 5, max_delay: int = 300, max_attempts: int = 10):
        self.base_delay = base_delay
        self.max_delay = max_delay
        self.max_attempts = max_attempts
        
        # Состояние
        self.attempt_count = 0
        self.last_success_time: Optional[float] = None
        self.consecutive_failures = 0
    
    async def wait_before_reconnect(self) -> None:
        """Ожидание перед переподключением."""
        self.attempt_count += 1
        self.consecutive_failures += 1
        
        # Экспоненциальная задержка
        delay = min(
            self.base_delay * (2 ** (self.consecutive_failures - 1)),
            self.max_delay
        )
        
        logger.info(
            f"Reconnect attempt {self.attempt_count} "
            f"(failures: {self.consecutive_failures}). Waiting {delay}s..."
        )
        
        await asyncio.sleep(delay)
        
        # Дополнительная задержка при превышении лимита
        if self.consecutive_failures >= self.max_attempts:
            logger.warning(
                f"Too many failures ({self.consecutive_failures}). "
                "Extended delay..."
            )
            await asyncio.sleep(self.max_delay)
    
    def reset(self) -> None:
        """Сброс при успешном подключении."""
        if self.consecutive_failures > 0:
            logger.info(f"Connection restored after {self.consecutive_failures} failures")
        
        self.consecutive_failures = 0
        self.last_success_time = time.time()
    
    def get_stats(self) -> Dict[str, Any]:
        """Получение статистики."""
        current_time = time.time()
        uptime = (
            current_time - self.last_success_time 
            if self.last_success_time else 0
        )
        
        return {
            "total_attempts": self.attempt_count,
            "consecutive_failures": self.consecutive_failures,
            "uptime_seconds": round(uptime, 2),
            "last_success_time": self.last_success_time
        }