# modules/price_alerts/repository.py
"""Репозиторий для работы с пресетами с встроенным кешем."""

import time
import json
from typing import List, Optional, Dict, Any
from uuid import UUID
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, update, delete
from sqlalchemy.exc import SQLAlchemyError

from shared.database.models import PricePreset
from shared.exceptions import DatabaseError
import logging

logger = logging.getLogger(__name__)

class PriceAlertsRepository:
    """Репозиторий для работы с пресетами с встроенным кешем."""
    
    def __init__(self, db_manager=None):
        self.db_manager = db_manager
        
        # Встроенный кеш
        self._presets_cache: Dict[int, Dict[str, Dict[str, Any]]] = {}  # user_id -> preset_id -> preset_data
        self._cache_timestamps: Dict[int, float] = {}  # user_id -> last_update_time
        self._cache_ttl = 300  # 5 минут
        
        # Глобальный кеш активных пресетов для быстрого доступа
        self._active_presets_cache: Dict[str, Dict[str, Any]] = {}  # preset_id -> preset_data
        self._active_cache_timestamp = 0
    
    async def get_user_presets(self, user_id: int) -> List[Dict[str, Any]]:
        """Получение всех пресетов пользователя с кешированием."""
        # Проверяем кеш
        if self._is_cache_valid(user_id):
            cached_presets = self._presets_cache.get(user_id, {})
            return list(cached_presets.values())
        
        # Загружаем из БД если доступна
        if self.db_manager:
            try:
                async with self.db_manager.get_session() as session:
                    result = await session.execute(
                        select(PricePreset).where(PricePreset.user_id == user_id)
                    )
                    presets = result.scalars().all()
                    
                    presets_data = []
                    user_cache = {}
                    
                    for preset in presets:
                        preset_data = {
                            'id': str(preset.preset_id),
                            'preset_id': str(preset.preset_id),
                            'name': preset.preset_name,
                            'symbols': json.loads(preset.pairs) if isinstance(preset.pairs, str) else preset.pairs,
                            'symbols_count': len(json.loads(preset.pairs) if isinstance(preset.pairs, str) else preset.pairs),
                            'interval': preset.interval,
                            'percent_threshold': preset.percent,
                            'is_active': preset.is_active,
                            'created_at': preset.created_at.isoformat() if preset.created_at else None,
                            'alerts_count': preset.alerts_triggered or 0
                        }
                        presets_data.append(preset_data)
                        user_cache[str(preset.preset_id)] = preset_data
                    
                    # Обновляем кеш
                    self._presets_cache[user_id] = user_cache
                    self._cache_timestamps[user_id] = time.time()
                    
                    return presets_data
                    
            except Exception as e:
                logger.error(f"Error loading presets from DB for user {user_id}: {e}")
        
        # Возвращаем из кеша или пустой список
        cached_presets = self._presets_cache.get(user_id, {})
        return list(cached_presets.values())
    
    async def get_active_presets(self, user_id: int) -> List[Dict[str, Any]]:
        """Получение активных пресетов пользователя."""
        all_presets = await self.get_user_presets(user_id)
        return [preset for preset in all_presets if preset.get('is_active', False)]
    
    async def create_preset(self, user_id: int, preset_data: Dict[str, Any]) -> Optional[str]:
        """Создание нового пресета."""
        try:
            preset_id = None
            
            # Сохраняем в БД если доступна
            if self.db_manager:
                try:
                    async with self.db_manager.get_session() as session:
                        preset = PricePreset(
                            user_id=user_id,
                            preset_name=preset_data["preset_name"],
                            pairs=json.dumps(preset_data["symbols"]),
                            interval=preset_data["interval"],
                            percent=preset_data["percent_threshold"],
                            is_active=preset_data.get("is_active", True)
                        )
                        session.add(preset)
                        await session.commit()
                        await session.refresh(preset)
                        preset_id = str(preset.preset_id)
                        
                except Exception as e:
                    logger.error(f"Error saving preset to DB: {e}")
            
            # Если БД недоступна, генерируем ID
            if not preset_id:
                import uuid
                preset_id = str(uuid.uuid4())
            
            # Создаем данные для кеша
            cached_preset_data = {
                'id': preset_id,
                'preset_id': preset_id,
                'name': preset_data["preset_name"],
                'symbols': preset_data["symbols"],
                'symbols_count': len(preset_data["symbols"]),
                'interval': preset_data["interval"],
                'percent_threshold': preset_data["percent_threshold"],
                'is_active': preset_data.get("is_active", True),
                'created_at': time.time(),
                'alerts_count': 0
            }
            
            # Обновляем кеш
            if user_id not in self._presets_cache:
                self._presets_cache[user_id] = {}
            
            self._presets_cache[user_id][preset_id] = cached_preset_data
            self._cache_timestamps[user_id] = time.time()
            
            # Обновляем кеш активных пресетов
            if cached_preset_data['is_active']:
                self._active_presets_cache[preset_id] = {
                    **cached_preset_data,
                    'user_id': user_id
                }
                self._active_cache_timestamp = time.time()
            
            logger.info(f"Created preset {preset_id} for user {user_id}")
            return preset_id
            
        except Exception as e:
            logger.error(f"Error creating preset: {e}")
            return None
    
    async def update_preset_status(self, user_id: int, preset_id: str, is_active: bool) -> bool:
        """Обновление статуса активности пресета."""
        try:
            # Обновляем в БД если доступна
            if self.db_manager:
                try:
                    async with self.db_manager.get_session() as session:
                        result = await session.execute(
                            update(PricePreset)
                            .where(PricePreset.preset_id == UUID(preset_id))
                            .values(is_active=is_active)
                        )
                        await session.commit()
                        
                except Exception as e:
                    logger.error(f"Error updating preset status in DB: {e}")
            
            # Обновляем в кеше
            if user_id in self._presets_cache and preset_id in self._presets_cache[user_id]:
                self._presets_cache[user_id][preset_id]['is_active'] = is_active
                self._cache_timestamps[user_id] = time.time()
                
                # Обновляем кеш активных пресетов
                if is_active:
                    self._active_presets_cache[preset_id] = {
                        **self._presets_cache[user_id][preset_id],
                        'user_id': user_id
                    }
                else:
                    self._active_presets_cache.pop(preset_id, None)
                
                self._active_cache_timestamp = time.time()
                
                logger.info(f"Updated preset {preset_id} status to {is_active}")
                return True
            
        except Exception as e:
            logger.error(f"Error updating preset status: {e}")
        
        return False
    
    async def delete_preset(self, user_id: int, preset_id: str) -> bool:
        """Удаление пресета."""
        try:
            # Удаляем из БД если доступна
            if self.db_manager:
                try:
                    async with self.db_manager.get_session() as session:
                        result = await session.execute(
                            delete(PricePreset).where(PricePreset.preset_id == UUID(preset_id))
                        )
                        await session.commit()
                        
                except Exception as e:
                    logger.error(f"Error deleting preset from DB: {e}")
            
            # Удаляем из кеша
            if user_id in self._presets_cache and preset_id in self._presets_cache[user_id]:
                del self._presets_cache[user_id][preset_id]
                self._cache_timestamps[user_id] = time.time()
                
                # Удаляем из кеша активных пресетов
                self._active_presets_cache.pop(preset_id, None)
                self._active_cache_timestamp = time.time()
                
                logger.info(f"Deleted preset {preset_id}")
                return True
            
        except Exception as e:
            logger.error(f"Error deleting preset: {e}")
        
        return False
    
    async def get_active_presets_cache(self) -> Dict[str, Dict[str, Any]]:
        """Получение кеша активных пресетов для быстрого доступа."""
        # Обновляем кеш если он устарел
        if time.time() - self._active_cache_timestamp > self._cache_ttl:
            await self._rebuild_active_cache()
        
        return self._active_presets_cache.copy()
    
    async def _rebuild_active_cache(self):
        """Перестроение кеша активных пресетов."""
        new_active_cache = {}
        
        for user_id, user_presets in self._presets_cache.items():
            for preset_id, preset_data in user_presets.items():
                if preset_data.get('is_active', False):
                    new_active_cache[preset_id] = {
                        **preset_data,
                        'user_id': user_id
                    }
        
        self._active_presets_cache = new_active_cache
        self._active_cache_timestamp = time.time()
    
    def _is_cache_valid(self, user_id: int) -> bool:
        """Проверка валидности кеша для пользователя."""
        if user_id not in self._cache_timestamps:
            return False
        
        return time.time() - self._cache_timestamps[user_id] < self._cache_ttl
    
    async def invalidate_user_cache(self, user_id: int):
        """Инвалидация кеша пользователя."""
        self._presets_cache.pop(user_id, None)
        self._cache_timestamps.pop(user_id, None)
        await self._rebuild_active_cache()
    
    async def invalidate_all_cache(self):
        """Полная инвалидация кеша."""
        self._presets_cache.clear()
        self._cache_timestamps.clear()
        self._active_presets_cache.clear()
        self._active_cache_timestamp = 0
    
    def get_cache_stats(self) -> Dict[str, Any]:
        """Получение статистики кеша."""
        total_presets = sum(len(presets) for presets in self._presets_cache.values())
        active_presets = len(self._active_presets_cache)
        
        return {
            "cached_users": len(self._presets_cache),
            "total_cached_presets": total_presets,
            "active_presets": active_presets,
            "cache_age_seconds": time.time() - min(self._cache_timestamps.values()) if self._cache_timestamps else 0
        }