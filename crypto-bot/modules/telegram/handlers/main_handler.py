# modules/telegram/handlers/main_handler.py
"""Главный обработчик команд."""

from aiogram import Router, types, F
from aiogram.filters import Command
from aiogram.fsm.context import FSMContext
from aiogram.utils.keyboard import InlineKeyboardBuilder

from shared.events import event_bus, Event, USER_COMMAND_RECEIVED
from modules.telegram.keyboards.main_keyboards import MainKeyboards

import logging

logger = logging.getLogger(__name__)


class MainHandler:
    """Главный обработчик команд бота."""
    
    def __init__(self):
        self.router = Router()
        self.keyboards = MainKeyboards()
    
    def register(self, dp):
        """Регистрация обработчиков."""
        # Команды
        self.router.message(Command("start"))(self.cmd_start)
        self.router.message(Command("help"))(self.cmd_help)
        self.router.message(Command("status"))(self.cmd_status)
        
        # Главное меню
        self.router.callback_query(F.data == "main_menu")(self.show_main_menu)
        
        # Модули
        self.router.callback_query(F.data == "price_alerts")(self.show_price_alerts)
        self.router.callback_query(F.data == "gas_tracker")(self.show_gas_tracker)
        self.router.callback_query(F.data == "whale_tracker")(self.show_whale_tracker)
        self.router.callback_query(F.data == "wallet_tracker")(self.show_wallet_tracker)
        
        # Настройки
        self.router.callback_query(F.data == "settings")(self.show_settings)
        self.router.callback_query(F.data == "about")(self.show_about)
        
        dp.include_router(self.router)
    
    async def cmd_start(self, message: types.Message):
        """Команда /start."""
        await event_bus.publish(Event(
            type=USER_COMMAND_RECEIVED,
            data={
                "user_id": message.from_user.id,
                "command": "start",
                "username": message.from_user.username
            },
            source_module="telegram"
        ))
        
        welcome_text = (
            "🤖 <b>Добро пожаловать в Crypto Monitor Bot!</b>\n\n"
            
            "📊 <b>Доступные модули:</b>\n"
            "📈 <b>Price Alerts</b> - Ценовые уведомления\n"
            "⛽ <b>Gas Tracker</b> - Мониторинг газа Ethereum\n"
            "🐋 <b>Whale Tracker</b> - Отслеживание китов (ограниченно)\n"
            "👛 <b>Wallet Tracker</b> - Мониторинг кошельков (ограниченно)\n\n"
            
            "⚠️ <b>Важно:</b> Некоторые функции имеют ограничения из-за использования бесплатных API"
        )
        
        keyboard = self.keyboards.get_main_menu_keyboard()
        await message.answer(welcome_text, reply_markup=keyboard, parse_mode="HTML")
    
    async def cmd_help(self, message: types.Message):
        """Команда /help."""
        help_text = (
            "📖 <b>Справка по боту</b>\n\n"
            
            "<b>Основные команды:</b>\n"
            "/start - Главное меню\n"
            "/help - Эта справка\n"
            "/status - Статус модулей\n\n"
            
            "<b>📈 Price Alerts:</b>\n"
            "• Создание пресетов для отслеживания цен\n"
            "• Уведомления при изменении цены\n"
            "• Поддержка множественных пар\n\n"
            
            "<b>⛽ Gas Tracker:</b>\n"
            "• Мониторинг цены газа Ethereum\n"
            "• Уведомления при достижении порога\n"
            "• Текущие цены и рекомендации\n\n"
            
            "<b>🐋 Whale Tracker (ограниченно):</b>\n"
            "• Отслеживание крупных транзакций\n"
            "• Только ETH переводы >100 ETH\n"
            "• Задержка 1-2 блока\n\n"
            
            "<b>👛 Wallet Tracker (ограниченно):</b>\n"
            "• Мониторинг конкретных кошельков\n"
            "• Проверка каждые 2-5 минут\n"
            "• Только ETH транзакции\n\n"
            
            "❓ <b>Вопросы?</b> Обратитесь к администратору"
        )
        
        keyboard = self.keyboards.get_help_keyboard()
        await message.answer(help_text, reply_markup=keyboard, parse_mode="HTML")
    
    async def cmd_status(self, message: types.Message):
        """Команда /status."""
        # Получаем статус модулей через события
        status_text = (
            "📊 <b>Статус модулей</b>\n\n"
            
            "📈 Price Alerts: 🟢 Активен\n"
            "⛽ Gas Tracker: 🟢 Активен\n"
            "🐋 Whale Tracker: 🟡 Ограниченно\n"
            "👛 Wallet Tracker: 🟡 Ограниченно\n\n"
            
            "🔄 Последнее обновление: сейчас"
        )
        
        keyboard = self.keyboards.get_status_keyboard()
        await message.answer(status_text, reply_markup=keyboard, parse_mode="HTML")
    
    async def show_main_menu(self, callback: types.CallbackQuery):
        """Показ главного меню."""
        text = (
            "🏠 <b>Главное меню</b>\n\n"
            
            "Выберите модуль для настройки:"
        )
        
        keyboard = self.keyboards.get_main_menu_keyboard()
        await callback.message.edit_text(text, reply_markup=keyboard, parse_mode="HTML")
        await callback.answer()
    
    async def show_price_alerts(self, callback: types.CallbackQuery):
        """Переход к модулю ценовых алертов."""
        # Публикуем событие для модуля price_alerts
        await event_bus.publish(Event(
            type="telegram.show_module",
            data={
                "module": "price_alerts",
                "user_id": callback.from_user.id,
                "callback": callback
            },
            source_module="telegram"
        ))
        
        await callback.answer()
    
    async def show_gas_tracker(self, callback: types.CallbackQuery):
        """Переход к модулю газ трекера."""
        # Временная заглушка - показываем уведомление о модуле
        text = (
            "⛽ <b>Gas Tracker</b>\n\n"
            "Модуль мониторинга цены газа Ethereum\n\n"
            "🔄 <b>Статус:</b> В разработке\n"
            "📅 <b>Доступность:</b> Скоро"
        )
        
        builder = InlineKeyboardBuilder()
        builder.button(text="◀️ Назад", callback_data="main_menu")
        
        await callback.message.edit_text(text, reply_markup=builder.as_markup(), parse_mode="HTML")
        await callback.answer("⛽ Gas Tracker скоро будет доступен!")
    
    async def show_whale_tracker(self, callback: types.CallbackQuery):
        """Переход к модулю отслеживания китов."""
        text = (
            "🐋 <b>Whale Tracker</b> (Ограниченная версия)\n\n"
            
            "⚠️ <b>Важные ограничения:</b>\n"
            "• Только ETH транзакции (не ERC-20)\n"
            "• Задержка 1-2 блока (~30-60 сек)\n"
            "• Только известные адреса китов\n"
            "• Лимит API: 5 запросов/сек\n\n"
            
            "✅ <b>Что работает:</b>\n"
            "• Крупные ETH переводы (>100 ETH)\n"
            "• Фильтрация по сумме\n"
            "• Основные уведомления\n\n"
            
            "💰 <b>Для полного функционала нужны платные API</b>"
        )
        
        builder = InlineKeyboardBuilder()
        builder.button(text="📊 Мои алерты", callback_data="whale_alerts")
        builder.button(text="➕ Добавить алерт", callback_data="whale_add")
        builder.button(text="ℹ️ Подробнее об ограничениях", callback_data="whale_limitations")
        builder.button(text="◀️ Назад", callback_data="main_menu")
        builder.adjust(1)
        
        await callback.message.edit_text(text, reply_markup=builder.as_markup(), parse_mode="HTML")
        await callback.answer()
    
    async def show_wallet_tracker(self, callback: types.CallbackQuery):
        """Переход к модулю отслеживания кошельков."""
        text = (
            "👛 <b>Wallet Tracker</b> (Сильно ограниченная версия)\n\n"
            
            "🚫 <b>Критические ограничения:</b>\n"
            "• НЕ работает в реальном времени\n"
            "• Проверка каждые 2-5 минут\n"
            "• Только ETH транзакции\n"
            "• Максимум 5 кошельков\n\n"
            
            "✅ <b>Что работает:</b>\n"
            "• Проверка кошелька по запросу\n"
            "• Уведомления с задержкой\n"
            "• Фильтрация по сумме\n\n"
            
            "💰 <b>Для реального времени нужна Ethereum нода</b>"
        )
        
        builder = InlineKeyboardBuilder()
        builder.button(text="👛 Мои кошельки", callback_data="wallet_list")
        builder.button(text="➕ Добавить кошелек", callback_data="wallet_add")
        builder.button(text="🔍 Проверить кошелек", callback_data="wallet_check")
        builder.button(text="⚠️ Ограничения", callback_data="wallet_limitations")
        builder.button(text="◀️ Назад", callback_data="main_menu")
        builder.adjust(1)
        
        await callback.message.edit_text(text, reply_markup=builder.as_markup(), parse_mode="HTML")
        await callback.answer()
    
    async def show_settings(self, callback: types.CallbackQuery):
        """Показ настроек."""
        text = (
            "⚙️ <b>Настройки</b>\n\n"
            
            "🔔 <b>Уведомления:</b> Включены\n"
            "🌐 <b>Язык:</b> Русский\n"
            "📊 <b>Формат данных:</b> Обычный\n\n"
            
            "Дополнительные настройки будут добавлены в следующих версиях."
        )
        
        builder = InlineKeyboardBuilder()
        builder.button(text="🔔 Уведомления", callback_data="settings_notifications")
        builder.button(text="📊 Статистика", callback_data="settings_stats")
        builder.button(text="◀️ Назад", callback_data="main_menu")
        builder.adjust(1)
        
        await callback.message.edit_text(text, reply_markup=builder.as_markup(), parse_mode="HTML")
        await callback.answer()
    
    async def show_about(self, callback: types.CallbackQuery):
        """Информация о боте."""
        text = (
            "ℹ️ <b>О боте</b>\n\n"
            
            "🤖 <b>Crypto Monitor Bot v2.0</b>\n"
            "📅 Обновлено: 2024\n\n"
            
            "📋 <b>Модули:</b>\n"
            "• Price Alerts - Полный функционал\n"
            "• Gas Tracker - Полный функционал\n"  
            "• Whale Tracker - Ограниченно\n"
            "• Wallet Tracker - Ограниченно\n\n"
            
            "⚠️ <b>Ограничения:</b>\n"
            "Некоторые функции ограничены из-за использования бесплатных API\n\n"
            
            "💡 <b>Архитектура:</b> Модульный монолит\n"
            "🔧 <b>Готов к масштабированию</b>"
        )
        
        builder = InlineKeyboardBuilder()
        builder.button(text="📝 Changelog", callback_data="about_changelog")
        builder.button(text="🔧 Техническая информация", callback_data="about_tech")
        builder.button(text="◀️ Назад", callback_data="main_menu")
        builder.adjust(1)
        
        await callback.message.edit_text(text, reply_markup=builder.as_markup(), parse_mode="HTML")
        await callback.answer()
