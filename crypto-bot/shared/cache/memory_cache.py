# shared/cache/memory_cache.py
"""Высокопроизводительный кеш в памяти для минимизации запросов к БД."""

import asyncio
import time
import pickle
import hashlib
from typing import Any, Dict, Optional, Callable, Union, List, Set
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from collections import defaultdict, OrderedDict
from weakref import WeakValueDictionary
import threading
import logging

logger = logging.getLogger(__name__)


@dataclass
class CacheEntry:
    """Запись в кеше."""
    value: Any
    created_at: float
    expires_at: Optional[float] = None
    access_count: int = 0
    last_accessed: float = field(default_factory=time.time)
    size_bytes: int = 0
    tags: Set[str] = field(default_factory=set)


@dataclass
class CacheStats:
    """Статистика кеша."""
    hits: int = 0
    misses: int = 0
    sets: int = 0
    deletes: int = 0
    evictions: int = 0
    memory_usage: int = 0
    total_entries: int = 0


class MemoryCache:
    """
    Высокопроизводительный кеш в памяти с поддержкой:
    - TTL (время жизни)
    - LRU eviction
    - Тегирование для группового удаления
    - Статистика
    - Thread-safe операции
    """
    
    def __init__(
        self, 
        max_size: int = 10000,
        default_ttl: int = 3600,
        max_memory_mb: int = 512,
        cleanup_interval: int = 300
    ):
        self.max_size = max_size
        self.default_ttl = default_ttl
        self.max_memory_bytes = max_memory_mb * 1024 * 1024
        self.cleanup_interval = cleanup_interval
        
        # Основное хранилище
        self._cache: OrderedDict[str, CacheEntry] = OrderedDict()
        self._lock = asyncio.Lock()
        
        # Индексы
        self._tags_index: Dict[str, Set[str]] = defaultdict(set)
        self._expiry_index: Dict[float, Set[str]] = defaultdict(set)
        
        # Статистика
        self._stats = CacheStats()
        
        # Фоновые задачи
        self._cleanup_task: Optional[asyncio.Task] = None
        self._running = False
        
        # Callback для логирования eviction
        self._eviction_callback: Optional[Callable] = None
    
    async def start(self):
        """Запуск кеша."""
        if self._running:
            return
        
        self._running = True
        self._cleanup_task = asyncio.create_task(self._cleanup_loop())
        logger.info(f"MemoryCache started: max_size={self.max_size}, max_memory={self.max_memory_bytes//1024//1024}MB")
    
    async def stop(self):
        """Остановка кеша."""
        self._running = False
        if self._cleanup_task:
            self._cleanup_task.cancel()
            try:
                await self._cleanup_task
            except asyncio.CancelledError:
                pass
        logger.info("MemoryCache stopped")
    
    async def get(self, key: str, default: Any = None) -> Any:
        """Получение значения из кеша."""
        async with self._lock:
            entry = self._cache.get(key)
            
            if entry is None:
                self._stats.misses += 1
                return default
            
            # Проверяем TTL
            current_time = time.time()
            if entry.expires_at and current_time > entry.expires_at:
                await self._remove_entry(key, entry)
                self._stats.misses += 1
                return default
            
            # Обновляем статистику доступа
            entry.access_count += 1
            entry.last_accessed = current_time
            
            # Перемещаем в конец (LRU)
            self._cache.move_to_end(key)
            
            self._stats.hits += 1
            return entry.value
    
    async def set(
        self, 
        key: str, 
        value: Any, 
        ttl: Optional[int] = None,
        tags: Optional[List[str]] = None
    ) -> bool:
        """Установка значения в кеш."""
        async with self._lock:
            current_time = time.time()
            
            # Вычисляем размер
            try:
                size_bytes = len(pickle.dumps(value))
            except Exception:
                size_bytes = len(str(value).encode('utf-8'))
            
            # Проверяем лимит памяти для одного объекта
            if size_bytes > self.max_memory_bytes // 10:  # Максимум 10% от общего лимита
                logger.warning(f"Object too large for cache: {size_bytes} bytes")
                return False
            
            # Вычисляем время истечения
            expires_at = None
            if ttl is not None:
                expires_at = current_time + ttl
            elif self.default_ttl > 0:
                expires_at = current_time + self.default_ttl
            
            # Удаляем старую запись если есть
            if key in self._cache:
                await self._remove_entry(key, self._cache[key])
            
            # Создаем новую запись
            entry = CacheEntry(
                value=value,
                created_at=current_time,
                expires_at=expires_at,
                size_bytes=size_bytes,
                tags=set(tags or [])
            )
            
            # Освобождаем место если нужно
            await self._ensure_space(size_bytes)
            
            # Добавляем в кеш
            self._cache[key] = entry
            
            # Обновляем индексы
            if expires_at:
                self._expiry_index[expires_at].add(key)
            
            for tag in entry.tags:
                self._tags_index[tag].add(key)
            
            # Обновляем статистику
            self._stats.sets += 1
            self._stats.memory_usage += size_bytes
            self._stats.total_entries = len(self._cache)
            
            return True
    
    async def delete(self, key: str) -> bool:
        """Удаление ключа из кеша."""
        async with self._lock:
            entry = self._cache.get(key)
            if entry is None:
                return False
            
            await self._remove_entry(key, entry)
            self._stats.deletes += 1
            return True
    
    async def delete_by_tags(self, tags: List[str]) -> int:
        """Удаление всех записей с указанными тегами."""
        async with self._lock:
            keys_to_delete = set()
            
            for tag in tags:
                keys_to_delete.update(self._tags_index.get(tag, set()))
            
            deleted_count = 0
            for key in keys_to_delete:
                if key in self._cache:
                    await self._remove_entry(key, self._cache[key])
                    deleted_count += 1
            
            self._stats.deletes += deleted_count
            return deleted_count
    
    async def exists(self, key: str) -> bool:
        """Проверка существования ключа."""
        return await self.get(key) is not None
    
    async def clear(self):
        """Очистка всего кеша."""
        async with self._lock:
            self._cache.clear()
            self._tags_index.clear()
            self._expiry_index.clear()
            self._stats.memory_usage = 0
            self._stats.total_entries = 0
    
    async def _ensure_space(self, required_bytes: int):
        """Освобождение места в кеше."""
        # Проверяем лимит по количеству
        while len(self._cache) >= self.max_size:
            await self._evict_lru()
        
        # Проверяем лимит по памяти
        while (self._stats.memory_usage + required_bytes) > self.max_memory_bytes:
            if not await self._evict_lru():
                break  # Нет больше записей для удаления
    
    async def _evict_lru(self) -> bool:
        """Удаление наименее используемой записи."""
        if not self._cache:
            return False
        
        # Получаем самую старую запись (первую в OrderedDict)
        key, entry = next(iter(self._cache.items()))
        await self._remove_entry(key, entry)
        self._stats.evictions += 1
        
        if self._eviction_callback:
            try:
                await self._eviction_callback(key, entry.value)
            except Exception as e:
                logger.error(f"Eviction callback failed: {e}")
        
        return True
    
    async def _remove_entry(self, key: str, entry: CacheEntry):
        """Удаление записи и обновление индексов."""
        # Удаляем из основного хранилища
        if key in self._cache:
            del self._cache[key]
        
        # Удаляем из индекса тегов
        for tag in entry.tags:
            self._tags_index[tag].discard(key)
            if not self._tags_index[tag]:
                del self._tags_index[tag]
        
        # Удаляем из индекса истечения
        if entry.expires_at:
            self._expiry_index[entry.expires_at].discard(key)
            if not self._expiry_index[entry.expires_at]:
                del self._expiry_index[entry.expires_at]
        
        # Обновляем статистику
        self._stats.memory_usage -= entry.size_bytes
        self._stats.total_entries = len(self._cache)
    
    async def _cleanup_loop(self):
        """Фоновая очистка истекших записей."""
        while self._running:
            try:
                await asyncio.sleep(self.cleanup_interval)
                await self._cleanup_expired()
            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error(f"Error in cache cleanup: {e}")
    
    async def _cleanup_expired(self):
        """Удаление истекших записей."""
        async with self._lock:
            current_time = time.time()
            expired_keys = []
            
            # Находим истекшие записи
            for key, entry in self._cache.items():
                if entry.expires_at and current_time > entry.expires_at:
                    expired_keys.append(key)
            
            # Удаляем истекшие записи
            for key in expired_keys:
                entry = self._cache.get(key)
                if entry:
                    await self._remove_entry(key, entry)
            
            if expired_keys:
                logger.debug(f"Cleaned up {len(expired_keys)} expired cache entries")
    
    def get_stats(self) -> Dict[str, Any]:
        """Получение статистики кеша."""
        hit_rate = 0.0
        total_requests = self._stats.hits + self._stats.misses
        if total_requests > 0:
            hit_rate = (self._stats.hits / total_requests) * 100
        
        return {
            "hits": self._stats.hits,
            "misses": self._stats.misses,
            "hit_rate": round(hit_rate, 2),
            "sets": self._stats.sets,
            "deletes": self._stats.deletes,
            "evictions": self._stats.evictions,
            "total_entries": self._stats.total_entries,
            "memory_usage_mb": round(self._stats.memory_usage / 1024 / 1024, 2),
            "memory_limit_mb": round(self.max_memory_bytes / 1024 / 1024, 2),
            "memory_usage_percent": round(
                (self._stats.memory_usage / self.max_memory_bytes) * 100, 2
            ),
            "tags_count": len(self._tags_index),
            "avg_entry_size": round(
                self._stats.memory_usage / max(1, self._stats.total_entries), 2
            )
        }
    
    def set_eviction_callback(self, callback: Callable):
        """Установка callback для уведомления об eviction."""
        self._eviction_callback = callback


class CacheManager:
    """Менеджер нескольких кешей для разных модулей."""
    
    def __init__(self):
        self._caches: Dict[str, MemoryCache] = {}
        self._default_configs = {
            'users': {'max_size': 5000, 'default_ttl': 7200},  # 2 часа
            'presets': {'max_size': 10000, 'default_ttl': 3600},  # 1 час
            'alerts': {'max_size': 20000, 'default_ttl': 1800},  # 30 минут
            'prices': {'max_size': 1000, 'default_ttl': 60},  # 1 минута
            'gas': {'max_size': 100, 'default_ttl': 30},  # 30 секунд
            'transactions': {'max_size': 50000, 'default_ttl': 86400},  # 24 часа
        }
    
    def get_cache(self, cache_name: str) -> MemoryCache:
        """Получение кеша по имени."""
        if cache_name not in self._caches:
            config = self._default_configs.get(cache_name, {})
            self._caches[cache_name] = MemoryCache(**config)
        
        return self._caches[cache_name]
    
    async def start_all(self):
        """Запуск всех кешей."""
        for cache in self._caches.values():
            await cache.start()
        logger.info(f"Started {len(self._caches)} caches")
    
    async def stop_all(self):
        """Остановка всех кешей."""
        for cache in self._caches.values():
            await cache.stop()
        logger.info("Stopped all caches")
    
    def get_all_stats(self) -> Dict[str, Dict[str, Any]]:
        """Получение статистики всех кешей."""
        return {name: cache.get_stats() for name, cache in self._caches.items()}


# Глобальный экземпляр менеджера кешей
cache_manager = CacheManager()


# Декораторы для кеширования
def cached(
    cache_name: str = 'default',
    ttl: Optional[int] = None,
    key_prefix: str = '',
    tags: Optional[List[str]] = None
):
    """
    Декоратор для кеширования результатов функций.
    
    Args:
        cache_name: Имя кеша
        ttl: Время жизни в секундах
        key_prefix: Префикс для ключа
        tags: Теги для группового удаления
    """
    def decorator(func: Callable):
        async def wrapper(*args, **kwargs):
            cache = cache_manager.get_cache(cache_name)
            
            # Генерируем ключ кеша
            key_data = f"{func.__name__}:{args}:{sorted(kwargs.items())}"
            cache_key = f"{key_prefix}:{hashlib.md5(key_data.encode()).hexdigest()}"
            
            # Пытаемся получить из кеша
            result = await cache.get(cache_key)
            if result is not None:
                return result
            
            # Выполняем функцию
            if asyncio.iscoroutinefunction(func):
                result = await func(*args, **kwargs)
            else:
                result = func(*args, **kwargs)
            
            # Сохраняем в кеш
            await cache.set(cache_key, result, ttl=ttl, tags=tags)
            
            return result
        
        return wrapper
    return decorator


class DatabaseCacheLayer:
    """Слой кеширования для базы данных."""
    
    def __init__(self, db_manager, cache_name: str = 'database'):
        self.db_manager = db_manager
        self.cache = cache_manager.get_cache(cache_name)
        
    async def get_user(self, user_id: int) -> Optional[Dict[str, Any]]:
        """Получение пользователя с кешированием."""
        cache_key = f"user:{user_id}"
        
        # Проверяем кеш
        cached_user = await self.cache.get(cache_key)
        if cached_user is not None:
            return cached_user
        
        # Запрашиваем из БД
        async with self.db_manager.get_session() as session:
            from shared.database.repositories.user_repository import UserRepository
            repo = UserRepository(session)
            user = await repo.get_by_user_id(user_id)
            
            if user:
                user_data = {
                    'user_id': user.user_id,
                    'username': user.username,
                    'first_name': user.first_name,
                    'is_active': user.is_active,
                    'created_at': user.created_at.isoformat() if user.created_at else None,
                    'language_code': user.language_code,
                    'notification_enabled': user.notification_enabled
                }
                
                # Сохраняем в кеш
                await self.cache.set(cache_key, user_data, tags=['users'])
                return user_data
        
        return None
    
    async def get_user_presets(self, user_id: int) -> List[Dict[str, Any]]:
        """Получение пресетов пользователя с кешированием."""
        cache_key = f"presets:user:{user_id}"
        
        # Проверяем кеш
        cached_presets = await self.cache.get(cache_key)
        if cached_presets is not None:
            return cached_presets
        
        # Запрашиваем из БД
        async with self.db_manager.get_session() as session:
            from shared.database.repositories.preset_repository import PresetRepository
            repo = PresetRepository(session)
            presets = await repo.get_by_user_id(user_id)
            
            presets_data = []
            for preset in presets:
                preset_data = {
                    'preset_id': str(preset.preset_id),
                    'preset_name': preset.preset_name,
                    'pairs': preset.pairs,
                    'interval': preset.interval,
                    'percent': preset.percent,
                    'is_active': preset.is_active,
                    'created_at': preset.created_at.isoformat() if preset.created_at else None
                }
                presets_data.append(preset_data)
            
            # Сохраняем в кеш
            await self.cache.set(cache_key, presets_data, tags=['presets', f'user:{user_id}'])
            return presets_data
    
    async def invalidate_user_cache(self, user_id: int):
        """Инвалидация кеша пользователя."""
        await self.cache.delete_by_tags([f'user:{user_id}'])
    
    async def invalidate_presets_cache(self, user_id: int):
        """Инвалидация кеша пресетов."""
        await self.cache.delete_by_tags(['presets', f'user:{user_id}'])

