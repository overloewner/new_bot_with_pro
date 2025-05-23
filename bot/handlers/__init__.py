"""Настройка обработчиков."""

from aiogram import Dispatcher
from bot.storage import Storage
from bot.handlers.start_handler import StartHandler
from bot.handlers.preset_handler import PresetHandler
from bot.handlers.config_handler import ConfigHandler


def setup_handlers(dp: Dispatcher, storage: Storage) -> None:
    """Настройка всех обработчиков."""
    
    # Создаем обработчики
    start_handler = StartHandler(storage)
    preset_handler = PresetHandler(storage)
    config_handler = ConfigHandler(storage)
    
    # Регистрируем роутеры
    dp.include_router(start_handler.router)
    dp.include_router(preset_handler.router)
    dp.include_router(config_handler.router)