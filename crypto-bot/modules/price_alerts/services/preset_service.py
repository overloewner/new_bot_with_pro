"""Сервис для работы с пресетами."""

from typing import Dict, Any, List, Set
import uuid
from bot.db.repositories.preset_repository import PresetRepository
from bot.core.exceptions import PresetNotFoundError, DatabaseError, ValidationError
from bot.core.logger import get_logger

logger = get_logger(__name__)


class PresetService:
    """Сервис для управления пресетами."""
    
    def __init__(self, preset_repository: PresetRepository):
        self.preset_repository = preset_repository
    
    async def create_preset(self, user_id: int, preset_data: Dict[str, Any]) -> str:
        """Создание нового пресета."""
        try:
            self._validate_preset_data(preset_data)
            
            preset = await self.preset_repository.create_preset(user_id, preset_data)
            preset_id = str(preset.preset_id)
            
            logger.info(f"Created preset {preset_id} for user {user_id}")
            return preset_id
        except ValidationError:
            raise
        except DatabaseError:
            logger.error(f"Database error creating preset for user {user_id}")
            raise
        except Exception as e:
            logger.error(f"Unexpected error creating preset for user {user_id}: {e}")
            raise DatabaseError(f"Failed to create preset: {e}")
    
    async def get_user_presets(self, user_id: int) -> Dict[str, Dict[str, Any]]:
        """Получение всех пресетов пользователя."""
        try:
            presets = await self.preset_repository.get_by_user_id(user_id)
            
            result = {}
            for preset in presets:
                import json
                result[str(preset.preset_id)] = {
                    "preset_name": preset.preset_name,
                    "pairs": json.loads(preset.pairs),
                    "interval": preset.interval,
                    "percent": preset.percent,
                    "is_active": preset.is_active
                }
            
            return result
        except DatabaseError:
            logger.error(f"Database error getting presets for user {user_id}")
            raise
        except Exception as e:
            logger.error(f"Unexpected error getting presets for user {user_id}: {e}")
            raise DatabaseError(f"Failed to get user presets: {e}")
    
    async def get_active_presets(self, user_id: int) -> Set[str]:
        """Получение ID активных пресетов пользователя."""
        try:
            presets = await self.preset_repository.get_active_by_user_id(user_id)
            return {str(preset.preset_id) for preset in presets}
        except DatabaseError:
            logger.error(f"Database error getting active presets for user {user_id}")
            raise
        except Exception as e:
            logger.error(f"Unexpected error getting active presets for user {user_id}: {e}")
            raise DatabaseError(f"Failed to get active presets: {e}")
    
    async def activate_preset(self, user_id: int, preset_id: str) -> bool:
        """Активация пресета."""
        try:
            preset = await self.preset_repository.get_by_preset_id(preset_id)
            if not preset or preset.user_id != user_id:
                raise PresetNotFoundError(f"Preset {preset_id} not found for user {user_id}")
            
            success = await self.preset_repository.update_active_status(preset_id, True)
            if success:
                logger.info(f"Activated preset {preset_id} for user {user_id}")
            return success
        except PresetNotFoundError:
            raise
        except DatabaseError:
            logger.error(f"Database error activating preset {preset_id}")
            raise
        except Exception as e:
            logger.error(f"Unexpected error activating preset {preset_id}: {e}")
            raise DatabaseError(f"Failed to activate preset: {e}")
    
    async def deactivate_preset(self, user_id: int, preset_id: str) -> bool:
        """Деактивация пресета."""
        try:
            preset = await self.preset_repository.get_by_preset_id(preset_id)
            if not preset or preset.user_id != user_id:
                raise PresetNotFoundError(f"Preset {preset_id} not found for user {user_id}")
            
            success = await self.preset_repository.update_active_status(preset_id, False)
            if success:
                logger.info(f"Deactivated preset {preset_id} for user {user_id}")
            return success
        except PresetNotFoundError:
            raise
        except DatabaseError:
            logger.error(f"Database error deactivating preset {preset_id}")
            raise
        except Exception as e:
            logger.error(f"Unexpected error deactivating preset {preset_id}: {e}")
            raise DatabaseError(f"Failed to deactivate preset: {e}")
    
    async def delete_preset(self, user_id: int, preset_id: str) -> bool:
        """Удаление пресета."""
        try:
            preset = await self.preset_repository.get_by_preset_id(preset_id)
            if not preset or preset.user_id != user_id:
                raise PresetNotFoundError(f"Preset {preset_id} not found for user {user_id}")
            
            success = await self.preset_repository.delete_preset(preset_id)
            if success:
                logger.info(f"Deleted preset {preset_id} for user {user_id}")
            return success
        except PresetNotFoundError:
            raise
        except DatabaseError:
            logger.error(f"Database error deleting preset {preset_id}")
            raise
        except Exception as e:
            logger.error(f"Unexpected error deleting preset {preset_id}: {e}")
            raise DatabaseError(f"Failed to delete preset: {e}")
    
    async def get_preset_details(self, user_id: int, preset_id: str) -> Dict[str, Any]:
        """Получение деталей пресета."""
        try:
            preset = await self.preset_repository.get_by_preset_id(preset_id)
            if not preset or preset.user_id != user_id:
                raise PresetNotFoundError(f"Preset {preset_id} not found for user {user_id}")
            
            import json
            return {
                "preset_name": preset.preset_name,
                "pairs": json.loads(preset.pairs),
                "interval": preset.interval,
                "percent": preset.percent,
                "is_active": preset.is_active
            }
        except PresetNotFoundError:
            raise
        except DatabaseError:
            logger.error(f"Database error getting preset {preset_id} details")
            raise
        except Exception as e:
            logger.error(f"Unexpected error getting preset {preset_id} details: {e}")
            raise DatabaseError(f"Failed to get preset details: {e}")
    
    async def get_all_presets_data(self) -> Dict[int, Dict[str, Any]]:
        """Получение данных всех пресетов."""
        try:
            return await self.preset_repository.get_all_presets_data()
        except DatabaseError:
            logger.error("Database error getting all presets data")
            raise
        except Exception as e:
            logger.error(f"Unexpected error getting all presets data: {e}")
            raise DatabaseError(f"Failed to get all presets data: {e}")
    
    def _validate_preset_data(self, preset_data: Dict[str, Any]) -> None:
        """Валидация данных пресета."""
        required_fields = ["preset_name", "pairs", "interval", "percent"]
        
        for field in required_fields:
            if field not in preset_data:
                raise ValidationError(f"Missing required field: {field}")
        
        if not isinstance(preset_data["pairs"], list) or len(preset_data["pairs"]) == 0:
            raise ValidationError("Pairs must be a non-empty list")
        
        if not isinstance(preset_data["percent"], (int, float)) or preset_data["percent"] <= 0:
            raise ValidationError("Percent must be a positive number")
        
        if not preset_data["preset_name"].strip():
            raise ValidationError("Preset name cannot be empty")