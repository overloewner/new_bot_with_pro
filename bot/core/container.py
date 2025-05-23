"""Dependency Injection контейнер."""

from typing import Dict, Type, TypeVar, Optional, Any
import logging

T = TypeVar('T')

logger = logging.getLogger(__name__)


class Container:
    """Простой DI контейнер для управления зависимостями."""
    
    def __init__(self):
        self._services: Dict[Type, Any] = {}
        self._singletons: Dict[Type, Any] = {}
        self._factories: Dict[Type, callable] = {}
    
    def register_singleton(self, interface: Type[T], instance: T) -> None:
        """Регистрирует singleton экземпляр."""
        self._singletons[interface] = instance
        logger.debug(f"Registered singleton: {interface.__name__}")
    
    def register_factory(self, interface: Type[T], factory: callable) -> None:
        """Регистрирует фабрику для создания экземпляров."""
        self._factories[interface] = factory
        logger.debug(f"Registered factory: {interface.__name__}")
    
    def register_service(self, interface: Type[T], implementation: Type[T]) -> None:
        """Регистрирует реализацию сервиса."""
        self._services[interface] = implementation
        logger.debug(f"Registered service: {interface.__name__} -> {implementation.__name__}")
    
    def resolve(self, interface: Type[T]) -> T:
        """Разрешает зависимость."""
        # Проверяем singleton
        if interface in self._singletons:
            return self._singletons[interface]
        
        # Проверяем фабрику
        if interface in self._factories:
            instance = self._factories[interface]()
            logger.debug(f"Created instance via factory: {interface.__name__}")
            return instance
        
        # Проверяем зарегистрированный сервис
        if interface in self._services:
            implementation = self._services[interface]
            instance = self._create_instance(implementation)
            logger.debug(f"Created instance: {interface.__name__}")
            return instance
        
        # Пытаемся создать напрямую
        try:
            instance = self._create_instance(interface)
            logger.debug(f"Created direct instance: {interface.__name__}")
            return instance
        except Exception as e:
            logger.error(f"Failed to resolve dependency {interface.__name__}: {e}")
            raise DependencyResolutionError(f"Cannot resolve {interface.__name__}") from e
    
    def _create_instance(self, cls: Type[T]) -> T:
        """Создает экземпляр класса с автоматическим разрешением зависимостей."""
        try:
            # Для простоты пока создаем без автоматического разрешения параметров
            # В реальном проекте можно добавить анализ __init__ и автоматическое внедрение
            return cls()
        except TypeError:
            # Если не удается создать без параметров, пробуем передать контейнер
            try:
                return cls(container=self)
            except TypeError:
                raise DependencyResolutionError(f"Cannot create instance of {cls.__name__}")


class DependencyResolutionError(Exception):
    """Исключение при ошибке разрешения зависимости."""
    pass


# Глобальный контейнер для приложения
container = Container()