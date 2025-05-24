# modules/price_alerts/core/preset_manager.py
"""Менеджер пресетов с кешированием и оптимизацией."""

import asyncio
import time
import uuid
from typing import Dict, Any, Set, List, Optional
from collections import defaultdict

from shared.utils.logger import get_module_logger
from shared.database.manager import DatabaseManager

logger = get_module_logger("preset_manager")


class PresetManager:
    """Менеджер пресетов с кешированием."""
    
    def __init__(self, db_manager: Optional[DatabaseManager] = None):
        self.db_manager = db_manager
        
        # Кеш пресетов в памяти для быстрого доступа
        self._user_presets: Dict[int, Dict[str, Dict[str, Any]]] = defaultdict(dict)
        self._active_presets: Dict[int, Set[str]] = defaultdict(set)
        self._user_monitoring: Dict[int, bool] = defaultdict(bool)
        
        # Индексы для быстрого поиска
        self._symbol_index: Dict[str, Set[str]] = defaultdict(set)  # symbol -> preset_ids
        self._interval_index: Dict[str, Set[str]] = defaultdict(set)  # interval -> preset_ids
        
        # Статистика
        self._stats = {
            'total_presets': 0,
            'active_presets': 0,
            'monitoring_users': 0
        }
    
    async def initialize(self):
        """Инициализация менеджера."""
        try:
            if self.db_manager:
                await self._load_from_database()
            else:
                # Создаем тестовые данные
                await self._create_test_presets()
            
            self._rebuild_indexes()
            logger.info(f"Preset manager initialized with {self._stats['total_presets']} presets")
            
        except Exception as e:
            logger.error(f"Error initializing preset manager: {e}")
            raise
    
    async def create_preset(self, user_id: int, preset_data: Dict[str, Any]) -> Optional[str]:
        """Создание нового пресета."""
        try:
            # Валидация данных
            if not self._validate_preset_data(preset_data):
                return None
            
            # Генерируем уникальный ID
            preset_id = str(uuid.uuid4())
            
            # Подготавливаем данные пресета
            preset = {
                'preset_id': preset_id,
                'user_id': user_id,
                'preset_name': preset_data['preset_name'],
                'pairs': preset_data['pairs'],
                'interval': preset_data['interval'],
                'percent': preset_data['percent'],
                'is_active': False,
                'created_at': time.time(),
                'check_correlation': preset_data.get('check_correlation', False)
            }
            
            # Сохраняем в кеш
            self._user_presets[user_id][preset_id] = preset
            
            # Сохраняем в БД если доступна
            if self.db_manager:
                await self._save_preset_to_db(preset)
            
            self._update_stats()
            logger.info(f"Created preset {preset_id} for user {user_id}")
            
            return preset_id
            
        except Exception as e:
            logger.error(f"Error creating preset: {e}")
            return None
    
    async def activate_preset(self, user_id: int, preset_id: str) -> bool:
        """Активация пресета."""
        try:
            if preset_id not in self._user_presets[user_id]:
                return False
            
            # Активируем пресет
            self._user_presets[user_id][preset_id]['is_active'] = True
            self._active_presets[user_id].add(preset_id)
            
            # Обновляем индексы
            preset = self._user_presets[user_id][preset_id]
            self._add_to_indexes(preset_id, preset)
            
            # Обновляем в БД
            if self.db_manager:
                await self._update_preset_in_db(preset_id, {'is_active': True})
            
            self._update_stats()
            logger.info(f"Activated preset {preset_id} for user {user_id}")
            
            return True
            
        except Exception as e:
            logger.error(f"Error activating preset: {e}")
            return False
    
    async def deactivate_preset(self, user_id: int, preset_id: str) -> bool:
        """Деактивация пресета."""
        try:
            if preset_id not in self._user_presets[user_id]:
                return False
            
            # Деактивируем пресет
            self._user_presets[user_id][preset_id]['is_active'] = False
            self._active_presets[user_id].discard(preset_id)
            
            # Удаляем из индексов
            preset = self._user_presets[user_id][preset_id]
            self._remove_from_indexes(preset_id, preset)
            
            # Обновляем в БД
            if self.db_manager:
                await self._update_preset_in_db(preset_id, {'is_active': False})
            
            self._update_stats()
            logger.info(f"Deactivated preset {preset_id} for user {user_id}")
            
            return True
            
        except Exception as e:
            logger.error(f"Error deactivating preset: {e}")
            return False
    
    async def get_user_presets(self, user_id: int) -> Dict[str, Dict[str, Any]]:
        """Получение всех пресетов пользователя."""
        return self._user_presets[user_id].copy()
    
    async def set_user_monitoring(self, user_id: int, monitoring: bool):
        """Установка статуса мониторинга для пользователя."""
        self._user_monitoring[user_id] = monitoring
        self._update_stats()
    
    async def get_required_streams(self) -> List[str]:
        """Получение списка необходимых WebSocket стримов."""
        streams = set()
        
        for user_id, monitoring in self._user_monitoring.items():
            if not monitoring:
                continue
            
            for preset_id in self._active_presets[user_id]:
                if preset_id in self._user_presets[user_id]:
                    preset = self._user_presets[user_id][preset_id]
                    interval = preset['interval']
                    
                    for pair in preset['pairs']:
                        stream = f"{pair.lower()}@kline_{interval}"
                        streams.add(stream)
        
        return list(streams)
    
    async def get_active_presets_cache(self) -> Dict[str, Dict[str, Any]]:
        """Получение кеша активных пресетов для быстрого доступа."""
        cache = {}
        
        for user_id, monitoring in self._user_monitoring.items():
            if not monitoring:
                continue
            
            for preset_id in self._active_presets[user_id]:
                if preset_id in self._user_presets[user_id]:
                    preset = self._user_presets[user_id][preset_id].copy()
                    preset['user_id'] = user_id
                    cache[preset_id] = preset
        
        return cache
    
    def _validate_preset_data(self, data: Dict[str, Any]) -> bool:
        """Валидация данных пресета."""
        required_fields = ['preset_name', 'pairs', 'interval', 'percent']
        
        for field in required_fields:
            if field not in data:
                logger.warning(f"Missing field: {field}")
                return False
        
        if not isinstance(data['pairs'], list) or not data['pairs']:
            logger.warning("Invalid pairs")
            return False
        
        if not isinstance(data['percent'], (int, float)) or data['percent'] <= 0:
            logger.warning("Invalid percent")
            return False
        
        return True
    
    def _rebuild_indexes(self):
        """Перестроение индексов."""
        self._symbol_index.clear()
        self._interval_index.clear()
        
        for user_id, presets in self._user_presets.items():
            for preset_id, preset in presets.items():
                if preset.get('is_active', False):
                    self._add_to_indexes(preset_id, preset)
    
    def _add_to_indexes(self, preset_id: str, preset: Dict[str, Any]):
        """Добавление пресета в индексы."""
        # Индекс по символам
        for pair in preset.get('pairs', []):
            self._symbol_index[pair].add(preset_id)
        
        # Индекс по интервалам
        interval = preset.get('interval')
        if interval:
            self._interval_index[interval].add(preset_id)
    
    def _remove_from_indexes(self, preset_id: str, preset: Dict[str, Any]):
        """Удаление пресета из индексов."""
        # Удаляем из индекса символов
        for pair in preset.get('pairs', []):
            self._symbol_index[pair].discard(preset_id)
        
        # Удаляем из индекса интервалов
        interval = preset.get('interval')
        if interval:
            self._interval_index[interval].discard(preset_id)
    
    def _update_stats(self):
        """Обновление статистики."""
        total_presets = sum(len(presets) for presets in self._user_presets.values())
        active_presets = sum(len(presets) for presets in self._active_presets.values())
        monitoring_users = sum(1 for monitoring in self._user_monitoring.values() if monitoring)
        
        self._stats.update({
            'total_presets': total_presets,
            'active_presets': active_presets,
            'monitoring_users': monitoring_users
        })
    
    async def _create_test_presets(self):
        """Создание тестовых пресетов."""
        test_user_id = 123456789
        
        test_presets = [
            {
                'preset_name': 'Топ криптовалюты 1%',
                'pairs': ['BTCUSDT', 'ETHUSDT', 'BNBUSDT'],
                'interval': '1m',
                'percent': 1.0,
                'check_correlation': False
            },
            {
                'preset_name': 'Альткоины 2%',
                'pairs': ['ADAUSDT', 'SOLUSDT', 'XRPUSDT'],
                'interval': '5m',
                'percent': 2.0,
                'check_correlation': True
            }
        ]
        
        for preset_data in test_presets:
            preset_id = await self.create_preset(test_user_id, preset_data)
            if preset_id:
                await self.activate_preset(test_user_id, preset_id)
        
        # Включаем мониторинг для тестового пользователя
        await self.set_user_monitoring(test_user_id, True)
    
    async def _load_from_database(self):
        """Загрузка пресетов из базы данных."""
        # TODO: Реализовать загрузку из БД когда будет готова
        pass
    
    async def _save_preset_to_db(self, preset: Dict[str, Any]):
        """Сохранение пресета в БД."""
        # TODO: Реализовать сохранение в БД когда будет готова
        pass
    
    async def _update_preset_in_db(self, preset_id: str, updates: Dict[str, Any]):
        """Обновление пресета в БД."""
        # TODO: Реализовать обновление в БД когда будет готова
        pass
    
    def get_stats(self) -> Dict[str, Any]:
        """Получение статистики."""
        return self._stats.copy()