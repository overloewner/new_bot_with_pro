# shared/database/repositories/base_repository.py
"""Базовый репозиторий для всех модулей."""

from abc import ABC
from typing import TypeVar, Generic, List, Optional, Any, Dict, Type
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, update, delete, func
from sqlalchemy.exc import SQLAlchemyError
import logging

logger = logging.getLogger(__name__)

T = TypeVar('T')


class BaseRepository(Generic[T], ABC):
    """Базовый репозиторий с общими операциями."""
    
    def __init__(self, session: AsyncSession, model: Type[T]):
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
            logger.error(f"Error getting {self.model.__name__} by id {id_value}: {e}")
            raise
    
    async def get_all(
        self, 
        limit: Optional[int] = None, 
        offset: Optional[int] = None,
        order_by: Optional[str] = None
    ) -> List[T]:
        """Получение всех записей с пагинацией."""
        try:
            query = select(self.model)
            
            if order_by:
                if hasattr(self.model, order_by):
                    query = query.order_by(getattr(self.model, order_by))
            
            if offset:
                query = query.offset(offset)
            if limit:
                query = query.limit(limit)
            
            result = await self.session.execute(query)
            return list(result.scalars().all())
        except SQLAlchemyError as e:
            logger.error(f"Error getting all {self.model.__name__}: {e}")
            raise
    
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
            logger.error(f"Error creating {self.model.__name__}: {e}")
            raise
    
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
            logger.error(f"Error updating {self.model.__name__} by id {id_value}: {e}")
            raise
    
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
            logger.error(f"Error deleting {self.model.__name__} by id {id_value}: {e}")
            raise
    
    async def count(self, **filters) -> int:
        """Подсчет записей с фильтрами."""
        try:
            query = select(func.count(self.model.id))
            
            for key, value in filters.items():
                if hasattr(self.model, key):
                    query = query.where(getattr(self.model, key) == value)
            
            result = await self.session.execute(query)
            return result.scalar()
        except SQLAlchemyError as e:
            logger.error(f"Error counting {self.model.__name__}: {e}")
            raise
    
    async def find_by(self, **kwargs) -> List[T]:
        """Поиск записей по условиям."""
        try:
            query = select(self.model)
            
            for key, value in kwargs.items():
                if hasattr(self.model, key):
                    query = query.where(getattr(self.model, key) == value)
            
            result = await self.session.execute(query)
            return list(result.scalars().all())
        except SQLAlchemyError as e:
            logger.error(f"Error finding {self.model.__name__} by conditions: {e}")
            raise
    
    async def find_one_by(self, **kwargs) -> Optional[T]:
        """Поиск одной записи по условиям."""
        results = await self.find_by(**kwargs)
        return results[0] if results else None
    
    async def exists(self, **kwargs) -> bool:
        """Проверка существования записи."""
        try:
            query = select(func.count(self.model.id))
            
            for key, value in kwargs.items():
                if hasattr(self.model, key):
                    query = query.where(getattr(self.model, key) == value)
            
            result = await self.session.execute(query)
            return result.scalar() > 0
        except SQLAlchemyError as e:
            logger.error(f"Error checking existence in {self.model.__name__}: {e}")
            raise