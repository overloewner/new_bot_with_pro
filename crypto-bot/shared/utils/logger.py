# shared/utils/logger.py
"""Централизованная система логирования для всех модулей."""

import logging
import sys
from typing import Optional, Dict, Any
from datetime import datetime
import json


class ModularFormatter(logging.Formatter):
    """Кастомный форматтер для модульной архитектуры."""
    
    def __init__(self):
        super().__init__()
        
        # Цветовые коды для разных уровней
        self.colors = {
            'DEBUG': '\033[36m',     # Cyan
            'INFO': '\033[32m',      # Green
            'WARNING': '\033[33m',   # Yellow
            'ERROR': '\033[31m',     # Red
            'CRITICAL': '\033[35m',  # Magenta
            'RESET': '\033[0m'       # Reset
        }
    
    def format(self, record):
        """Форматирование записи лога."""
        # Добавляем цвет
        color = self.colors.get(record.levelname, self.colors['RESET'])
        reset = self.colors['RESET']
        
        # Извлекаем модуль из имени логгера
        module_name = self._extract_module_name(record.name)
        
        # Форматируем время
        timestamp = datetime.fromtimestamp(record.created).strftime('%H:%M:%S.%f')[:-3]
        
        # Создаем основное сообщение
        formatted = (
            f"{color}[{timestamp}]{reset} "
            f"{color}[{record.levelname:8}]{reset} "
            f"[{module_name:15}] "
            f"{record.getMessage()}"
        )
        
        # Добавляем exception info если есть
        if record.exc_info:
            formatted += f"\n{self.formatException(record.exc_info)}"
        
        return formatted
    
    def _extract_module_name(self, logger_name: str) -> str:
        """Извлечение имени модуля из имени логгера."""
        parts = logger_name.split('.')
        
        # Ищем модуль в пути
        if 'modules' in parts:
            idx = parts.index('modules')
            if len(parts) > idx + 1:
                return parts[idx + 1]
        
        # Ищем shared компоненты
        if 'shared' in parts:
            return 'shared'
        
        # Возвращаем последнюю часть
        return parts[-1] if parts else 'unknown'


class StructuredLogger:
    """Структурированный логгер для модулей."""
    
    def __init__(self, module_name: str):
        self.module_name = module_name
        self.logger = logging.getLogger(f"modules.{module_name}")
    
    def info(self, message: str, **kwargs):
        """Информационное сообщение."""
        self._log('INFO', message, **kwargs)
    
    def debug(self, message: str, **kwargs):
        """Отладочное сообщение."""
        self._log('DEBUG', message, **kwargs)
    
    def warning(self, message: str, **kwargs):
        """Предупреждение."""
        self._log('WARNING', message, **kwargs)
    
    def error(self, message: str, **kwargs):
        """Ошибка."""
        self._log('ERROR', message, **kwargs)
    
    def critical(self, message: str, **kwargs):
        """Критическая ошибка."""
        self._log('CRITICAL', message, **kwargs)
    
    def _log(self, level: str, message: str, **kwargs):
        """Внутренний метод логирования."""
        # ИСПРАВЛЕНО: Убираем конфликтующие поля из extra
        # Не добавляем 'module' в extra, так как это зарезервированное поле
        extra_data = {
            'source_module': self.module_name,  # ИСПРАВЛЕНО: переименовано с 'module'
            'timestamp': datetime.utcnow().isoformat(),
            **{k: v for k, v in kwargs.items() if k not in ['module', 'name', 'msg', 'args']}  # ИСПРАВЛЕНО: фильтруем зарезервированные поля
        }
        
        # Если есть дополнительные данные, добавляем их к сообщению
        if kwargs:
            filtered_kwargs = {k: v for k, v in kwargs.items() if k not in ['module', 'name', 'msg', 'args']}
            if filtered_kwargs:
                message += f" | {json.dumps(filtered_kwargs, default=str)}"
        
        getattr(self.logger, level.lower())(message, extra=extra_data)


def setup_logging(level: str = "INFO") -> None:
    """Настройка логирования для всего приложения."""
    
    # Очищаем существующие обработчики
    logging.root.handlers.clear()
    
    # Создаем обработчик для консоли
    console_handler = logging.StreamHandler(sys.stdout)
    console_handler.setFormatter(ModularFormatter())
    
    # Настраиваем корневой логгер
    logging.root.setLevel(getattr(logging, level.upper()))
    logging.root.addHandler(console_handler)
    
    # Настраиваем уровни для сторонних библиотек
    logging.getLogger('aiohttp').setLevel(logging.WARNING)
    logging.getLogger('aiogram').setLevel(logging.INFO)
    logging.getLogger('sqlalchemy').setLevel(logging.WARNING)
    
    # Логируем успешную инициализацию
    logger = logging.getLogger('shared.logger')
    logger.info("✅ Logging system initialized")


def get_module_logger(module_name: str) -> StructuredLogger:
    """Получение логгера для модуля."""
    return StructuredLogger(module_name)