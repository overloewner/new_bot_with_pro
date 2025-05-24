"""Обновленный менеджер базы данных с улучшенной архитектурой."""

import logging
from contextlib import asynccontextmanager
from typing import AsyncGenerator
from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession, async_sessionmaker
from sqlalchemy.exc import SQLAlchemyError

from bot.database.models import Base
from bot.core.config import DatabaseConfig
from bot.core.exceptions import DatabaseError

logger = logging.getLogger(__name__)


class DatabaseManager:
    """Менеджер базы данных с улучшенным управлением соединениями."""
    
    def __init__(self, config: DatabaseConfig):
        """Инициализация менеджера БД.
        
        Args:
            config: Конфигурация базы данных
        """
        if isinstance(config, str):
            # Обратная совместимость
            config = DatabaseConfig(url=config)
        
        self.config = config
        
        # Подготавливаем URL для asyncpg
        self.db_url = self._prepare_url(config.url)
        
        # Создаем движок
        self.engine = create_async_engine(
            self.db_url,
            pool_size=config.pool_size,
            max_overflow=config.max_overflow,
            pool_pre_ping=config.pool_pre_ping,
            connect_args={
                "server_settings": {
                    "client_encoding": "utf8"
                }
            },
            echo=False  # Установите True для отладки SQL запросов
        )
        
        # Создаем фабрику сессий
        self.async_session = async_sessionmaker(
            bind=self.engine,
            expire_on_commit=False,
            class_=AsyncSession
        )
    
    def _prepare_url(self, url: str) -> str:
        """Подготовка URL для использования с asyncpg."""
        # Убираем параметры из URL
        clean_url = url.split('?')[0]
        
        # Конвертируем postgresql:// в postgresql+asyncpg://
        if clean_url.startswith('postgresql://'):
            return clean_url.replace('postgresql://', 'postgresql+asyncpg://')
        elif clean_url.startswith('postgres://'):
            return clean_url.replace('postgres://', 'postgresql+asyncpg://')
        
        return clean_url
    
    async def initialize(self) -> None:
        """Инициализация базы данных."""
        try:
            async with self.engine.begin() as conn:
                await conn.run_sync(Base.metadata.create_all)
            logger.info("Database initialized successfully")
        except SQLAlchemyError as e:
            logger.error(f"Failed to initialize database: {e}")
            raise DatabaseError(f"Database initialization failed: {e}")
    
    @asynccontextmanager
    async def get_session(self) -> AsyncGenerator[AsyncSession, None]:
        """Контекстный менеджер для получения сессии БД."""
        async with self.async_session() as session:
            try:
                yield session
            except SQLAlchemyError as e:
                await session.rollback()
                logger.error(f"Database session error: {e}")
                raise DatabaseError(f"Database operation failed: {e}")
            finally:
                await session.close()
    
    async def health_check(self) -> bool:
        """Проверка здоровья соединения с БД."""
        try:
            async with self.get_session() as session:
                await session.execute("SELECT 1")
                return True
        except Exception as e:
            logger.error(f"Database health check failed: {e}")
            return False
    
    async def close(self) -> None:
        """Закрытие соединений с базой данных."""
        try:
            await self.engine.dispose()
            logger.info("Database connections closed")
        except Exception as e:
            logger.error(f"Error closing database connections: {e}")
    
    def get_repository_session(self) -> AsyncSession:
        """Получение сессии для репозиториев.
        
        Note: Сессия должна быть закрыта вручную или использована в контексте.
        """
        return self.async_session()
    
    async def execute_raw(self, query: str, params: dict = None) -> any:
        """Выполнение сырого SQL запроса.
        
        Args:
            query: SQL запрос
            params: Параметры запроса
            
        Returns:
            Результат выполнения запроса
        """
        async with self.get_session() as session:
            try:
                result = await session.execute(query, params or {})
                await session.commit()
                return result
            except SQLAlchemyError as e:
                await session.rollback()
                raise DatabaseError(f"Raw query execution failed: {e}")
    
    def get_stats(self) -> dict:
        """Получение статистики пула соединений."""
        pool = self.engine.pool
        return {
            "pool_size": pool.size(),
            "checked_in": pool.checkedin(),
            "checked_out": pool.checkedout(),
            "overflow": pool.overflow(),
            "invalid": pool.invalid()
        }