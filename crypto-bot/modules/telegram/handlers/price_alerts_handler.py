# modules/telegram/handlers/price_alerts_handler.py
"""Обработчик ценовых алертов для Telegram."""

from aiogram import Router, types, F
from aiogram.fsm.context import FSMContext
from aiogram.utils.keyboard import InlineKeyboardBuilder

from shared.events import event_bus, Event

import logging

logger = logging.getLogger(__name__)


class PriceAlertsHandler:
    """Обработчик команд ценовых алертов."""
    
    def __init__(self):
        self.router = Router()
        
        # Подписываемся на события
        event_bus.subscribe("telegram.show_module", self._handle_show_module)
    
    def register(self, dp):
        """Регистрация обработчиков."""
        # Основные команды ценовых алертов
        self.router.callback_query(F.data == "price_alerts_menu")(self.show_price_alerts_menu)
        self.router.callback_query(F.data == "price_create_preset")(self.create_preset)
        self.router.callback_query(F.data == "price_my_presets")(self.show_my_presets)
        self.router.callback_query(F.data == "price_active_presets")(self.show_active_presets)
        self.router.callback_query(F.data == "price_settings")(self.show_settings)
        
        dp.include_router(self.router)
    
    async def _handle_show_module(self, event: Event):
        """Обработка события показа модуля."""
        if event.data.get("module") == "price_alerts":
            callback = event.data.get("callback")
            if callback:
                await self.show_price_alerts_menu(callback)
    
    async def show_price_alerts_menu(self, callback: types.CallbackQuery):
        """Показ меню ценовых алертов."""
        text = (
            "📈 <b>Price Alerts</b>\n\n"
            
            "Модуль мониторинга цен криптовалют с полным функционалом:\n\n"
            
            "✅ <b>Возможности:</b>\n"
            "• Создание пресетов для множественных пар\n"
            "• Настройка процентного изменения\n"
            "• Выбор таймфреймов (1m, 5m, 15m, 1h, 4h, 1d)\n"
            "• Фильтрация по объему торгов\n"
            "• Реальное время через WebSocket\n\n"
            
            "📊 <b>Ваша статистика:</b>\n"
            "• Активных пресетов: 0\n"
            "• Всего пресетов: 0\n"
            "• Алертов получено: 0"
        )
        
        builder = InlineKeyboardBuilder()
        builder.button(text="➕ Создать пресет", callback_data="price_create_preset")
        builder.button(text="📋 Мои пресеты", callback_data="price_my_presets")
        builder.button(text="🟢 Активные пресеты", callback_data="price_active_presets")
        builder.button(text="⚙️ Настройки", callback_data="price_settings")
        builder.button(text="◀️ Назад", callback_data="main_menu")
        builder.adjust(1)
        
        await callback.message.edit_text(text, reply_markup=builder.as_markup(), parse_mode="HTML")
        await callback.answer()
    
    async def create_preset(self, callback: types.CallbackQuery):
        """Создание нового пресета."""
        text = (
            "➕ <b>Создание пресета</b>\n\n"
            
            "Пресет позволяет настроить мониторинг цен для группы торговых пар.\n\n"
            
            "<b>Шаги создания:</b>\n"
            "1️⃣ Введите название пресета\n"
            "2️⃣ Выберите торговые пары\n"
            "3️⃣ Установите таймфрейм\n"
            "4️⃣ Укажите процент изменения\n\n"
            
            "🚀 <b>Готовы начать?</b>"
        )
        
        builder = InlineKeyboardBuilder()
        builder.button(text="🚀 Начать создание", callback_data="price_start_creation")
        builder.button(text="📖 Подробная инструкция", callback_data="price_creation_help")
        builder.button(text="◀️ Назад", callback_data="price_alerts_menu")
        builder.adjust(1)
        
        await callback.message.edit_text(text, reply_markup=builder.as_markup(), parse_mode="HTML")
        await callback.answer()
    
    async def show_my_presets(self, callback: types.CallbackQuery):
        """Показ всех пресетов пользователя."""
        text = (
            "📋 <b>Мои пресеты</b>\n\n"
            
            "У вас пока нет созданных пресетов.\n\n"
            
            "Создайте первый пресет для начала мониторинга цен!"
        )
        
        builder = InlineKeyboardBuilder()
        builder.button(text="➕ Создать первый пресет", callback_data="price_create_preset")
        builder.button(text="◀️ Назад", callback_data="price_alerts_menu")
        builder.adjust(1)
        
        await callback.message.edit_text(text, reply_markup=builder.as_markup(), parse_mode="HTML")
        await callback.answer()
    
    async def show_active_presets(self, callback: types.CallbackQuery):
        """Показ активных пресетов."""
        text = (
            "🟢 <b>Активные пресеты</b>\n\n"
            
            "У вас нет активных пресетов.\n\n"
            
            "Активируйте пресеты для получения уведомлений о изменениях цен."
        )
        
        builder = InlineKeyboardBuilder()
        builder.button(text="📋 Все пресеты", callback_data="price_my_presets")
        builder.button(text="◀️ Назад", callback_data="price_alerts_menu")
        builder.adjust(1)
        
        await callback.message.edit_text(text, reply_markup=builder.as_markup(), parse_mode="HTML")
        await callback.answer()
    
    async def show_settings(self, callback: types.CallbackQuery):
        """Показ настроек ценовых алертов."""
        text = (
            "⚙️ <b>Настройки Price Alerts</b>\n\n"
            
            "🔔 <b>Уведомления:</b> Включены\n"
            "📊 <b>Группировка алертов:</b> Включена\n"
            "⏱️ <b>Кулдаун:</b> 60 секунд\n"
            "📈 <b>Формат сообщений:</b> Подробный\n\n"
            
            "Дополнительные настройки:"
        )
        
        builder = InlineKeyboardBuilder()
        builder.button(text="🔔 Настройки уведомлений", callback_data="price_notif_settings")
        builder.button(text="📊 Формат сообщений", callback_data="price_format_settings")
        builder.button(text="⏱️ Кулдаун алертов", callback_data="price_cooldown_settings")
        builder.button(text="◀️ Назад", callback_data="price_alerts_menu")
        builder.adjust(1)
        
        await callback.message.edit_text(text, reply_markup=builder.as_markup(), parse_mode="HTML")
        await callback.answer()