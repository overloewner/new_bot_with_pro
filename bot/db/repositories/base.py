"""Базовый репозиторий."""

from abc import ABC, abstractmethod
from typing import TypeVar, Generic, List, Optional, Any, Dict
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, update, delete
from sqlalchemy.exc import SQLAlchemyError

from bot.core.exceptions import DatabaseError

T = TypeVar('T')


class BaseRepository(Generic[T], ABC):
    """Базовый репозиторий для работы с БД."""
    
    def __init__(self, session: AsyncSession, model: type):
        self.session = session
        self.model = model
    
    async def get_by_id(self, id_value: Any) -> Optional[T]:
        """Получение записи по ID."""
        try:
            result = await self.session.execute(
                select(self.model).where(self.model.id == id_value)
            )
            return result.scalar_one_or_none()
        except SQLAlchemyError as e:
            raise DatabaseError(f"Error getting {self.model.__name__} by id {id_value}: {e}")
    
    async def get_all(self, limit: Optional[int] = None, offset: Optional[int] = None) -> List[T]:
        """Получение всех записей."""
        try:
            query = select(self.model)
            if offset:
                query = query.offset(offset)
            if limit:
                query = query.limit(limit)
            
            result = await self.session.execute(query)
            return list(result.scalars().all())
        except SQLAlchemyError as e:
            raise DatabaseError(f"Error getting all {self.model.__name__}: {e}")
    
    async def create(self, **kwargs) -> T:
        """Создание новой записи."""
        try:
            instance = self.model(**kwargs)
            self.session.add(instance)
            await self.session.commit()
            await self.session.refresh(instance)
            return instance
        except SQLAlchemyError as e:
            await self.session.rollback()
            raise DatabaseError(f"Error creating {self.model.__name__}: {e}")
    
    async def update_by_id(self, id_value: Any, **kwargs) -> bool:
        """Обновление записи по ID."""
        try:
            result = await self.session.execute(
                update(self.model)
                .where(self.model.id == id_value)
                .values(**kwargs)
            )
            await self.session.commit()
            return result.rowcount > 0
        except SQLAlchemyError as e:
            await self.session.rollback()
            raise DatabaseError(f"Error updating {self.model.__name__} by id {id_value}: {e}")
    
    async def delete_by_id(self, id_value: Any) -> bool:
        """Удаление записи по ID."""
        try:
            result = await self.session.execute(
                delete(self.model).where(self.model.id == id_value)
            )
            await self.session.commit()
            return result.rowcount > 0
        except SQLAlchemyError as e:
            await self.session.rollback()
            raise DatabaseError(f"Error deleting {self.model.__name__} by id {id_value}: {e}")
    
    async def find_by(self, **kwargs) -> List[T]:
        """Поиск записей по условиям."""
        try:
            conditions = [getattr(self.model, key) == value for key, value in kwargs.items()]
            query = select(self.model)
            for condition in conditions:
                query = query.where(condition)
            
            result = await self.session.execute(query)
            return list(result.scalars().all())
        except SQLAlchemyError as e:
            raise DatabaseError(f"Error finding {self.model.__name__} by conditions: {e}")
    
    async def find_one_by(self, **kwargs) -> Optional[T]:
        """Поиск одной записи по условиям."""
        results = await self.find_by(**kwargs)
        return results[0] if results else None