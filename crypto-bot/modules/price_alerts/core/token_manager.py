# modules/price_alerts/core/token_manager.py
"""Менеджер токенов с кешированием."""

import asyncio
import aiohttp
import orjson
import time
from typing import List, Dict, Any, Optional
from pathlib import Path

from shared.utils.logger import get_module_logger

logger = get_module_logger("token_manager")


class TokenManager:
    """Менеджер токенов с автообновлением."""
    
    def __init__(self):
        # Кеш токенов
        self._tokens_cache: List[Dict[str, Any]] = []
        self._last_update: float = 0
        self._update_interval = 3600  # Обновляем каждый час
        
        # Конфигурация
        self.api_url = "https://fapi.binance.com/fapi/v1/ticker/24hr"
        self.top_tokens_limit = 100
        self.cache_file = Path("data/tokens_cache.json")
        
        # Статистика
        self._stats = {
            'total_tokens': 0,
            'last_update': 0,
            'update_errors': 0
        }
        
        # Создаем директорию для кеша
        self.cache_file.parent.mkdir(exist_ok=True)
    
    async def initialize(self):
        """Инициализация менеджера токенов."""
        try:
            # Пытаемся загрузить из кеша
            if await self._load_from_cache():
                logger.info("Loaded tokens from cache")
            else:
                # Если кеша нет, используем дефолтные токены
                self._set_default_tokens()
                logger.info("Using default token list")
            
            # Запускаем фоновое обновление
            asyncio.create_task(self._background_updater())
            
        except Exception as e:
            logger.error(f"Error initializing token manager: {e}")
            self._set_default_tokens()
    
    def get_all_tokens(self) -> List[str]:
        """Получение списка всех токенов."""
        return [token['symbol'] for token in self._tokens_cache]
    
    def get_all_timeframes(self) -> List[str]:
        """Получение списка всех таймфреймов."""
        return ["1m", "5m", "15m", "1h", "4h", "1d"]
    
    def get_tokens_by_volume(self, min_volume: float) -> List[str]:
        """Получение токенов с объемом выше указанного."""
        return [
            token['symbol'] 
            for token in self._tokens_cache
            if float(token.get('quoteVolume', 0)) >= min_volume
        ]
    
    def is_valid_token(self, symbol: str) -> bool:
        """Проверка валидности токена."""
        return symbol in self.get_all_tokens()
    
    async def update_tokens(self) -> bool:
        """Принудительное обновление токенов."""
        try:
            async with aiohttp.ClientSession() as session:
                async with session.get(self.api_url, timeout=aiohttp.ClientTimeout(total=30)) as response:
                    if response.status == 200:
                        data = await response.json()
                        
                        # Фильтруем USDT пары
                        usdt_pairs = [
                            ticker for ticker in data 
                            if ticker['symbol'].endswith('USDT')
                        ]
                        
                        # Сортируем по объему и берем топ
                        sorted_pairs = sorted(
                            usdt_pairs,
                            key=lambda x: float(x.get('quoteVolume', 0)),
                            reverse=True
                        )[:self.top_tokens_limit]
                        
                        self._tokens_cache = sorted_pairs
                        self._last_update = time.time()
                        
                        # Сохраняем в кеш
                        await self._save_to_cache()
                        
                        self._stats['total_tokens'] = len(self._tokens_cache)
                        self._stats['last_update'] = self._last_update
                        
                        logger.info(f"Updated {len(self._tokens_cache)} tokens from Binance")
                        return True
                    else:
                        logger.warning(f"Binance API returned status {response.status}")
                        
        except Exception as e:
            logger.error(f"Error updating tokens: {e}")
            self._stats['update_errors'] += 1
        
        return False
    
    async def _load_from_cache(self) -> bool:
        """Загрузка токенов из кеша."""
        try:
            if not self.cache_file.exists():
                return False
            
            with open(self.cache_file, 'rb') as f:
                cache_data = orjson.loads(f.read())
            
            # Проверяем возраст кеша
            cache_age = time.time() - cache_data.get('timestamp', 0)
            if cache_age > self._update_interval:
                logger.info("Cache is outdated, will update")
                return False
            
            self._tokens_cache = cache_data.get('tokens', [])
            self._last_update = cache_data.get('timestamp', 0)
            
            if self._tokens_cache:
                self._stats['total_tokens'] = len(self._tokens_cache)
                self._stats['last_update'] = self._last_update
                return True
                
        except Exception as e:
            logger.error(f"Error loading cache: {e}")
        
        return False
    
    async def _save_to_cache(self):
        """Сохранение токенов в кеш."""
        try:
            cache_data = {
                'tokens': self._tokens_cache,
                'timestamp': self._last_update
            }
            
            with open(self.cache_file, 'wb') as f:
                f.write(orjson.dumps(cache_data, option=orjson.OPT_INDENT_2))
                
        except Exception as e:
            logger.error(f"Error saving cache: {e}")
    
    def _set_default_tokens(self):
        """Установка дефолтного списка токенов."""
        default_tokens = [
            {'symbol': 'BTCUSDT', 'quoteVolume': '1000000000'},
            {'symbol': 'ETHUSDT', 'quoteVolume': '800000000'},
            {'symbol': 'BNBUSDT', 'quoteVolume': '200000000'},
            {'symbol': 'XRPUSDT', 'quoteVolume': '150000000'},
            {'symbol': 'ADAUSDT', 'quoteVolume': '100000000'},
            {'symbol': 'SOLUSDT', 'quoteVolume': '90000000'},
            {'symbol': 'DOGEUSDT', 'quoteVolume': '80000000'},
            {'symbol': 'DOTUSDT', 'quoteVolume': '70000000'},
            {'symbol': 'MATICUSDT', 'quoteVolume': '60000000'},
            {'symbol': 'AVAXUSDT', 'quoteVolume': '50000000'}
        ]
        
        self._tokens_cache = default_tokens
        self._last_update = time.time()
        self._stats['total_tokens'] = len(default_tokens)
        self._stats['last_update'] = self._last_update
    
    async def _background_updater(self):
        """Фоновое обновление токенов."""
        while True:
            try:
                # Ждем до следующего обновления
                time_since_update = time.time() - self._last_update
                sleep_time = max(60, self._update_interval - time_since_update)
                
                await asyncio.sleep(sleep_time)
                
                # Обновляем токены
                success = await self.update_tokens()
                if success:
                    logger.debug("Background token update completed")
                else:
                    logger.warning("Background token update failed")
                    
            except asyncio.CancelledError:
                logger.debug("Token updater cancelled")
                break
            except Exception as e:
                logger.error(f"Error in background updater: {e}")
                await asyncio.sleep(300)  # Пауза при ошибке
    
    def get_stats(self) -> Dict[str, Any]:
        """Получение статистики."""
        return self._stats.copy()