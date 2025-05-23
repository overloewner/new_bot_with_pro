"""Рефакторинг хранилища с улучшенной архитектурой."""

from typing import Dict, Any, Set
from aiogram.fsm.state import State, StatesGroup

from bot.services.user_service import UserService
from bot.services.preset_service import PresetService
from bot.services.token_service import TokenService
from bot.db.database import DatabaseManager
from bot.core.logger import get_logger

logger = get_logger(__name__)


class PresetStates(StatesGroup):
    """Состояния для создания пресетов."""
    waiting_preset_name = State()
    waiting_pairs = State()
    waiting_volume_input = State()
    waiting_interval = State()
    waiting_percent = State()


class Storage:
    """Основное хранилище с делегированием к сервисам."""
    
    def __init__(
        self, 
        db_manager: DatabaseManager,
        token_service: TokenService
    ):
        self.db_manager = db_manager
        self.token_service = token_service
        
        # Кеш данных пользователей
        self._users_data: Dict[int, Dict[str, Any]] = {}
        
        # Индексы подписок
        self._subscriptions_stream: Dict[str, Dict[int, Set[str]]] = {}
        self._subscriptions_user: Dict[int, Dict[str, Set[str]]] = {}
    
    async def initialize(self) -> None:
        """Инициализация хранилища."""
        try:
            # Инициализируем сервис токенов
            await self.token_service.initialize()
            
            # Загружаем данные пользователей и пресетов
            await self._load_all_data()
            
            # Восстанавливаем подписки
            await self._restore_user_subscriptions()
            
            logger.info(f"Storage initialized with {len(self._users_data)} users")
            
        except Exception as e:
            logger.error(f"Failed to initialize storage: {e}")
            raise
    
    async def _load_all_data(self) -> None:
        """Загрузка всех данных из БД."""
        async with self.db_manager.get_session() as session:
            from bot.db.repositories.user_repository import UserRepository
            from bot.db.repositories.preset_repository import PresetRepository
            
            user_repo = UserRepository(session)
            preset_repo = PresetRepository(session)
            
            # Загружаем пользователей
            users_data = await user_repo.get_all_users_data()
            
            # Загружаем пресеты
            presets_data = await preset_repo.get_all_presets_data()
            
            # Объединяем данные
            self._users_data = users_data
            for user_id, preset_info in presets_data.items():
                if user_id in self._users_data:
                    self._users_data[user_id].update(preset_info)
                else:
                    self._users_data[user_id] = {
                        "is_running": False,
                        **preset_info
                    }
    
    async def get_user_data(self, user_id: int) -> Dict[str, Any]:
        """Получение данных пользователя."""
        if user_id not in self._users_data:
            # Создаем пользователя
            async with self.db_manager.get_session() as session:
                from bot.db.repositories.user_repository import UserRepository
                from bot.db.repositories.preset_repository import PresetRepository
                
                user_repo = UserRepository(session)
                preset_repo = PresetRepository(session)
                
                # Проверяем существование пользователя
                user = await user_repo.get_by_user_id(user_id)
                if not user:
                    user = await user_repo.create_user(user_id)
                
                # Загружаем пресеты
                presets = await preset_repo.get_by_user_id(user_id)
                active_presets = await preset_repo.get_active_by_user_id(user_id)
                
                presets_dict = {}
                active_preset_ids = set()
                
                for preset in presets:
                    import json
                    preset_id_str = str(preset.preset_id)
                    presets_dict[preset_id_str] = {
                        "preset_name": preset.preset_name,
                        "pairs": json.loads(preset.pairs),
                        "interval": preset.interval,
                        "percent": preset.percent
                    }
                    if preset.is_active:
                        active_preset_ids.add(preset_id_str)
                
                self._users_data[user_id] = {
                    "is_running": user.is_running,
                    "presets": presets_dict,
                    "active_presets": active_preset_ids
                }
        
        return self._users_data[user_id]
    
    async def update_user_running_status(self, user_id: int, is_running: bool) -> bool:
        """Обновление статуса запуска пользователя."""
        async with self.db_manager.get_session() as session:
            from bot.db.repositories.user_repository import UserRepository
            user_repo = UserRepository(session)
            success = await user_repo.update_running_status(user_id, is_running)
            
            if success and user_id in self._users_data:
                self._users_data[user_id]["is_running"] = is_running
            return success
    
    async def add_preset(self, user_id: int, preset_id: str, preset_data: Dict[str, Any]) -> None:
        """Добавление пресета."""
        async with self.db_manager.get_session() as session:
            from bot.db.repositories.preset_repository import PresetRepository
            preset_repo = PresetRepository(session)
            
            # Создаем пресет в БД
            preset = await preset_repo.create_preset(user_id, preset_data)
            actual_preset_id = str(preset.preset_id)
            
            # Обновляем кеш
            user_data = await self.get_user_data(user_id)
            user_data["presets"][actual_preset_id] = preset_data
            
            logger.info(f"Added preset {actual_preset_id} for user {user_id}")
    
    async def activate_preset(self, user_id: int, preset_id: str) -> bool:
        """Активация пресета."""
        async with self.db_manager.get_session() as session:
            from bot.db.repositories.preset_repository import PresetRepository
            preset_repo = PresetRepository(session)
            
            success = await preset_repo.update_active_status(preset_id, True)
            if success:
                user_data = await self.get_user_data(user_id)
                user_data["active_presets"].add(preset_id)
            return success
    
    async def deactivate_preset(self, user_id: int, preset_id: str) -> bool:
        """Деактивация пресета."""
        async with self.db_manager.get_session() as session:
            from bot.db.repositories.preset_repository import PresetRepository
            preset_repo = PresetRepository(session)
            
            success = await preset_repo.update_active_status(preset_id, False)
            if success:
                user_data = await self.get_user_data(user_id)
                user_data["active_presets"].discard(preset_id)
            return success
    
    async def delete_preset(self, user_id: int, preset_id: str) -> bool:
        """Удаление пресета."""
        async with self.db_manager.get_session() as session:
            from bot.db.repositories.preset_repository import PresetRepository
            preset_repo = PresetRepository(session)
            
            success = await preset_repo.delete_preset(preset_id)
            if success:
                user_data = await self.get_user_data(user_id)
                user_data["presets"].pop(preset_id, None)
                user_data["active_presets"].discard(preset_id)
            return success
    
    # Методы работы с подписками
    async def add_subscription(self, key: str, user_id: int, preset_id: str) -> None:
        """Добавление подписки."""
        # Обновляем индекс по стриму
        if key not in self._subscriptions_stream:
            self._subscriptions_stream[key] = {}
        if user_id not in self._subscriptions_stream[key]:
            self._subscriptions_stream[key][user_id] = set()
        self._subscriptions_stream[key][user_id].add(preset_id)
        
        # Обновляем индекс по пользователю
        if user_id not in self._subscriptions_user:
            self._subscriptions_user[user_id] = {}
        if key not in self._subscriptions_user[user_id]:
            self._subscriptions_user[user_id][key] = set()
        self._subscriptions_user[user_id][key].add(preset_id)
    
    async def remove_user_subscriptions(self, user_id: int) -> int:
        """Удаление всех подписок пользователя."""
        if user_id not in self._subscriptions_user:
            return 0
        
        removed = 0
        
        # Удаляем из индекса стримов
        for key in list(self._subscriptions_user[user_id].keys()):
            if key in self._subscriptions_stream and user_id in self._subscriptions_stream[key]:
                removed += len(self._subscriptions_stream[key][user_id])
                del self._subscriptions_stream[key][user_id]
                if not self._subscriptions_stream[key]:
                    del self._subscriptions_stream[key]
        
        # Удаляем из индекса пользователей
        del self._subscriptions_user[user_id]
        
        logger.info(f"Removed {removed} subscriptions for user {user_id}")
        return removed
    
    async def get_subscriptions_for_stream(self, stream_key: str) -> Dict[int, Set[str]]:
        """Получение подписок для стрима."""
        return {
            k: v.copy() 
            for k, v in self._subscriptions_stream.get(stream_key, {}).items()
        }
    
    async def _restore_user_subscriptions(self) -> int:
        """Восстановление подписок активных пользователей."""
        total_added = 0
        
        for user_id, user_data in self._users_data.items():
            if not user_data.get("is_running", False):
                continue
            
            # Очищаем старые подписки
            await self.remove_user_subscriptions(user_id)
            
            # Добавляем подписки для активных пресетов
            for preset_id in user_data.get("active_presets", set()):
                preset = user_data.get("presets", {}).get(preset_id)
                if not preset:
                    continue
                
                for pair in preset["pairs"]:
                    key = f"{pair.lower()}@kline_{preset['interval']}"
                    await self.add_subscription(key, user_id, preset_id)
                    total_added += 1
        
        logger.info(f"Restored {total_added} subscriptions")
        return total_added
    
    # Делегирование к TokenService
    def get_all_tokens(self):
        """Получение всех токенов."""
        return self.token_service.get_all_tokens()
    
    def get_all_timeframes(self):
        """Получение всех таймфреймов."""
        return self.token_service.get_all_timeframes()
    
    async def is_valid_token(self, token: str) -> bool:
        """Проверка валидности токена."""
        return self.token_service.is_valid_token(token)
    
    async def get_tokens_by_volume(self, min_volume: float):
        """Получение токенов по объему."""
        return await self.token_service.get_tokens_by_volume(min_volume)