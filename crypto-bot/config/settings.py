# config/settings.py
"""Конфигурация приложения."""

import os
from dataclasses import dataclass
from typing import Optional


@dataclass
class AppConfig:
    """Основная конфигурация приложения."""
    
    # Telegram
    bot_token: str
    
    # База данных
    database_url: str
    
    # API ключи (опционально)
    etherscan_api_key: Optional[str] = None
    
    # Лимиты
    max_users_per_instance: int = 1000
    max_alerts_per_user: int = 50
    
    @classmethod
    def from_env(cls) -> "AppConfig":
        """Создание конфигурации из переменных окружения."""
        return cls(
            bot_token=os.getenv(
                "BOT_TOKEN", 
                "7512410143:AAF0MI-LrPVC8JXVhkYO0jtDs2Yn2uSnUlM"
            ),
            database_url=os.getenv(
                "DATABASE_URL",
                "postgresql://postgres:Zxasqw!2@localhost/crypto_bot"
            ),
            etherscan_api_key=os.getenv("ETHERSCAN_API_KEY")
        )
