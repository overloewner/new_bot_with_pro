"""Основные клавиатуры для Telegram интерфейса."""

from aiogram.utils.keyboard import InlineKeyboardBuilder
from aiogram.types import InlineKeyboardMarkup


class MainKeyboards:
    """Генератор клавиатур для главного интерфейса."""
    
    def get_main_menu_keyboard(self) -> InlineKeyboardMarkup:
        """Клавиатура главного меню."""
        builder = InlineKeyboardBuilder()
        
        # Основные модули
        builder.button(text="📈 Price Alerts", callback_data="price_alerts")
        builder.button(text="⛽ Gas Tracker", callback_data="gas_tracker")
        builder.button(text="🐋 Whale Tracker", callback_data="whale_tracker")
        builder.button(text="👛 Wallet Tracker", callback_data="wallet_tracker")
        
        # Дополнительные опции
        builder.button(text="⚙️ Настройки", callback_data="settings")
        builder.button(text="ℹ️ О боте", callback_data="about")
        
        builder.adjust(2, 2, 2)
        return builder.as_markup()
    
    def get_help_keyboard(self) -> InlineKeyboardMarkup:
        """Клавиатура для справки."""
        builder = InlineKeyboardBuilder()
        builder.button(text="🏠 Главное меню", callback_data="main_menu")
        builder.button(text="📊 Статус модулей", callback_data="cmd_status")
        builder.adjust(1)
        return builder.as_markup()
    
    def get_status_keyboard(self) -> InlineKeyboardMarkup:
        """Клавиатура для статуса."""
        builder = InlineKeyboardBuilder()
        builder.button(text="🔄 Обновить", callback_data="cmd_status")
        builder.button(text="🏠 Главное меню", callback_data="main_menu")
        builder.adjust(1)
        return builder.as_markup()
    
    def get_back_to_main_keyboard(self) -> InlineKeyboardMarkup:
        """Клавиатура возврата в главное меню."""
        builder = InlineKeyboardBuilder()
        builder.button(text="◀️ Назад в главное меню", callback_data="main_menu")
        return builder.as_markup()
