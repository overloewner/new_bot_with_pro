# config/base.py
"""Основная конфигурация приложения."""

import os
from dataclasses import dataclass
from typing import Optional

@dataclass
class DatabaseConfig:
    """Конфигурация базы данных."""
    url: str
    pool_size: int = 10
    max_overflow: int = 20
    pool_pre_ping: bool = True

@dataclass
class AppConfig:
    """Основная конфигурация приложения."""
    
    # Telegram
    bot_token: str
    
    # База данных
    database: DatabaseConfig
    
    # Лимиты
    max_users_per_instance: int = 1000
    max_alerts_per_user: int = 50
    
    # Режим отладки
    debug: bool = False
    
    @classmethod
    def from_env(cls) -> "AppConfig":
        """Создание конфигурации из переменных окружения."""
        
        # Получаем основные параметры
        bot_token = os.getenv("BOT_TOKEN")
        if not bot_token:
            # Используем тестовый токен если не задан
            bot_token = "7512410143:AAF0MI-LrPVC8JXVhkYO0jtDs2Yn2uSnUlM"
            print("⚠️ Using default BOT_TOKEN")
        
        # База данных
        database_url = os.getenv(
            "DATABASE_URL",
            "postgresql://postgres:Zxasqw!2@localhost/crypto_bot"
        )
        
        database_config = DatabaseConfig(
            url=database_url,
            pool_size=int(os.getenv("DB_POOL_SIZE", "10")),
            max_overflow=int(os.getenv("DB_MAX_OVERFLOW", "20"))
        )
        
        # Отладочная информация
        debug = os.getenv("DEBUG", "false").lower() in ("true", "1", "yes")
        
        config = cls(
            bot_token=bot_token,
            database=database_config,
            max_users_per_instance=int(os.getenv("MAX_USERS", "1000")),
            max_alerts_per_user=int(os.getenv("MAX_ALERTS_PER_USER", "50")),
            debug=debug
        )
        
        # Выводим информацию о конфигурации
        print("🔧 Configuration loaded:")
        print(f"   Bot token: {'✅ Set' if bot_token else '❌ Missing'}")
        print(f"   Database: {'✅ Configured' if database_url else '❌ Missing'}")
        print(f"   Debug mode: {'✅ Enabled' if debug else '❌ Disabled'}")
        
        return config
    
    def get_database_url(self) -> str:
        """Получение URL базы данных."""
        return self.database.url
    
    def is_production(self) -> bool:
        """Проверка production режима."""
        return not self.debug

# Создаем глобальный экземпляр конфигурации
_config = None

def get_config() -> AppConfig:
    """Получение глобальной конфигурации."""
    global _config
    if _config is None:
        _config = AppConfig.from_env()
    return _config