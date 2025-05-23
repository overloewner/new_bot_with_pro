"""Сервис для работы с токенами."""

import asyncio
import aiohttp
import orjson
from datetime import datetime
from pathlib import Path
from typing import List, Dict, Any
from bot.core.config import TokenConfig
from bot.core.exceptions import TokenServiceError
from bot.core.logger import get_logger

logger = get_logger(__name__)


class TokenService:
    """Сервис для управления токенами и их конфигурацией."""
    
    def __init__(self, config: TokenConfig):
        self.config = config
        self.config_path = Path(config.config_path)
        self._cache = {
            "tokens": [],
            "timeframes": config.timeframes,
            "last_updated": None
        }
    
    async def load_config(self) -> Dict[str, Any]:
        """Загрузка конфигурации из файла."""
        try:
            if not self.config_path.exists():
                logger.warning(f"Config file {self.config_path} not found, creating default")
                await self.update_token_list()
            
            config_data = orjson.loads(self.config_path.read_text())
            self._cache.update(config_data)
            return config_data
        except Exception as e:
            logger.error(f"Error loading config from {self.config_path}: {e}")
            raise TokenServiceError(f"Failed to load token config: {e}")
    
    async def update_token_list(self) -> bool:
        """Обновление списка токенов из Binance API."""
        try:
            tokens = await self._fetch_top_tokens()
            config = {
                "tokens": tokens,
                "timeframes": self.config.timeframes,
                "last_updated": datetime.utcnow().isoformat()
            }
            
            # Обновляем кеш
            self._cache.update(config)
            
            # Сохраняем в файл
            await self._save_config(config)
            
            logger.info(f"Updated token list with {len(tokens)} tokens")
            return True
        except Exception as e:
            logger.error(f"Error updating token list: {e}")
            return False
    
    async def _fetch_top_tokens(self, max_retries: int = 3) -> List[Dict[str, Any]]:
        """Получение топ токенов с Binance."""
        url = "https://fapi.binance.com/fapi/v1/ticker/24hr"
        
        for attempt in range(max_retries):
            try:
                async with aiohttp.ClientSession(
                    timeout=aiohttp.ClientTimeout(total=10)
                ) as session:
                    async with session.get(url) as response:
                        if response.status == 200:
                            data = await response.json()
                            usdt_pairs = [
                                ticker for ticker in data 
                                if ticker['symbol'].endswith('USDT')
                            ]
                            return sorted(
                                usdt_pairs, 
                                key=lambda x: float(x['quoteVolume']), 
                                reverse=True
                            )[:self.config.top_tokens_limit]
                        else:
                            logger.warning(
                                f"Attempt {attempt + 1}: Binance API returned {response.status}"
                            )
            except Exception as e:
                logger.warning(f"Attempt {attempt + 1}: Connection error - {str(e)}")
                if attempt < max_retries - 1:
                    await asyncio.sleep(2 ** attempt)  # Exponential backoff
        
        raise TokenServiceError("Failed to fetch tokens after multiple attempts")
    
    async def _save_config(self, config: Dict[str, Any]) -> None:
        """Сохранение конфигурации в файл."""
        try:
            # Создаем директорию, если не существует
            self.config_path.parent.mkdir(parents=True, exist_ok=True)
            
            with open(self.config_path, 'wb') as f:
                f.write(orjson.dumps(
                    config,
                    option=orjson.OPT_INDENT_2 | orjson.OPT_SERIALIZE_NUMPY
                ))
        except Exception as e:
            logger.error(f"Error saving config to {self.config_path}: {e}")
            raise TokenServiceError(f"Failed to save token config: {e}")
    
    def get_all_tokens(self) -> List[str]:
        """Получение списка всех токенов."""
        return [token['symbol'] for token in self._cache["tokens"]]
    
    def get_all_timeframes(self) -> List[str]:
        """Получение списка всех таймфреймов."""
        return self._cache["timeframes"]
    
    def is_valid_token(self, token: str) -> bool:
        """Проверка валидности токена."""
        return token in self.get_all_tokens()
    
    async def get_tokens_by_volume(self, min_volume: float) -> List[str]:
        """Получение токенов с объемом выше указанного."""
        try:
            # Обновляем данные, если они устарели
            if not self._cache["tokens"]:
                await self.load_config()
            
            return [
                token['symbol'] 
                for token in self._cache["tokens"]
                if float(token.get('quoteVolume', 0)) > min_volume
            ]
        except Exception as e:
            logger.error(f"Error filtering tokens by volume {min_volume}: {e}")
            raise TokenServiceError(f"Failed to filter tokens by volume: {e}")
    
    def get_token_info(self, symbol: str) -> Dict[str, Any]:
        """Получение информации о токене."""
        for token in self._cache["tokens"]:
            if token['symbol'] == symbol:
                return token
        raise TokenServiceError(f"Token {symbol} not found")
    
    async def initialize(self) -> None:
        """Инициализация сервиса токенов."""
        try:
            await self.load_config()
            logger.info("Token service initialized successfully")
        except Exception as e:
            logger.error(f"Failed to initialize token service: {e}")
            raise
    
    def needs_update(self) -> bool:
        """Проверка необходимости обновления токенов."""
        if not self._cache.get("last_updated"):
            return True
        
        try:
            last_updated = datetime.fromisoformat(self._cache["last_updated"])
            time_diff = datetime.utcnow() - last_updated
            return time_diff.total_seconds() > self.config.update_interval
        except Exception:
            return True