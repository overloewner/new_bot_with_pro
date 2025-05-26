# config/settings.py
"""Исправленная конфигурация приложения с корректным получением API ключей."""

import os
from dataclasses import dataclass
from typing import Optional
from pathlib import Path

# Загружаем .env файл если он есть - ИСПРАВЛЕНО: убрана зависимость от dotenv
env_path = Path(__file__).parent.parent / '.env'
if env_path.exists():
    try:
        # Простой парсер .env файла без зависимостей
        with open(env_path, 'r', encoding='utf-8') as f:
            for line in f:
                line = line.strip()
                if line and not line.startswith('#') and '=' in line:
                    key, value = line.split('=', 1)
                    key = key.strip()
                    value = value.strip().strip('"').strip("'")
                    if key and value:
                        os.environ[key] = value
        print(f"✅ Loaded .env file from {env_path}")
    except Exception as e:
        print(f"⚠️ Error loading .env file: {e}")
else:
    print(f"⚠️ .env file not found at {env_path}")


@dataclass
class DatabaseConfig:
    """Конфигурация базы данных."""
    url: str
    pool_size: int = 10
    max_overflow: int = 20
    pool_pre_ping: bool = True


@dataclass
class APIConfig:
    """Конфигурация API ключей."""
    etherscan_api_key: Optional[str] = None
    binance_api_key: Optional[str] = None
    binance_secret: Optional[str] = None
    coingecko_api_key: Optional[str] = None
    
    def has_etherscan_api(self) -> bool:
        """Проверка наличия Etherscan API ключа."""
        return bool(self.etherscan_api_key and self.etherscan_api_key.strip() and 
                   self.etherscan_api_key != "YourApiKeyToken")
    
    def get_etherscan_api_key(self) -> str:
        """Получение API ключа Etherscan или fallback."""
        if self.has_etherscan_api():
            return self.etherscan_api_key
        return "YourApiKeyToken"  # Fallback для ограниченных запросов
    
    def has_binance_api(self) -> bool:
        """Проверка наличия Binance API ключей."""
        return bool(self.binance_api_key and self.binance_secret and 
                   self.binance_api_key.strip() and self.binance_secret.strip())


@dataclass
class AppConfig:
    """Основная конфигурация приложения."""
    
    # Telegram
    bot_token: str
    
    # База данных
    database: DatabaseConfig
    
    # API ключи
    api: APIConfig
    
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
            print("⚠️ Using default BOT_TOKEN. Set BOT_TOKEN in .env for production")
        
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
        
        # API ключи
        api_config = APIConfig(
            etherscan_api_key=os.getenv("ETHERSCAN_API_KEY"),
            binance_api_key=os.getenv("BINANCE_API_KEY"),
            binance_secret=os.getenv("BINANCE_SECRET"),
            coingecko_api_key=os.getenv("COINGECKO_API_KEY")
        )
        
        # Отладочная информация
        debug = os.getenv("DEBUG", "false").lower() in ("true", "1", "yes")
        
        config = cls(
            bot_token=bot_token,
            database=database_config,
            api=api_config,
            max_users_per_instance=int(os.getenv("MAX_USERS", "1000")),
            max_alerts_per_user=int(os.getenv("MAX_ALERTS_PER_USER", "50")),
            debug=debug
        )
        
        # Выводим информацию о конфигурации
        print("🔧 Configuration loaded:")
        print(f"   Bot token: {'✅ Set' if bot_token else '❌ Missing'}")
        print(f"   Database: {'✅ Configured' if database_url else '❌ Missing'}")
        print(f"   Etherscan API: {'✅ Available' if api_config.has_etherscan_api() else '⚠️ Limited (free tier)'}")
        print(f"   Binance API: {'✅ Available' if api_config.has_binance_api() else '⚠️ Using public endpoints'}")
        print(f"   Debug mode: {'✅ Enabled' if debug else '❌ Disabled'}")
        
        return config
    
    def get_database_url(self) -> str:
        """Получение URL базы данных."""
        return self.database.url
    
    def is_production(self) -> bool:
        """Проверка production режима."""
        return not self.debug and self.api.has_etherscan_api()


# Создаем глобальный экземпляр конфигурации
_config = None

def get_config() -> AppConfig:
    """Получение глобальной конфигурации."""
    global _config
    if _config is None:
        _config = AppConfig.from_env()
    return _config