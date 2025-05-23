"""Репозиторий для работы с пресетами."""

from typing import List, Optional, Dict, Any
from uuid import UUID
import json
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, update, delete
from sqlalchemy.exc import SQLAlchemyError

from bot.db.models import Preset
from bot.db.repositories.base import BaseRepository
from bot.core.exceptions import DatabaseError


class PresetRepository(BaseRepository[Preset]):
    """Репозиторий для работы с пресетами."""
    
    def __init__(self, session: AsyncSession):
        super().__init__(session, Preset)
    
    async def get_by_preset_id(self, preset_id: str) -> Optional[Preset]:
        """Получение пресета по preset_id."""
        try:
            result = await self.session.execute(
                select(Preset).where(Preset.preset_id == UUID(preset_id))
            )
            return result.scalar_one_or_none()
        except SQLAlchemyError as e:
            raise DatabaseError(f"Error getting preset by preset_id {preset_id}: {e}")
    
    async def get_by_user_id(self, user_id: int) -> List[Preset]:
        """Получение всех пресетов пользователя."""
        try:
            result = await self.session.execute(
                select(Preset).where(Preset.user_id == user_id)
            )
            return list(result.scalars().all())
        except SQLAlchemyError as e:
            raise DatabaseError(f"Error getting presets for user {user_id}: {e}")
    
    async def get_active_by_user_id(self, user_id: int) -> List[Preset]:
        """Получение активных пресетов пользователя."""
        try:
            result = await self.session.execute(
                select(Preset).where(
                    Preset.user_id == user_id,
                    Preset.is_active == True
                )
            )
            return list(result.scalars().all())
        except SQLAlchemyError as e:
            raise DatabaseError(f"Error getting active presets for user {user_id}: {e}")
    
    async def create_preset(self, user_id: int, preset_data: Dict[str, Any]) -> Preset:
        """Создание нового пресета."""
        try:
            preset = Preset(
                user_id=user_id,
                preset_name=preset_data["preset_name"],
                pairs=json.dumps(preset_data["pairs"]),
                interval=preset_data["interval"],
                percent=preset_data["percent"],
                is_active=preset_data.get("is_active", False)
            )
            self.session.add(preset)
            await self.session.commit()
            await self.session.refresh(preset)
            return preset
        except SQLAlchemyError as e:
            await self.session.rollback()
            raise DatabaseError(f"Error creating preset for user {user_id}: {e}")
    
    async def update_active_status(self, preset_id: str, is_active: bool) -> bool:
        """Обновление статуса активности пресета."""
        try:
            result = await self.session.execute(
                update(Preset)
                .where(Preset.preset_id == UUID(preset_id))
                .values(is_active=is_active)
            )
            await self.session.commit()
            return result.rowcount > 0
        except SQLAlchemyError as e:
            await self.session.rollback()
            raise DatabaseError(f"Error updating preset {preset_id} status: {e}")
    
    async def delete_preset(self, preset_id: str) -> bool:
        """Удаление пресета."""
        try:
            result = await self.session.execute(
                delete(Preset).where(Preset.preset_id == UUID(preset_id))
            )
            await self.session.commit()
            return result.rowcount > 0
        except SQLAlchemyError as e:
            await self.session.rollback()
            raise DatabaseError(f"Error deleting preset {preset_id}: {e}")
    
    async def get_all_presets_data(self) -> Dict[int, Dict[str, Any]]:
        """Получение данных всех пресетов для инициализации."""
        try:
            presets = await self.get_all()
            presets_data = {}
            
            for preset in presets:
                if preset.user_id not in presets_data:
                    presets_data[preset.user_id] = {
                        "presets": {},
                        "active_presets": set()
                    }
                
                preset_id_str = str(preset.preset_id)
                presets_data[preset.user_id]["presets"][preset_id_str] = {
                    "preset_name": preset.preset_name,
                    "pairs": json.loads(preset.pairs),
                    "interval": preset.interval,
                    "percent": preset.percent
                }
                
                if preset.is_active:
                    presets_data[preset.user_id]["active_presets"].add(preset_id_str)
            
            return presets_data
        except SQLAlchemyError as e:
            raise DatabaseError(f"Error loading all presets data: {e}")