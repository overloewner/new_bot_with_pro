"""Конфигурация приложения."""

from dataclasses import dataclass
from typing import List
import os


@dataclass
class DatabaseConfig:
    """Конфигурация базы данных."""
    url: str
    pool_size: int = 20
    max_overflow: int = 10
    pool_pre_ping: bool = True


@dataclass
class BinanceConfig:
    """Конфигурация Binance WebSocket."""
    ws_url: str = "wss://stream.binance.com:9443/stream?streams="
    api_url: str = "https://fapi.binance.com/fapi/v1/ticker/24hr"
    max_streams_per_connection: int = 750
    reconnect_delay: int = 5
    connection_timeout: int = 10


@dataclass
class RateLimitConfig:
    """Конфигурация ограничения запросов."""
    global_limit: int = 30
    global_interval: float = 1.0
    user_message_interval: float = 1.0
    max_messages_per_batch: int = 50


@dataclass
class ProcessingConfig:
    """Конфигурация обработки данных."""
    max_queue_size: int = 20000
    batch_size: int = 500
    batch_timeout: float = 0.3
    cooldown_time: int = 60


@dataclass
class TokenConfig:
    """Конфигурация токенов."""
    config_path: str = "bot/tokens.json"
    top_tokens_limit: int = 500
    update_interval: int = 3600
    timeframes: List[str] = None

    def __post_init__(self):
        if self.timeframes is None:
            self.timeframes = ["1s", "1m", "5m", "15m", "1h", "4h", "1d"]


@dataclass
class AppConfig:
    """Основная конфигурация приложения."""
    bot_token: str
    database: DatabaseConfig
    binance: BinanceConfig = None
    rate_limit: RateLimitConfig = None
    processing: ProcessingConfig = None
    token: TokenConfig = None

    def __post_init__(self):
        if self.binance is None:
            self.binance = BinanceConfig()
        if self.rate_limit is None:
            self.rate_limit = RateLimitConfig()
        if self.processing is None:
            self.processing = ProcessingConfig()
        if self.token is None:
            self.token = TokenConfig()

    @classmethod
    def from_env(cls) -> "AppConfig":
        """Создает конфигурацию из переменных окружения."""
        bot_token = os.getenv("BOT_TOKEN", "7877054794:AAEJO3tifLlvGvMawhubEfUcMn609qt30QQ")
        
        db_url = os.getenv(
            "DATABASE_URL", 
            "postgresql://postgres:Zxasqw!2@localhost/crypto_bot"
        )
        
        return cls(
            bot_token=bot_token,
            database=DatabaseConfig(url=db_url)
        )