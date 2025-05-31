# modules/telegram/handlers/main_handler.py
"""Обновленный главный обработчик без старых сервисов и кеша."""

from datetime import datetime
from typing import Any, Dict, Optional
from aiogram import Router, types, F
from aiogram.filters import Command
from aiogram.fsm.context import FSMContext
from aiogram.utils.keyboard import InlineKeyboardBuilder
from modules.telegram.keyboards.main_keyboards import MainKeyboards
from shared.events import event_bus, Event, USER_COMMAND_RECEIVED

import logging

logger = logging.getLogger(__name__)


class MainHandler:
    """Главный обработчик команд бота с обновленной функциональностью."""
    
    def __init__(self):
        self.router = Router()
        self.keyboards = MainKeyboards()
        
        # Сервисы (будут инжектированы)
        self.price_alerts_service = None
    
    def set_services(self, **services):
        """Инъекция сервисов."""
        self.price_alerts_service = services.get('price_alerts')
    
    def register(self, dp):
        """Регистрация всех обработчиков."""
        # Команды
        self.router.message(Command("start"))(self.cmd_start)
        self.router.message(Command("help"))(self.cmd_help)
        self.router.message(Command("status"))(self.cmd_status)
        
        # Главное меню
        self.router.callback_query(F.data == "main_menu")(self.show_main_menu)
        
        # Модули
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
        self.router.callback_query(F.data == "about_roadmap")(self.about_roadmap)
        
        # Status handlers
        self.router.callback_query(F.data.startswith("status_"))(self.handle_status_actions)
        
        # Price Alerts info
        self.router.callback_query(F.data == "price_help_info")(self.price_help_info)
    
    async def cmd_start(self, message: types.Message):
        """Команда /start с обновленной функциональностью."""
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
        
        welcome_text = (
            f"🤖 <b>Добро пожаловать{', ' + message.from_user.first_name if message.from_user.first_name else ''}!</b>\n\n"
            
            "🚀 <b>Crypto Monitor Bot v2.0</b>\n"
            "Профессиональный мониторинг криптовалют\n\n"
            
            "📊 <b>Доступные модули:</b>\n"
            "📈 <b>Price Alerts</b> - Умные ценовые уведомления\n"
            "⛽ <b>Gas Tracker</b> - В разработке\n"
            "🐋 <b>Whale Tracker</b> - В разработке\n"
            "👛 <b>Wallet Tracker</b> - В разработке\n\n"
            
            "✨ <b>Новая архитектура v2.0:</b>\n"
            "• Модульная система\n"
            "• Улучшенная производительность\n"
            "• Встроенное кеширование\n\n"
            
            "⚡ Выберите модуль для начала работы:"
        )
        
        keyboard = self.keyboards.get_main_menu_keyboard()
        await message.answer(welcome_text, reply_markup=keyboard, parse_mode="HTML")
    
    async def cmd_help(self, message: types.Message):
        """Команда /help с обновленной информацией."""
        help_text = (
            "📖 <b>Справка по Crypto Monitor Bot v2.0</b>\n\n"
            
            "<b>🎯 Основные команды:</b>\n"
            "/start - Главное меню и приветствие\n"
            "/help - Подробная справка (эта страница)\n"
            "/status - Статус системы\n\n"
            
            "<b>📈 Price Alerts - Ценовые уведомления:</b>\n"
            "• Создание пользовательских пресетов\n"
            "• Отслеживание множества пар одновременно\n"
            "• Настройка процента изменения\n"
            "• Различные таймфреймы\n"
            "• Группировка уведомлений\n"
            "• Встроенное кеширование для быстрой работы\n\n"
            
            "<b>🔧 Другие модули:</b>\n"
            "⛽ Gas Tracker - В разработке\n"
            "🐋 Whale Tracker - В разработке\n"
            "👛 Wallet Tracker - В разработке\n\n"
            
            "<b>⚙️ Дополнительные возможности:</b>\n"
            "• Персональные настройки\n"
            "• Статистика использования\n"
            "• Техническая информация\n\n"
            
            "<b>🔧 Архитектурные улучшения v2.0:</b>\n"
            "• Модульная система\n"
            "• Встроенное кеширование\n"
            "• Улучшенная отказоустойчивость\n"
            "• Упрощенная структура проекта\n\n"
            
            "❓ <b>Нужна помощь?</b>\n"
            "Используйте кнопки меню для навигации"
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
        
        status_text = (
            "📊 <b>Статус системы Crypto Monitor Bot v2.0</b>\n\n"
            
            "<b>🔧 Основные модули:</b>\n"
        )
        
        # Проверяем статус модулей
        modules_status = {
            "📈 Price Alerts": self._check_service_status(self.price_alerts_service),
            "⛽ Gas Tracker": {"running": False, "status": "В разработке"},
            "🐋 Whale Tracker": {"running": False, "status": "В разработке"},
            "👛 Wallet Tracker": {"running": False, "status": "В разработке"}
        }
        
        for module_name, status in modules_status.items():
            status_icon = "🟢" if status["running"] else "🔴"
            status_text += f"{status_icon} {module_name}: {status['status']}\n"
        
        status_text += (
            f"\n<b>📡 Event System:</b>\n"
            f"• Типов событий: {event_stats.get('event_types', 0)}\n"
            f"• Активных обработчиков: {event_stats.get('total_handlers', 0)}\n"
            f"• Статус: {'🟢 Работает' if event_stats.get('running', False) else '🔴 Остановлен'}\n"
        )
        
        # Добавляем статистику Price Alerts если доступен
        if self.price_alerts_service:
            pa_stats = self.price_alerts_service.get_statistics()
            status_text += (
                f"\n<b>📈 Price Alerts:</b>\n"
                f"• Отслеживаемых символов: {pa_stats.get('monitored_symbols', 0)}\n"
                f"• Цен в кеше: {pa_stats.get('current_prices_count', 0)}\n"
                f"• Алертов отправлено: {pa_stats.get('alerts_triggered', 0)}\n"
            )
            
            repo_stats = pa_stats.get('repository_stats', {})
            if repo_stats:
                status_text += (
                    f"• Кешированных пользователей: {repo_stats.get('cached_users', 0)}\n"
                    f"• Активных пресетов: {repo_stats.get('active_presets', 0)}\n"
                )
        
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
        text = "🏠 <b>Главное меню</b>\n\n"
        
        # Получаем статистику Price Alerts если доступен
        if self.price_alerts_service:
            try:
                stats = self.price_alerts_service.get_statistics()
                text += (
                    f"📊 <b>Статистика Price Alerts:</b>\n"
                    f"• Отслеживаемых символов: {stats.get('monitored_symbols', 0)}\n"
                    f"• Алертов отправлено: {stats.get('alerts_triggered', 0)}\n\n"
                )
            except Exception as e:
                logger.error(f"Error getting PA stats: {e}")
        
        text += "🎯 Выберите модуль для работы:"
        
        keyboard = self.keyboards.get_main_menu_keyboard()
        await callback.message.edit_text(text, reply_markup=keyboard, parse_mode="HTML")
        await callback.answer()
    
    # ОБРАБОТЧИКИ МОДУЛЕЙ
    
    async def show_price_alerts_menu(self, callback: types.CallbackQuery):
        """Показ меню Price Alerts."""
        if not self.price_alerts_service:
            await callback.answer("❌ Сервис Price Alerts недоступен")
            return
        
        # Получаем статистику
        stats = self.price_alerts_service.get_statistics()
        
        text = (
            "📈 <b>Price Alerts</b>\n\n"
            "🚀 <b>Система мониторинга цен в реальном времени</b>\n\n"
            
            f"📊 <b>Статистика системы:</b>\n"
            f"• Статус: {'🟢 Работает' if stats.get('running', False) else '🔴 Остановлен'}\n"
            f"• Отслеживаемых символов: {stats.get('monitored_symbols', 0)}\n"
            f"• Цен в кеше: {stats.get('current_prices_count', 0)}\n"
            f"• Алертов отправлено: {stats.get('alerts_triggered', 0)}\n\n"
            
            "🎯 <b>Возможности:</b>\n"
            "• Создание пресетов для групп токенов\n"
            "• Мониторинг множества пар одновременно\n" 
            "• Настройка процента изменения\n"
            "• Различные таймфреймы\n"
            "• Встроенное кеширование\n\n"
            
            "⚡ Что хотите сделать?"
        )
        
        builder = InlineKeyboardBuilder()
        builder.button(text="📋 Перейти к Price Alerts", callback_data="price_alerts")
        builder.button(text="📊 Текущие цены", callback_data="price_current_prices")
        builder.button(text="📈 Подробная статистика", callback_data="price_statistics")
        builder.button(text="ℹ️ Справка", callback_data="price_help_info")
        builder.button(text="◀️ Назад", callback_data="main_menu")
        builder.adjust(1)
        
        await callback.message.edit_text(text, reply_markup=builder.as_markup(), parse_mode="HTML")
        await callback.answer()
    
    async def show_gas_tracker_menu(self, callback: types.CallbackQuery):
        """Показ меню Gas Tracker."""
        text = (
            "⛽ <b>Gas Tracker</b>\n"
            "<i>Модуль в разработке</i>\n\n"
            
            "🚧 <b>Планируемый функционал:</b>\n"
            "• Мониторинг цен газа Ethereum\n"
            "• Уведомления при достижении порогов\n"
            "• Исторические данные\n"
            "• Рекомендации по оптимальному времени\n\n"
            
            "📅 <b>Статус:</b> В разработке\n"
            "🕐 <b>Планируемый релиз:</b> Скоро"
        )
        
        builder = InlineKeyboardBuilder()
        builder.button(text="📈 Попробовать Price Alerts", callback_data="price_alerts")
        builder.button(text="◀️ Назад", callback_data="main_menu")
        builder.adjust(1)
        
        await callback.message.edit_text(text, reply_markup=builder.as_markup(), parse_mode="HTML")
        await callback.answer()
    
    async def show_whale_tracker_menu(self, callback: types.CallbackQuery):
        """Показ меню Whale Tracker."""
        text = (
            "🐋 <b>Whale Tracker</b>\n"
            "<i>Модуль в разработке</i>\n\n"
            
            "🚧 <b>Планируемый функционал:</b>\n"
            "• Отслеживание крупных транзакций\n"
            "• Анализ движений китов\n"
            "• Уведомления о значительных переводах\n"
            "• Статистика по кошелькам\n\n"
            
            "📅 <b>Статус:</b> В разработке\n"
            "🕐 <b>Планируемый релиз:</b> Скоро"
        )
        
        builder = InlineKeyboardBuilder()
        builder.button(text="📈 Попробовать Price Alerts", callback_data="price_alerts")
        builder.button(text="◀️ Назад", callback_data="main_menu")
        builder.adjust(1)
        
        await callback.message.edit_text(text, reply_markup=builder.as_markup(), parse_mode="HTML")
        await callback.answer()
    
    async def show_wallet_tracker_menu(self, callback: types.CallbackQuery):
        """Показ меню Wallet Tracker."""
        text = (
            "👛 <b>Wallet Tracker</b>\n"
            "<i>Модуль в разработке</i>\n\n"
            
            "🚧 <b>Планируемый функционал:</b>\n"
            "• Мониторинг кошельков\n"
            "• Уведомления о транзакциях\n"
            "• Отслеживание балансов\n"
            "• Анализ активности\n\n"
            
            "📅 <b>Статус:</b> В разработке\n"
            "🕐 <b>Планируемый релиз:</b> Скоро"
        )
        
        builder = InlineKeyboardBuilder()
        builder.button(text="📈 Попробовать Price Alerts", callback_data="price_alerts")
        builder.button(text="◀️ Назад", callback_data="main_menu")
        builder.adjust(1)
        
        await callback.message.edit_text(text, reply_markup=builder.as_markup(), parse_mode="HTML")
        await callback.answer()
    
    async def show_settings(self, callback: types.CallbackQuery):
        """Показ настроек."""
        text = (
            "⚙️ <b>Настройки</b>\n\n"
            
            "🔧 <b>Системные настройки:</b>\n"
            "• Архитектура: Модульная v2.0\n"
            "• Кеширование: Встроенное\n"
            "• События: Упрощенная система\n\n"
            
            "📈 <b>Price Alerts:</b>\n"
            "• Статус: Активен\n"
            "• Кеш: Встроен в репозиторий\n"
            "• API: Binance (бесплатный)\n\n"
            
            "🎛️ Управление:"
        )
        
        builder = InlineKeyboardBuilder()
        builder.button(text="📊 Моя статистика", callback_data="settings_stats")
        builder.button(text="🔧 Техническая информация", callback_data="about_tech")
        builder.button(text="◀️ Назад", callback_data="main_menu")
        builder.adjust(1)
        
        await callback.message.edit_text(text, reply_markup=builder.as_markup(), parse_mode="HTML")
        await callback.answer()
    
    async def show_about(self, callback: types.CallbackQuery):
        """Показ информации о боте."""
        # Получаем статистику системы
        event_stats = event_bus.get_stats()
        
        text = (
            "ℹ️ <b>О Crypto Monitor Bot v2.0</b>\n\n"
            
            "🤖 <b>Версия:</b> 2.0.0 (Refactored)\n"
            "📅 <b>Обновлено:</b> Декабрь 2024\n"
            "👨‍💻 <b>Архитектура:</b> Модульная система\n\n"
            
            "📋 <b>Активные модули:</b>\n"
            "✅ Price Alerts - Полный функционал\n"
            "🚧 Gas Tracker - В разработке\n"
            "🚧 Whale Tracker - В разработке\n"
            "🚧 Wallet Tracker - В разработке\n\n"
            
            "🔧 <b>Технические улучшения v2.0:</b>\n"
            f"• Обработчиков событий: {event_stats.get('total_handlers', 0)}\n"
            f"• Типов событий: {event_stats.get('event_types', 0)}\n"
            "• Встроенное кеширование в репозиториях\n"
            "• Упрощенная архитектура\n"
            "• Модульная изоляция\n\n"
            
            "🚀 <b>Ключевые изменения v2.0:</b>\n"
            "• Реструктурирован весь проект\n"
            "• Кеш встроен в репозитории\n"
            "• Упрощена система событий\n"
            "• Убрана избыточность кода\n"
            "• Улучшена производительность\n\n"
            
            "💡 <b>Планы развития:</b>\n"
            "• Завершение всех модулей\n"
            "• Дополнительные API интеграции\n"
            "• Расширенная аналитика\n\n"
            
            f"⏰ <b>Время работы:</b> {datetime.now().strftime('%d.%m.%Y %H:%M')}"
        )
        
        builder = InlineKeyboardBuilder()
        builder.button(text="📝 Changelog", callback_data="about_changelog")
        builder.button(text="🔧 Техническая информация", callback_data="about_tech")
        builder.button(text="📊 Статистика системы", callback_data="cmd_status")
        builder.button(text="◀️ Назад", callback_data="main_menu")
        builder.adjust(2, 1, 1)
        
        await callback.message.edit_text(text, reply_markup=builder.as_markup(), parse_mode="HTML")
        await callback.answer()
    
    # ДОПОЛНИТЕЛЬНЫЕ ОБРАБОТЧИКИ
    
    async def toggle_notifications(self, callback: types.CallbackQuery):
        """Переключение уведомлений."""
        await callback.answer("🔔 Уведомления управляются через настройки Price Alerts")
        await self.show_settings(callback)
    
    async def show_user_stats(self, callback: types.CallbackQuery):
        """Показ пользовательской статистики."""
        user_id = callback.from_user.id
        
        text = (
            f"📊 <b>Статистика пользователя</b>\n\n"
            
            f"👤 <b>Профиль:</b>\n"
            f"• ID: {user_id}\n"
            f"• Имя: {callback.from_user.first_name or 'Не указано'}\n"
            f"• Username: @{callback.from_user.username or 'не указан'}\n\n"
        )
        
        # Добавляем статистику Price Alerts если доступен
        if self.price_alerts_service:
            try:
                # Получаем пресеты пользователя через событие
                await event_bus.publish(Event(
                    type="price_alerts.get_user_presets",
                    data={"user_id": user_id},
                    source_module="telegram"
                ))
                
                text += (
                    f"📈 <b>Price Alerts:</b>\n"
                    f"• Загружаем данные...\n\n"
                )
            except Exception as e:
                logger.error(f"Error getting user stats: {e}")
                text += "📈 <b>Price Alerts:</b> Данные недоступны\n\n"
        
        text += f"📅 <b>Дата регистрации:</b> {datetime.now().strftime('%d.%m.%Y')}"
        
        builder = InlineKeyboardBuilder()
        builder.button(text="🔄 Обновить", callback_data="settings_stats")
        builder.button(text="◀️ Назад", callback_data="settings")
        builder.adjust(1)
        
        await callback.message.edit_text(text, reply_markup=builder.as_markup(), parse_mode="HTML")
        await callback.answer()
    
    async def show_changelog(self, callback: types.CallbackQuery):
        """Показ истории изменений."""
        text = (
            "📝 <b>История изменений</b>\n\n"
            
            "<b>🚀 Версия 2.0.0</b> (Декабрь 2024)\n"
            "• Полная реструктуризация проекта\n"
            "• Модульная архитектура\n"
            "• Кеш встроен в репозитории\n"
            "• Упрощена система событий\n"
            "• Убрана избыточность кода\n"
            "• Улучшена производительность\n"
            "• Alert dispatcher встроен в Telegram\n"
            "• Token manager выделен в отдельный модуль\n\n"
            
            "<b>📈 Архитектурные изменения:</b>\n"
            "• config/ - модульные настройки\n"
            "• core/ - только общие компоненты\n"
            "• shared/ - минимальный набор утилит\n"
            "• modules/ - самодостаточные модули\n\n"
            
            "<b>🔧 Технические улучшения:</b>\n"
            "• PriceAlertsRepository с встроенным кешем\n"
            "• Упрощенный EventBus без circuit breaker\n"
            "• Все handlers в telegram модуле\n"
            "• Изоляция модулей\n\n"
            
            "<b>📋 Сохранена функциональность:</b>\n"
            "• Price Alerts работает полностью\n"
            "• Все кнопки и команды функциональны\n"
            "• Telegram интерфейс не изменился\n"
            "• API интеграции сохранены"
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
        
        text = (
            "🔧 <b>Техническая информация v2.0</b>\n\n"
            
            "<b>🏗️ Новая архитектура:</b>\n"
            "• Модульная система\n"
            "• Встроенное кеширование\n"
            "• Упрощенная Event система\n"
            "• Изоляция компонентов\n"
            "• Отказ от сложных абстракций\n\n"
            
            "<b>📡 Event System:</b>\n"
            f"• Типов событий: {event_stats.get('event_types', 0)}\n"
            f"• Обработчиков: {event_stats.get('total_handlers', 0)}\n"
            f"• Статус: {'🟢 Работает' if event_stats.get('running', False) else '🔴 Остановлен'}\n\n"
        )
        
        # Добавляем статистику Price Alerts
        if self.price_alerts_service:
            pa_stats = self.price_alerts_service.get_statistics()
            repo_stats = pa_stats.get('repository_stats', {})
            
            text += (
                "<b>📈 Price Alerts:</b>\n"
                f"• Статус: {'🟢 Работает' if pa_stats.get('running', False) else '🔴 Остановлен'}\n"
                f"• Отслеживаемых символов: {pa_stats.get('monitored_symbols', 0)}\n"
                f"• API вызовов: {pa_stats.get('api_calls', 0)}\n"
                f"• Среднее время ответа: {pa_stats.get('avg_response_time', 0):.3f}с\n\n"
                
                "<b>💾 Встроенный кеш:</b>\n"
                f"• Кешированных пользователей: {repo_stats.get('cached_users', 0)}\n"
                f"• Всего пресетов в кеше: {repo_stats.get('total_cached_presets', 0)}\n"
                f"• Активных пресетов: {repo_stats.get('active_presets', 0)}\n"
            )
        
        text += (
            "\n<b>🛡️ Упрощения v2.0:</b>\n"
            "• Убран сложный кеш-менеджер\n"
            "• Убраны circuit breakers из событий\n"
            "• Упрощены репозитории\n"
            "• Объединены модели в один файл\n"
            "• Минимизированы зависимости"
        )
        
        builder = InlineKeyboardBuilder()
        builder.button(text="📊 Подробная статистика", callback_data="cmd_status")
        builder.button(text="📝 Changelog", callback_data="about_changelog")
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
            await callback.answer("🔄 Функция перезапуска недоступна")
        elif action == "logs":
            await callback.answer("📋 Логи доступны в консоли сервера")
        else:
            await callback.answer("❌ Неизвестное действие")
    
    async def _show_detailed_status(self, callback: types.CallbackQuery):
        """Детальный статус системы."""
        event_stats = event_bus.get_stats()
        
        text = (
            "📊 <b>Детальный статус системы</b>\n\n"
            
            "<b>📡 Event Bus:</b>\n"
            f"• Статус: {'🟢 Работает' if event_stats.get('running', False) else '🔴 Остановлен'}\n"
            f"• Обработчиков: {event_stats.get('total_handlers', 0)}\n"
            f"• Типов событий: {event_stats.get('event_types', 0)}\n"
        )
        
        subscribers = event_stats.get('subscribers', {})
        if subscribers:
            text += "\n<b>📋 Подписчики событий:</b>\n"
            for event_type, count in list(subscribers.items())[:5]:  # Показываем первые 5
                text += f"• {event_type}: {count}\n"
            
            if len(subscribers) > 5:
                text += f"• ... и еще {len(subscribers) - 5} типов\n"
        
        # Статистика Price Alerts если доступен
        if self.price_alerts_service:
            pa_stats = self.price_alerts_service.get_statistics()
            text += (
                f"\n<b>📈 Price Alerts детально:</b>\n"
                f"• Обновлений цен: {pa_stats.get('total_updates', 0)}\n"
                f"• Неудачных обновлений: {pa_stats.get('failed_updates', 0)}\n"
                f"• Алертов отправлено: {pa_stats.get('alerts_triggered', 0)}\n"
            )
        
        builder = InlineKeyboardBuilder()
        builder.button(text="🔄 Обновить", callback_data="status_details")
        builder.button(text="◀️ Назад", callback_data="cmd_status")
        builder.adjust(1)
        
        await callback.message.edit_text(text, reply_markup=builder.as_markup(), parse_mode="HTML")
        await callback.answer()
    
    async def about_roadmap(self, callback: types.CallbackQuery):
        """Показ планов развития."""
        text = (
            "🔮 <b>Планы развития</b>\n\n"
            
            "<b>📅 Ближайшие планы:</b>\n"
            "• Завершение Gas Tracker модуля\n"
            "• Добавление Whale Tracker функционала\n"
            "• Реализация Wallet Tracker\n"
            "• Интеграция с premium API\n\n"
            
            "<b>🚀 Среднесрочные цели:</b>\n"
            "• Расширенная аналитика\n"
            "• Дополнительные биржи\n"
            "• Мобильные уведомления\n"
            "• Экспорт данных\n\n"
            
            "<b>💡 Долгосрочное видение:</b>\n"
            "• Мультиплатформенность\n"
            "• Машинное обучение для прогнозов\n"
            "• Социальные функции\n"
            "• API для разработчиков\n\n"
            
            "🎯 Архитектура v2.0 подготовлена для всех этих улучшений!"
        )
        
        builder = InlineKeyboardBuilder()
        builder.button(text="📈 Попробовать Price Alerts", callback_data="price_alerts")
        builder.button(text="◀️ Назад", callback_data="about")
        builder.adjust(1)
        
        await callback.message.edit_text(text, reply_markup=builder.as_markup(), parse_mode="HTML")
        await callback.answer()
    
    async def price_help_info(self, callback: types.CallbackQuery):
        """Справка по Price Alerts."""
        text = (
            "ℹ️ <b>Справка по Price Alerts</b>\n\n"
            
            "📝 <b>Как создать пресет:</b>\n"
            "1. Нажмите 'Перейти к Price Alerts'\n"
            "2. Выберите 'Создать пресет'\n"
            "3. Следуйте шагам мастера\n\n"
            
            "🎯 <b>Советы по настройке:</b>\n"
            "• Процент 1-2% - много сигналов\n"
            "• Процент 3-5% - оптимально\n"
            "• Процент 10%+ - только крупные движения\n\n"
            
            "⏰ <b>Таймфреймы:</b>\n"
            "• 1m/5m - для скальпинга\n"
            "• 15m/1h - для обычной торговли\n"
            "• 4h/1d - для долгосрочных позиций\n\n"
            
            "🔔 Уведомления приходят мгновенно при достижении условий!"
        )
        
        builder = InlineKeyboardBuilder()
        builder.button(text="📈 Перейти к Price Alerts", callback_data="price_alerts")
        builder.button(text="◀️ Назад", callback_data="price_alerts")
        builder.adjust(1)
        
        await callback.message.edit_text(text, reply_markup=builder.as_markup(), parse_mode="HTML")
        await callback.answer()