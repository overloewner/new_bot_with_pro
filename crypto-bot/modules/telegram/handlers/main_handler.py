# modules/telegram/handlers/main_handler.py
"""Исправленный главный обработчик с рабочими callback handlers."""

from datetime import datetime
from typing import Any, Dict, Optional
from aiogram import Router, types, F
from aiogram.filters import Command
from aiogram.fsm.context import FSMContext
from aiogram.utils.keyboard import InlineKeyboardBuilder
from modules.telegram.keyboards.main_keyboards import MainKeyboards
from shared.events import event_bus, Event, USER_COMMAND_RECEIVED
from shared.cache.memory_cache import cache_manager

import logging

logger = logging.getLogger(__name__)


class MainHandler:
    """Главный обработчик команд бота с полной функциональностью."""
    
    def __init__(self):
        self.router = Router()
        self.keyboards = MainKeyboards()
        self.cache = cache_manager.get_cache('telegram')
        
        # Сервисы (будут инжектированы)
        self.price_alerts_service = None
        self.gas_tracker_service = None
        self.whale_service = None
        self.wallet_service = None
    
    def set_services(self, **services):
        """Инъекция сервисов."""
        self.price_alerts_service = services.get('price_alerts')
        self.gas_tracker_service = services.get('gas_tracker')
        self.whale_service = services.get('whale_tracker')
        self.wallet_service = services.get('wallet_tracker')
    
    def register(self, dp):
        """Регистрация всех обработчиков."""
        # Команды
        self.router.message(Command("start"))(self.cmd_start)
        self.router.message(Command("help"))(self.cmd_help)
        self.router.message(Command("status"))(self.cmd_status)
        
        # Главное меню
        self.router.callback_query(F.data == "main_menu")(self.show_main_menu)
        
        # Модули - исправленные обработчики
        self.router.callback_query(F.data == "price_alerts")(self.show_price_alerts_menu)
        self.router.callback_query(F.data == "gas_tracker")(self.show_gas_tracker_menu)
        self.router.callback_query(F.data == "whale_tracker")(self.show_whale_tracker_menu)
        self.router.callback_query(F.data == "wallet_tracker")(self.show_wallet_tracker_menu)
        
        # Настройки и информация
        self.router.callback_query(F.data == "settings")(self.show_settings)
        self.router.callback_query(F.data == "about")(self.show_about)
        self.router.callback_query(F.data == "cmd_status")(self.cmd_status_callback)
        
        # Дополнительные обработчики для вложенных меню
        self._register_additional_handlers()
        
        dp.include_router(self.router)
    
    def _register_additional_handlers(self):
        """Регистрация дополнительных обработчиков."""
        # Settings handlers
        self.router.callback_query(F.data == "settings_notifications")(self.toggle_notifications)
        self.router.callback_query(F.data == "settings_stats")(self.show_user_stats)
        
        # About handlers
        self.router.callback_query(F.data == "about_changelog")(self.show_changelog)
        self.router.callback_query(F.data == "about_tech")(self.show_tech_info)
        
        # Status handlers
        self.router.callback_query(F.data.startswith("status_"))(self.handle_status_actions)
    
    async def cmd_start(self, message: types.Message):
        """Команда /start с улучшенной функциональностью."""
        user_id = message.from_user.id
        username = message.from_user.username
        
        # Публикуем событие
        await event_bus.publish(Event(
            type=USER_COMMAND_RECEIVED,
            data={
                "user_id": user_id,
                "command": "start",
                "username": username,
                "first_name": message.from_user.first_name
            },
            source_module="telegram"
        ))
        
        # Проверяем кеш для персонализации
        cache_key = f"user_stats:{user_id}"
        user_stats = await self.cache.get(cache_key, {})
        
        welcome_text = (
            f"🤖 <b>Добро пожаловать{', ' + message.from_user.first_name if message.from_user.first_name else ''}!</b>\n\n"
            
            "🚀 <b>Crypto Monitor Bot v2.0</b>\n"
            "Профессиональный мониторинг криптовалют\n\n"
            
            "📊 <b>Доступные модули:</b>\n"
            "📈 <b>Price Alerts</b> - Умные ценовые уведомления\n"
            "⛽ <b>Gas Tracker</b> - Мониторинг газа Ethereum\n"
            "🐋 <b>Whale Tracker</b> - Отслеживание крупных транзакций\n"
            "👛 <b>Wallet Tracker</b> - Мониторинг кошельков\n\n"
        )
        
        if user_stats:
            welcome_text += f"📈 Ваша статистика:\n"
            welcome_text += f"• Получено алертов: {user_stats.get('alerts_received', 0)}\n"
            welcome_text += f"• Активных пресетов: {user_stats.get('active_presets', 0)}\n\n"
        
        welcome_text += (
            "✨ <b>Новое в v2.0:</b>\n"
            "• Модульная архитектура\n"
            "• Улучшенная производительность\n"
            "• Расширенные настройки\n\n"
            
            "⚡ Выберите модуль для начала работы:"
        )
        
        keyboard = self.keyboards.get_main_menu_keyboard()
        await message.answer(welcome_text, reply_markup=keyboard, parse_mode="HTML")
    
    async def cmd_help(self, message: types.Message):
        """Команда /help с подробной информацией."""
        help_text = (
            "📖 <b>Справка по Crypto Monitor Bot</b>\n\n"
            
            "<b>🎯 Основные команды:</b>\n"
            "/start - Главное меню и приветствие\n"
            "/help - Подробная справка (эта страница)\n"
            "/status - Статус всех модулей системы\n\n"
            
            "<b>📈 Price Alerts - Ценовые уведомления:</b>\n"
            "• Создание пользовательских пресетов\n"
            "• Отслеживание до 500 пар одновременно\n"
            "• Настройка процента изменения (0.1% - 100%)\n"
            "• Множественные таймфреймы (1m - 1d)\n"
            "• Фильтрация по объему торгов\n"
            "• Группировка уведомлений\n\n"
            
            "<b>⛽ Gas Tracker - Мониторинг газа:</b>\n"
            "• Текущие цены газа в реальном времени\n"
            "• Уведомления при достижении порога\n"
            "• 4 уровня скорости (Safe/Standard/Fast/Instant)\n"
            "• Исторические данные и рекомендации\n\n"
            
            "<b>🐋 Whale Tracker - Отслеживание китов:</b>\n"
            "• Мониторинг крупных транзакций\n"
            "• Настройка порогов в USD или BTC\n"
            "• Фильтрация по типам транзакций\n"
            "⚠️ <i>Ограниченная версия (требует API ключи)</i>\n\n"
            
            "<b>👛 Wallet Tracker - Мониторинг кошельков:</b>\n"
            "• Отслеживание до 5 кошельков\n"
            "• Уведомления о входящих/исходящих\n"
            "• Фильтрация по минимальной сумме\n"
            "⚠️ <i>Проверка каждые 2-5 минут</i>\n\n"
            
            "<b>⚙️ Дополнительные возможности:</b>\n"
            "• Персональные настройки уведомлений\n"
            "• Статистика использования\n"
            "• Экспорт данных\n"
            "• Многоязычная поддержка\n\n"
            
            "<b>🔧 Технические особенности:</b>\n"
            "• Модульная архитектура\n"
            "• Отказоустойчивость\n"
            "• Кеширование в памяти\n"
            "• Защита от Rate Limiting\n\n"
            
            "❓ <b>Нужна помощь?</b>\n"
            "Используйте кнопки меню или обратитесь к администратору"
        )
        
        keyboard = self.keyboards.get_help_keyboard()
        await message.answer(help_text, reply_markup=keyboard, parse_mode="HTML")
    
    async def cmd_status(self, message: types.Message):
        """Команда /status с реальной информацией о модулях."""
        await self._show_status(message)
    
    async def cmd_status_callback(self, callback: types.CallbackQuery):
        """Callback для команды статуса."""
        await self._show_status(callback.message, callback=callback)
    
    async def _show_status(self, message: types.Message, callback: Optional[types.CallbackQuery] = None):
        """Показ статуса системы."""
        # Получаем статус EventBus
        event_stats = event_bus.get_stats()
        
        # Получаем статус кешей
        cache_stats = cache_manager.get_all_stats()
        
        status_text = (
            "📊 <b>Статус системы Crypto Monitor Bot</b>\n\n"
            
            "<b>🔧 Основные модули:</b>\n"
        )
        
        # Проверяем статус каждого модуля
        modules_status = {
            "📈 Price Alerts": self._check_service_status(self.price_alerts_service),
            "⛽ Gas Tracker": self._check_service_status(self.gas_tracker_service),
            "🐋 Whale Tracker": self._check_service_status(self.whale_service),
            "👛 Wallet Tracker": self._check_service_status(self.wallet_service)
        }
        
        for module_name, status in modules_status.items():
            status_icon = "🟢" if status["running"] else "🔴"
            status_text += f"{status_icon} {module_name}: {status['status']}\n"
        
        status_text += (
            f"\n<b>📡 Event System:</b>\n"
            f"• Типов событий: {event_stats['event_types']}\n"
            f"• Активных обработчиков: {event_stats['total_handlers']}\n"
            f"• Неисправных обработчиков: {event_stats['failed_handlers']}\n"
        )
        
        if cache_stats:
            status_text += f"\n<b>💾 Система кеширования:</b>\n"
            total_entries = sum(stats.get('total_entries', 0) for stats in cache_stats.values())
            total_memory = sum(stats.get('memory_usage_mb', 0) for stats in cache_stats.values())
            status_text += f"• Записей в кеше: {total_entries}\n"
            status_text += f"• Память: {total_memory:.1f} MB\n"
        
        status_text += f"\n🕐 <b>Последнее обновление:</b> {datetime.now().strftime('%H:%M:%S')}"
        
        builder = InlineKeyboardBuilder()
        builder.button(text="🔄 Обновить", callback_data="cmd_status")
        builder.button(text="📊 Детали", callback_data="status_details")
        builder.button(text="🏠 Главное меню", callback_data="main_menu")
        builder.adjust(2, 1)
        
        if callback:
            await callback.message.edit_text(status_text, reply_markup=builder.as_markup(), parse_mode="HTML")
            await callback.answer("🔄 Статус обновлен")
        else:
            await message.answer(status_text, reply_markup=builder.as_markup(), parse_mode="HTML")
    
    def _check_service_status(self, service) -> Dict[str, Any]:
        """Проверка статуса сервиса."""
        if service is None:
            return {"running": False, "status": "Не инициализирован"}
        
        if hasattr(service, 'running'):
            if service.running:
                return {"running": True, "status": "Активен"}
            else:
                return {"running": False, "status": "Остановлен"}
        
        return {"running": True, "status": "Готов"}
    
    async def show_main_menu(self, callback: types.CallbackQuery):
        """Показ главного меню."""
        user_id = callback.from_user.id
        
        # Получаем персональную статистику
        cache_key = f"user_stats:{user_id}"
        user_stats = await self.cache.get(cache_key, {})
        
        text = "🏠 <b>Главное меню</b>\n\n"
        
        if user_stats:
            text += (
                f"📊 <b>Ваша статистика:</b>\n"
                f"• Алертов получено: {user_stats.get('alerts_received', 0)}\n"
                f"• Активных пресетов: {user_stats.get('active_presets', 0)}\n"
                f"• Отслеживаемых пар: {user_stats.get('tracked_pairs', 0)}\n\n"
            )
        
        text += "🎯 Выберите модуль для работы:"
        
        keyboard = self.keyboards.get_main_menu_keyboard()
        await callback.message.edit_text(text, reply_markup=keyboard, parse_mode="HTML")
        await callback.answer()
    
    # ИСПРАВЛЕННЫЕ ОБРАБОТЧИКИ МОДУЛЕЙ
    
    async def show_price_alerts_menu(self, callback: types.CallbackQuery):
        """Показ меню Price Alerts с реальной функциональностью."""
        if not self.price_alerts_service:
            await callback.answer("❌ Сервис Price Alerts недоступен")
            return
        
        # Публикуем событие для получения статистики
        await event_bus.publish(Event(
            type="price_alerts.get_user_stats",
            data={"user_id": callback.from_user.id},
            source_module="telegram"
        ))
        
        text = (
            "📈 <b>Price Alerts</b>\n\n"
            "🎯 <b>Возможности:</b>\n"
            "• Мониторинг до 500 торговых пар\n"
            "• Настройка процента изменения\n"
            "• Множественные таймфреймы\n"
            "• Группировка уведомлений\n"
            "• Фильтрация по объему\n\n"
            
            "📊 <b>Ваши пресеты:</b>\n"
            "Загружаем данные...\n\n"
            
            "⚡ Что хотите сделать?"
        )
        
        builder = InlineKeyboardBuilder()
        builder.button(text="➕ Создать пресет", callback_data="price_create_preset")
        builder.button(text="📋 Мои пресеты", callback_data="price_my_presets")
        builder.button(text="🚀 Запустить мониторинг", callback_data="price_start_monitoring")
        builder.button(text="⏹️ Остановить мониторинг", callback_data="price_stop_monitoring")
        builder.button(text="📊 Статистика", callback_data="price_statistics")
        builder.button(text="◀️ Назад", callback_data="main_menu")
        builder.adjust(1)
        
        await callback.message.edit_text(text, reply_markup=builder.as_markup(), parse_mode="HTML")
        await callback.answer()
    
    async def show_gas_tracker_menu(self, callback: types.CallbackQuery):
        """Показ меню Gas Tracker с реальной функциональностью."""
        if not self.gas_tracker_service:
            await callback.answer("❌ Сервис Gas Tracker недоступен")
            return
        
        # Получаем текущие цены на газ
        current_gas = None
        if hasattr(self.gas_tracker_service, 'get_current_gas_price'):
            current_gas = self.gas_tracker_service.get_current_gas_price()
        
        text = "⛽ <b>Gas Tracker</b>\n\n"
        
        if current_gas:
            text += (
                f"💰 <b>Текущие цены газа:</b>\n"
                f"🟢 Безопасный: {current_gas['safe']:.1f} gwei\n"
                f"🟡 Стандартный: {current_gas['standard']:.1f} gwei\n"
                f"🟠 Быстрый: {current_gas['fast']:.1f} gwei\n"
                f"🔴 Мгновенный: {current_gas['instant']:.1f} gwei\n\n"
            )
        else:
            text += "⏳ Загружаем актуальные цены на газ...\n\n"
        
        # Получаем пользовательские алерты
        user_alerts = []
        if hasattr(self.gas_tracker_service, 'get_user_alerts'):
            user_alerts = self.gas_tracker_service.get_user_alerts(callback.from_user.id)
        
        text += (
            f"🔔 <b>Ваши алерты:</b>\n"
            f"Активных: {len([a for a in user_alerts if a.get('is_active', False)])}\n"
            f"Всего: {len(user_alerts)}\n\n"
            
            "⚡ Управление алертами:"
        )
        
        builder = InlineKeyboardBuilder()
        builder.button(text="📊 Текущие цены", callback_data="gas_current")
        builder.button(text="🔔 Мои алерты", callback_data="gas_alerts")
        builder.button(text="➕ Добавить алерт", callback_data="gas_add_alert")
        builder.button(text="📈 График цен", callback_data="gas_chart")
        builder.button(text="⚙️ Настройки", callback_data="gas_settings")
        builder.button(text="◀️ Назад", callback_data="main_menu")
        builder.adjust(2, 2, 1, 1)
        
        await callback.message.edit_text(text, reply_markup=builder.as_markup(), parse_mode="HTML")
        await callback.answer()
    
    async def show_whale_tracker_menu(self, callback: types.CallbackQuery):
        """Показ меню Whale Tracker с информацией об ограничениях."""
        if not self.whale_service:
            await callback.answer("❌ Сервис Whale Tracker недоступен")
            return
        
        # Получаем информацию об ограничениях
        limitations = {}
        if hasattr(self.whale_service, 'get_limitations_info'):
            limitations = self.whale_service.get_limitations_info()
        
        # Получаем пользовательские алерты
        user_alerts = []
        if hasattr(self.whale_service, 'get_user_alerts'):
            user_alerts = self.whale_service.get_user_alerts(callback.from_user.id)
        
        text = (
            "🐋 <b>Whale Tracker</b>\n"
            "<i>Ограниченная версия</i>\n\n"
            
            f"🔔 <b>Ваши алерты:</b> {len(user_alerts)}\n"
            f"✅ <b>Активных:</b> {len([a for a in user_alerts if a.get('is_active', False)])}\n\n"
        )
        
        if limitations:
            text += (
                "⚠️ <b>Текущие ограничения:</b>\n"
                "• Требуется Etherscan API ключ\n"
                "• Только мониторинг цен ETH/BTC\n"
                "• Нет отслеживания транзакций\n\n"
            )
        
        text += "🎯 Доступные действия:"
        
        builder = InlineKeyboardBuilder()
        builder.button(text="📊 Мои алерты", callback_data="whale_alerts")
        builder.button(text="➕ Добавить алерт", callback_data="whale_add_alert")
        builder.button(text="ℹ️ Ограничения", callback_data="whale_limitations")
        builder.button(text="💰 Upgrade", callback_data="whale_upgrade_info")
        builder.button(text="◀️ Назад", callback_data="main_menu")
        builder.adjust(2, 2, 1)
        
        await callback.message.edit_text(text, reply_markup=builder.as_markup(), parse_mode="HTML")
        await callback.answer()
    
    async def show_wallet_tracker_menu(self, callback: types.CallbackQuery):
        """Показ меню Wallet Tracker с реальной функциональностью."""
        if not self.wallet_service:
            await callback.answer("❌ Сервис Wallet Tracker недоступен")
            return
        
        # Получаем пользовательские алерты
        user_alerts = []
        if hasattr(self.wallet_service, 'get_user_alerts'):
            user_alerts = self.wallet_service.get_user_alerts(callback.from_user.id)
        
        # Получаем информацию об ограничениях
        limitations = {}
        if hasattr(self.wallet_service, 'get_limitations_info'):
            limitations = self.wallet_service.get_limitations_info()
        
        text = (
            "👛 <b>Wallet Tracker</b>\n"
            "<i>Ограниченная версия</i>\n\n"
            
            f"🔍 <b>Отслеживаемых кошельков:</b> {len(user_alerts)}/5\n"
            f"✅ <b>Активных:</b> {len([a for a in user_alerts if a.get('is_active', False)])}\n\n"
            
            "⚠️ <b>Важно:</b>\n"
            "• НЕ работает в реальном времени\n"
            "• Проверка каждые 2-5 минут\n"
            "• Только ETH транзакции\n\n"
            
            "🎯 Управление кошельками:"
        )
        
        builder = InlineKeyboardBuilder()
        builder.button(text="👛 Мои кошельки", callback_data="wallet_list")
        builder.button(text="➕ Добавить кошелек", callback_data="wallet_add")
        builder.button(text="🔍 Проверить кошелек", callback_data="wallet_check")
        builder.button(text="⚠️ Ограничения", callback_data="wallet_limitations")
        builder.button(text="💰 Upgrade", callback_data="wallet_upgrade_info")
        builder.button(text="◀️ Назад", callback_data="main_menu")
        builder.adjust(2, 2, 1, 1)
        
        await callback.message.edit_text(text, reply_markup=builder.as_markup(), parse_mode="HTML")
        await callback.answer()
    
    async def show_settings(self, callback: types.CallbackQuery):
        """Показ настроек с реальной функциональностью."""
        user_id = callback.from_user.id
        
        # Получаем настройки пользователя из кеша
        cache_key = f"user_settings:{user_id}"
        user_settings = await self.cache.get(cache_key, {
            'notifications_enabled': True,
            'language': 'ru',
            'timezone': 'UTC',
            'alert_sound': True,
            'group_notifications': True
        })
        
        text = (
            "⚙️ <b>Настройки</b>\n\n"
            
            f"🔔 Уведомления: {'🟢 Включены' if user_settings.get('notifications_enabled') else '🔴 Отключены'}\n"
            f"🌐 Язык: {user_settings.get('language', 'ru').upper()}\n"
            f"🕐 Часовой пояс: {user_settings.get('timezone', 'UTC')}\n"
            f"🔊 Звук алертов: {'🟢 Вкл' if user_settings.get('alert_sound') else '🔴 Выкл'}\n"
            f"📦 Группировка: {'🟢 Вкл' if user_settings.get('group_notifications') else '🔴 Выкл'}\n\n"
            
            "🎛️ Управление настройками:"
        )
        
        builder = InlineKeyboardBuilder()
        builder.button(
            text="🔔 Уведомления" if user_settings.get('notifications_enabled') else "🔕 Уведомления",
            callback_data="settings_toggle_notifications"
        )
        builder.button(text="🌐 Язык", callback_data="settings_language")
        builder.button(text="🕐 Часовой пояс", callback_data="settings_timezone")
        builder.button(text="🔊 Звук", callback_data="settings_toggle_sound")
        builder.button(text="📦 Группировка", callback_data="settings_toggle_grouping")
        builder.button(text="📊 Моя статистика", callback_data="settings_stats")
        builder.button(text="📤 Экспорт данных", callback_data="settings_export")
        builder.button(text="🗑️ Очистить данные", callback_data="settings_clear")
        builder.button(text="◀️ Назад", callback_data="main_menu")
        builder.adjust(2, 2, 2, 1, 1, 1)
        
        await callback.message.edit_text(text, reply_markup=builder.as_markup(), parse_mode="HTML")
        await callback.answer()
    
    async def show_about(self, callback: types.CallbackQuery):
        """Показ информации о боте."""
        from datetime import datetime
        
        # Получаем статистику системы
        event_stats = event_bus.get_stats()
        cache_stats = cache_manager.get_all_stats()
        
        text = (
            "ℹ️ <b>О Crypto Monitor Bot</b>\n\n"
            
            "🤖 <b>Версия:</b> 2.0.0\n"
            "📅 <b>Обновлено:</b> Декабрь 2024\n"
            "👨‍💻 <b>Архитектура:</b> Модульный монолит\n\n"
            
            "📋 <b>Активные модули:</b>\n"
            "✅ Price Alerts - Полный функционал\n"
            "✅ Gas Tracker - Полный функционал\n"
            "⚠️ Whale Tracker - Ограниченно\n"
            "⚠️ Wallet Tracker - Ограниченно\n\n"
            
            "🔧 <b>Технические характеристики:</b>\n"
            f"• Обработчиков событий: {event_stats.get('total_handlers', 0)}\n"
            f"• Кеш в памяти: {sum(s.get('total_entries', 0) for s in cache_stats.values())} записей\n"
            f"• Модульная архитектура\n"
            f"• Отказоустойчивость\n"
            f"• Rate limiting защита\n\n"
            
            "🚀 <b>Возможности v2.0:</b>\n"
            "• Кеширование в памяти\n"
            "• Многопоточная обработка\n"
            "• Circuit breaker pattern\n"
            "• Улучшенная изоляция модулей\n"
            "• Расширенная статистика\n\n"
            
            "💡 <b>Планы развития:</b>\n"
            "• Интеграция с premium API\n"
            "• Реальное время для всех модулей\n"
            "• Расширенная аналитика\n"
            "• Мобильное приложение\n\n"
            
            f"⏰ <b>Время работы:</b> {datetime.now().strftime('%d.%m.%Y %H:%M')}"
        )
        
        builder = InlineKeyboardBuilder()
        builder.button(text="📝 Changelog", callback_data="about_changelog")
        builder.button(text="🔧 Техническая информация", callback_data="about_tech")
        builder.button(text="📊 Статистика системы", callback_data="about_system_stats")
        builder.button(text="🔗 Исходный код", callback_data="about_source")
        builder.button(text="👨‍💻 Разработчик", callback_data="about_developer")
        builder.button(text="◀️ Назад", callback_data="main_menu")
        builder.adjust(2, 2, 1, 1)
        
        await callback.message.edit_text(text, reply_markup=builder.as_markup(), parse_mode="HTML")
        await callback.answer()
    
    # ДОПОЛНИТЕЛЬНЫЕ ОБРАБОТЧИКИ
    
    async def toggle_notifications(self, callback: types.CallbackQuery):
        """Переключение уведомлений."""
        user_id = callback.from_user.id
        cache_key = f"user_settings:{user_id}"
        
        user_settings = await self.cache.get(cache_key, {})
        current_state = user_settings.get('notifications_enabled', True)
        new_state = not current_state
        
        user_settings['notifications_enabled'] = new_state
        await self.cache.set(cache_key, user_settings, ttl=86400)  # 24 часа
        
        # Публикуем событие изменения настроек
        await event_bus.publish(Event(
            type="user.settings_changed",
            data={
                "user_id": user_id,
                "setting": "notifications_enabled",
                "value": new_state
            },
            source_module="telegram"
        ))
        
        status = "включены" if new_state else "отключены"
        await callback.answer(f"🔔 Уведомления {status}")
        
        # Обновляем меню настроек
        await self.show_settings(callback)
    
    async def show_user_stats(self, callback: types.CallbackQuery):
        """Показ пользовательской статистики."""
        user_id = callback.from_user.id
        
        # Получаем статистику из кеша
        stats_key = f"user_stats:{user_id}"
        user_stats = await self.cache.get(stats_key, {})
        
        if not user_stats:
            # Генерируем базовую статистику
            user_stats = {
                'alerts_received': 0,
                'active_presets': 0,
                'tracked_pairs': 0,
                'gas_alerts': 0,
                'whale_alerts': 0,
                'wallet_alerts': 0,
                'join_date': datetime.now().isoformat(),
                'last_activity': datetime.now().isoformat()
            }
            await self.cache.set(stats_key, user_stats, ttl=3600)
        
        text = (
            f"📊 <b>Статистика пользователя</b>\n\n"
            
            f"👤 <b>Профиль:</b>\n"
            f"• ID: {user_id}\n"
            f"• Имя: {callback.from_user.first_name or 'Не указано'}\n"
            f"• Username: @{callback.from_user.username or 'не указан'}\n\n"
            
            f"📈 <b>Активность:</b>\n"
            f"• Получено алертов: {user_stats.get('alerts_received', 0)}\n"
            f"• Активных пресетов: {user_stats.get('active_presets', 0)}\n"
            f"• Отслеживаемых пар: {user_stats.get('tracked_pairs', 0)}\n\n"
            
            f"🔔 <b>Алерты по модулям:</b>\n"
            f"• Price Alerts: {user_stats.get('price_alerts', 0)}\n"
            f"• Gas Tracker: {user_stats.get('gas_alerts', 0)}\n"
            f"• Whale Tracker: {user_stats.get('whale_alerts', 0)}\n"
            f"• Wallet Tracker: {user_stats.get('wallet_alerts', 0)}\n\n"
            
            f"📅 <b>Даты:</b>\n"
            f"• Регистрация: {user_stats.get('join_date', 'Неизвестно')[:10]}\n"
            f"• Последняя активность: {user_stats.get('last_activity', 'Неизвестно')[:10]}"
        )
        
        builder = InlineKeyboardBuilder()
        builder.button(text="📤 Экспорт", callback_data="stats_export")
        builder.button(text="🔄 Обновить", callback_data="settings_stats")
        builder.button(text="◀️ Назад", callback_data="settings")
        builder.adjust(2, 1)
        
        await callback.message.edit_text(text, reply_markup=builder.as_markup(), parse_mode="HTML")
        await callback.answer()
    
    async def show_changelog(self, callback: types.CallbackQuery):
        """Показ истории изменений."""
        text = (
            "📝 <b>История изменений</b>\n\n"
            
            "<b>🚀 Версия 2.0.0</b> (Декабрь 2024)\n"
            "• Полная переработка архитектуры\n"
            "• Модульная система с изоляцией\n"
            "• Кеширование в памяти\n"
            "• Circuit breaker pattern\n"
            "• Улучшенная отказоустойчивость\n"
            "• Многопоточная обработка\n"
            "• Расширенная статистика\n"
            "• Новый интерфейс\n\n"
            
            "<b>📈 Версия 1.5.2</b> (Ноябрь 2024)\n"
            "• Исправления багов Price Alerts\n"
            "• Оптимизация WebSocket соединений\n"
            "• Улучшенная обработка ошибок\n\n"
            
            "<b>⛽ Версия 1.5.0</b> (Октябрь 2024)\n"
            "• Добавлен Gas Tracker\n"
            "• Поддержка множественных алертов\n"
            "• Настройки уведомлений\n\n"
            
            "<b>🐋 Версия 1.4.0</b> (Сентябрь 2024)\n"
            "• Beta версия Whale Tracker\n"
            "• Базовое отслеживание кошельков\n"
            "• Система тегов\n\n"
            
            "<b>🎯 Версия 1.0.0</b> (Август 2024)\n"
            "• Первый релиз\n"
            "• Базовые ценовые алерты\n"
            "• Поддержка Binance API\n"
            "• Простой интерфейс"
        )
        
        builder = InlineKeyboardBuilder()
        builder.button(text="🔮 Планы", callback_data="about_roadmap")
        builder.button(text="◀️ Назад", callback_data="about")
        builder.adjust(1)
        
        await callback.message.edit_text(text, reply_markup=builder.as_markup(), parse_mode="HTML")
        await callback.answer()
    
    async def show_tech_info(self, callback: types.CallbackQuery):
        """Показ технической информации."""
        # Получаем детальную статистику
        event_stats = event_bus.get_stats()
        cache_stats = cache_manager.get_all_stats()
        
        text = (
            "🔧 <b>Техническая информация</b>\n\n"
            
            "<b>🏗️ Архитектура:</b>\n"
            "• Модульный монолит\n"
            "• Event-driven architecture\n"
            "• In-memory caching\n"
            "• Circuit breaker pattern\n"
            "• Graceful degradation\n\n"
            
            "<b>📡 Event System:</b>\n"
            f"• Типов событий: {event_stats.get('event_types', 0)}\n"
            f"• Обработчиков: {event_stats.get('total_handlers', 0)}\n"
            f"• Middleware: {event_stats.get('middleware_count', 0)}\n"
            f"• История: {event_stats.get('history_size', 0)} событий\n\n"
            
            "<b>💾 Система кеширования:</b>\n"
        )
        
        if cache_stats:
            total_entries = sum(s.get('total_entries', 0) for s in cache_stats.values())
            total_memory = sum(s.get('memory_usage_mb', 0) for s in cache_stats.values())
            avg_hit_rate = sum(s.get('hit_rate', 0) for s in cache_stats.values()) / len(cache_stats)
            
            text += (
                f"• Кешей: {len(cache_stats)}\n"
                f"• Записей: {total_entries}\n"
                f"• Память: {total_memory:.1f} MB\n"
                f"• Hit rate: {avg_hit_rate:.1f}%\n\n"
            )
        
        text += (
            "<b>🛡️ Защита:</b>\n"
            "• Rate limiting\n"
            "• Circuit breakers\n"
            "• Timeout protection\n"
            "• Error isolation\n"
            "• Graceful fallbacks\n\n"
            
            "<b>⚡ Производительность:</b>\n"
            "• Async/await everywhere\n"
            "• Connection pooling\n"
            "• Batch processing\n"
            "• Memory optimization\n"
            "• Smart caching strategies"
        )
        
        builder = InlineKeyboardBuilder()
        builder.button(text="📊 Подробная статистика", callback_data="tech_detailed_stats")
        builder.button(text="🔧 Конфигурация", callback_data="tech_config")
        builder.button(text="◀️ Назад", callback_data="about")
        builder.adjust(1)
        
        await callback.message.edit_text(text, reply_markup=builder.as_markup(), parse_mode="HTML")
        await callback.answer()
    
    async def handle_status_actions(self, callback: types.CallbackQuery):
        """Обработка действий в меню статуса."""
        action = callback.data.split("_", 1)[1]
        
        if action == "details":
            await self._show_detailed_status(callback)
        elif action == "restart":
            await callback.answer("🔄 Перезапуск модулей...")
            # Здесь можно добавить логику перезапуска
        elif action == "logs":
            await self._show_system_logs(callback)
        else:
            await callback.answer("❌ Неизвестное действие")
    
    async def _show_detailed_status(self, callback: types.CallbackQuery):
        """Детальный статус системы."""
        event_stats = event_bus.get_stats()
        cache_stats = cache_manager.get_all_stats()
        
        text = (
            "📊 <b>Детальный статус системы</b>\n\n"
            
            "<b>📡 Event Bus:</b>\n"
        )
        
        for event_type, count in event_stats.get('subscribers', {}).items():
            text += f"• {event_type}: {count} подписчиков\n"
        
        text += f"\n<b>💾 Кеши:</b>\n"
        for cache_name, stats in cache_stats.items():
            text += (
                f"• {cache_name}: {stats.get('total_entries', 0)} записей, "
                f"{stats.get('hit_rate', 0):.1f}% hit rate\n"
            )
        
        failed_handlers = event_stats.get('circuit_breakers_open', [])
        if failed_handlers:
            text += f"\n⚠️ <b>Проблемные обработчики:</b>\n"
            for handler in failed_handlers:
                text += f"• {handler}\n"
        
        builder = InlineKeyboardBuilder()
        builder.button(text="🔄 Обновить", callback_data="status_details")
        builder.button(text="◀️ Назад", callback_data="cmd_status")
        builder.adjust(1)
        
        await callback.message.edit_text(text, reply_markup=builder.as_markup(), parse_mode="HTML")
        await callback.answer()
    
    async def _show_system_logs(self, callback: types.CallbackQuery):
        """Показ системных логов."""
        # Получаем последние события из EventBus
        recent_events = event_bus.get_events_by_type("system.error", limit=10)
        
        text = "📋 <b>Системные логи</b>\n\n"
        
        if recent_events:
            text += "<b>Последние ошибки:</b>\n"
            for event in recent_events[-5:]:  # Последние 5
                timestamp = event.get('timestamp', 'Unknown')
                if isinstance(timestamp, str):
                    timestamp = timestamp[:19]  # Обрезаем до секунд
                text += f"• {timestamp}: {event.get('type', 'Unknown')}\n"
        else:
            text += "✅ Ошибок не обнаружено"
        
        builder = InlineKeyboardBuilder()
        builder.button(text="🔄 Обновить", callback_data="status_logs")
        builder.button(text="📤 Экспорт логов", callback_data="status_export_logs")
        builder.button(text="◀️ Назад", callback_data="cmd_status")
        builder.adjust(2, 1)
        
        await callback.message.edit_text(text, reply_markup=builder.as_markup(), parse_mode="HTML")
        await callback.answer()