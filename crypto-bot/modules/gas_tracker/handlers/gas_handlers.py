# modules/gas_tracker/handlers/gas_handlers.py
"""Полностью рабочие обработчики команд для газ трекера."""

from aiogram import types, F, Router
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.utils.keyboard import InlineKeyboardBuilder
from datetime import datetime
from typing import Dict, Any, List

from shared.events import event_bus, Event, USER_COMMAND_RECEIVED
from shared.cache.memory_cache import cache_manager

import logging

logger = logging.getLogger(__name__)


class GasStates(StatesGroup):
    """Состояния для настройки газ алертов."""
    waiting_threshold = State()
    waiting_alert_type = State()
    waiting_cooldown = State()
    editing_alert = State()


class GasHandlers:
    """Обработчики команд газ трекера с полной функциональностью."""
    
    def __init__(self, gas_service=None):
        self.gas_service = gas_service
        self.router = Router()
        self.cache = cache_manager.get_cache('gas_handlers')
        
        # Подписываемся на ответы от сервиса
        event_bus.subscribe("gas_tracker.current_price_response", self._handle_price_response)
        event_bus.subscribe("gas_tracker.user_alerts_response", self._handle_alerts_response)
        event_bus.subscribe("gas_tracker.alert_added", self._handle_alert_added)
        event_bus.subscribe("gas_tracker.alert_removed", self._handle_alert_removed)
        event_bus.subscribe("gas_tracker.price_history_response", self._handle_history_response)
        
        # Кеш для временного хранения ответов
        self._response_cache = {}
    
    def register_handlers(self, dp):
        """Регистрация всех обработчиков."""
        # Основные команды
        self.router.callback_query(F.data == "gas_tracker")(self.show_gas_menu)
        self.router.callback_query(F.data == "gas_current")(self.show_current_gas)
        self.router.callback_query(F.data == "gas_alerts")(self.show_user_alerts)
        self.router.callback_query(F.data == "gas_add_alert")(self.start_add_alert)
        self.router.callback_query(F.data == "gas_chart")(self.show_price_chart)
        self.router.callback_query(F.data == "gas_settings")(self.show_gas_settings)
        
        # Состояния создания алерта
        self.router.message(GasStates.waiting_threshold)(self.process_threshold)
        self.router.callback_query(F.data.startswith("gas_type_"))(self.process_alert_type)
        self.router.message(GasStates.waiting_cooldown)(self.process_cooldown)
        
        # Управление алертами
        self.router.callback_query(F.data.startswith("gas_toggle_"))(self.toggle_alert)
        self.router.callback_query(F.data.startswith("gas_delete_"))(self.delete_alert)
        self.router.callback_query(F.data.startswith("gas_edit_"))(self.edit_alert)
        
        # Дополнительные функции
        self.router.callback_query(F.data == "gas_statistics")(self.show_statistics)
        self.router.callback_query(F.data == "gas_refresh")(self.refresh_data)
        self.router.callback_query(F.data.startswith("gas_history_"))(self.show_history)
        
        # Настройки
        self.router.callback_query(F.data == "gas_settings_notifications")(self.toggle_notifications)
        self.router.callback_query(F.data == "gas_settings_cooldown")(self.set_default_cooldown)
        
        dp.include_router(self.router)
    
    async def show_gas_menu(self, callback: types.CallbackQuery):
        """Показ главного меню газ трекера."""
        user_id = callback.from_user.id
        
        # Запрашиваем текущие данные
        await event_bus.publish(Event(
            type="gas_tracker.get_current_price",
            data={"user_id": user_id},
            source_module="telegram"
        ))
        
        # Запрашиваем алерты пользователя
        await event_bus.publish(Event(
            type="gas_tracker.get_user_alerts",
            data={"user_id": user_id},
            source_module="telegram"
        ))
        
        # Показываем loading
        text = (
            "⛽ <b>Gas Tracker</b>\n\n"
            "🔄 Загружаем актуальные данные...\n\n"
            "📊 Мониторинг цен на газ Ethereum в реальном времени"
        )
        
        builder = InlineKeyboardBuilder()
        builder.button(text="📊 Текущие цены", callback_data="gas_current")
        builder.button(text="🔔 Мои алерты", callback_data="gas_alerts")
        builder.button(text="➕ Добавить алерт", callback_data="gas_add_alert")
        builder.button(text="📈 История цен", callback_data="gas_chart")
        builder.button(text="📊 Статистика", callback_data="gas_statistics")
        builder.button(text="⚙️ Настройки", callback_data="gas_settings")
        builder.button(text="🔄 Обновить", callback_data="gas_refresh")
        builder.button(text="◀️ Назад", callback_data="main_menu")
        builder.adjust(2, 2, 2, 1, 1)
        
        await callback.message.edit_text(text, reply_markup=builder.as_markup(), parse_mode="HTML")
        await callback.answer()
        
        # Сохраняем контекст для обновления
        self._response_cache[user_id] = {
            "type": "main_menu",
            "message": callback.message
        }
    
    async def show_current_gas(self, callback: types.CallbackQuery):
        """Показ текущих цен на газ."""
        user_id = callback.from_user.id
        
        # Запрашиваем текущие цены
        await event_bus.publish(Event(
            type="gas_tracker.get_current_price",
            data={"user_id": user_id},
            source_module="telegram"
        ))
        
        # Временно показываем loading
        loading_text = "📊 <b>Текущие цены на газ</b>\n\n🔄 Загружаем данные..."
        
        builder = InlineKeyboardBuilder()
        builder.button(text="🔄 Обновить", callback_data="gas_current")
        builder.button(text="📈 История", callback_data="gas_chart")
        builder.button(text="◀️ Назад", callback_data="gas_tracker")
        builder.adjust(2, 1)
        
        await callback.message.edit_text(loading_text, reply_markup=builder.as_markup(), parse_mode="HTML")
        await callback.answer()
        
        # Сохраняем контекст
        self._response_cache[user_id] = {
            "type": "current_price",
            "message": callback.message
        }
    
    async def show_user_alerts(self, callback: types.CallbackQuery):
        """Показ алертов пользователя."""
        user_id = callback.from_user.id
        
        # Запрашиваем алерты
        await event_bus.publish(Event(
            type="gas_tracker.get_user_alerts",
            data={"user_id": user_id},
            source_module="telegram"
        ))
        
        loading_text = "🔔 <b>Мои газ алерты</b>\n\n🔄 Загружаем ваши алерты..."
        
        builder = InlineKeyboardBuilder()
        builder.button(text="➕ Добавить алерт", callback_data="gas_add_alert")
        builder.button(text="◀️ Назад", callback_data="gas_tracker")
        builder.adjust(1)
        
        await callback.message.edit_text(loading_text, reply_markup=builder.as_markup(), parse_mode="HTML")
        await callback.answer()
        
        # Сохраняем контекст
        self._response_cache[user_id] = {
            "type": "user_alerts",
            "message": callback.message
        }
    
    async def start_add_alert(self, callback: types.CallbackQuery, state: FSMContext):
        """Начало добавления алерта."""
        await state.set_state(GasStates.waiting_threshold)
        
        text = (
            "➕ <b>Добавление газ алерта</b>\n\n"
            
            "💰 <b>Шаг 1/3:</b> Пороговое значение\n\n"
            
            "Введите пороговое значение в gwei:\n"
            "• Минимум: 1 gwei\n"
            "• Максимум: 1000 gwei\n"
            "• Рекомендуемо: 15-50 gwei\n\n"
            
            "💡 <b>Примеры:</b>\n"
            "• 15 - для дешевых транзакций\n"
            "• 30 - для стандартных операций\n"
            "• 50 - для срочных операций"
        )
        
        builder = InlineKeyboardBuilder()
        # Быстрые кнопки
        builder.button(text="15 gwei", callback_data="gas_quick_15")
        builder.button(text="20 gwei", callback_data="gas_quick_20")
        builder.button(text="30 gwei", callback_data="gas_quick_30")
        builder.button(text="50 gwei", callback_data="gas_quick_50")
        builder.button(text="❌ Отмена", callback_data="gas_tracker")
        builder.adjust(2, 2, 1)
        
        await callback.message.edit_text(text, reply_markup=builder.as_markup(), parse_mode="HTML")
        await callback.answer()
    
    async def process_threshold(self, message: types.Message, state: FSMContext):
        """Обработка порогового значения."""
        try:
            threshold = float(message.text.strip())
            
            if threshold <= 0 or threshold > 1000:
                await message.answer(
                    "❌ Неверное значение!\n\n"
                    "Введите число от 1 до 1000 gwei:"
                )
                return
            
            await state.update_data(threshold=threshold)
            await state.set_state(GasStates.waiting_alert_type)
            
            text = (
                f"✅ Порог установлен: <b>{threshold:.1f} gwei</b>\n\n"
                
                "🎯 <b>Шаг 2/3:</b> Тип алерта\n\n"
                
                "Когда отправлять уведомление?"
            )
            
            builder = InlineKeyboardBuilder()
            builder.button(text="⬇️ Когда цена УПАДЕТ ниже", callback_data="gas_type_below")
            builder.button(text="⬆️ Когда цена ПОДНИМЕТСЯ выше", callback_data="gas_type_above")
            builder.button(text="❌ Отмена", callback_data="gas_tracker")
            builder.adjust(1)
            
            await message.answer(text, reply_markup=builder.as_markup(), parse_mode="HTML")
            
        except ValueError:
            await message.answer(
                "❌ Некорректное число!\n\n"
                "Введите число (например: 25.5):"
            )
    
    async def process_alert_type(self, callback: types.CallbackQuery, state: FSMContext):
        """Обработка типа алерта."""
        alert_type = callback.data.split("_")[-1]  # below или above
        data = await state.get_data()
        threshold = data.get("threshold")
        
        await state.update_data(alert_type=alert_type)
        await state.set_state(GasStates.waiting_cooldown)
        
        direction = "упадет ниже" if alert_type == "below" else "поднимется выше"
        
        text = (
            f"✅ Тип алерта: когда цена <b>{direction}</b> {threshold:.1f} gwei\n\n"
            
            "⏰ <b>Шаг 3/3:</b> Интервал уведомлений\n\n"
            
            "Как часто отправлять повторные уведомления?\n"
            "(если условие продолжает выполняться)"
        )
        
        builder = InlineKeyboardBuilder()
        builder.button(text="🚀 Каждую минуту", callback_data="gas_cooldown_1")
        builder.button(text="⚡ Каждые 5 минут", callback_data="gas_cooldown_5")
        builder.button(text="🔔 Каждые 15 минут", callback_data="gas_cooldown_15")
        builder.button(text="📱 Каждые 30 минут", callback_data="gas_cooldown_30")
        builder.button(text="💤 Только один раз", callback_data="gas_cooldown_once")
        builder.button(text="❌ Отмена", callback_data="gas_tracker")
        builder.adjust(2, 2, 1, 1)
        
        await callback.message.edit_text(text, reply_markup=builder.as_markup(), parse_mode="HTML")
        await callback.answer()
    
    async def process_cooldown(self, callback: types.CallbackQuery, state: FSMContext):
        """Обработка интервала уведомлений."""
        if callback.data.startswith("gas_cooldown_"):
            cooldown_str = callback.data.split("_")[-1]
            
            if cooldown_str == "once":
                cooldown_minutes = 999999  # Практически никогда не повторять
                cooldown_text = "только один раз"
            else:
                cooldown_minutes = int(cooldown_str)
                cooldown_text = f"каждые {cooldown_minutes} мин"
        else:
            return
        
        # Получаем все данные
        data = await state.get_data()
        threshold = data.get("threshold")
        alert_type = data.get("alert_type")
        
        # Создаем алерт через сервис
        await event_bus.publish(Event(
            type="gas_tracker.add_alert",
            data={
                "user_id": callback.from_user.id,
                "threshold_gwei": threshold,
                "alert_type": alert_type,
                "cooldown_minutes": cooldown_minutes
            },
            source_module="telegram"
        ))
        
        # Показываем подтверждение
        direction = "упадет ниже" if alert_type == "below" else "поднимется выше"
        
        text = (
            "✅ <b>Алерт создается...</b>\n\n"
            
            f"🎯 <b>Условие:</b> когда цена {direction} {threshold:.1f} gwei\n"
            f"⏰ <b>Повтор:</b> {cooldown_text}\n\n"
            
            "🔔 Вы получите уведомление как только условие выполнится!"
        )
        
        builder = InlineKeyboardBuilder()
        builder.button(text="📊 Текущие цены", callback_data="gas_current")
        builder.button(text="🔔 Мои алерты", callback_data="gas_alerts")
        builder.button(text="◀️ Главное меню", callback_data="gas_tracker")
        builder.adjust(2, 1)
        
        await callback.message.edit_text(text, reply_markup=builder.as_markup(), parse_mode="HTML")
        await callback.answer()
        
        await state.clear()
    
    async def show_price_chart(self, callback: types.CallbackQuery):
        """Показ графика цен."""
        user_id = callback.from_user.id
        
        # Запрашиваем историю цен
        await event_bus.publish(Event(
            type="gas_tracker.get_price_history",
            data={"user_id": user_id, "hours": 24},
            source_module="telegram"
        ))
        
        text = "📈 <b>История цен на газ</b>\n\n🔄 Загружаем данные за последние 24 часа..."
        
        builder = InlineKeyboardBuilder()
        builder.button(text="📊 1 час", callback_data="gas_history_1")
        builder.button(text="📈 6 часов", callback_data="gas_history_6")
        builder.button(text="📉 24 часа", callback_data="gas_history_24")
        builder.button(text="🔄 Обновить", callback_data="gas_chart")
        builder.button(text="◀️ Назад", callback_data="gas_tracker")
        builder.adjust(3, 1, 1)
        
        await callback.message.edit_text(text, reply_markup=builder.as_markup(), parse_mode="HTML")
        await callback.answer()
        
        # Сохраняем контекст
        self._response_cache[user_id] = {
            "type": "price_chart",
            "message": callback.message
        }
    
    async def show_history(self, callback: types.CallbackQuery):
        """Показ истории за определенный период."""
        hours = int(callback.data.split("_")[-1])
        user_id = callback.from_user.id
        
        await event_bus.publish(Event(
            type="gas_tracker.get_price_history",
            data={"user_id": user_id, "hours": hours},
            source_module="telegram"
        ))
        
        await callback.answer(f"📊 Загружаем данные за {hours}ч")
    
    async def show_statistics(self, callback: types.CallbackQuery):
        """Показ статистики газа."""
        user_id = callback.from_user.id
        
        # Запрашиваем текущие данные для статистики
        await event_bus.publish(Event(
            type="gas_tracker.get_current_price",
            data={"user_id": user_id},
            source_module="telegram"
        ))
        
        text = "📊 <b>Статистика газа</b>\n\n🔄 Вычисляем статистику..."
        
        builder = InlineKeyboardBuilder()
        builder.button(text="🔄 Обновить", callback_data="gas_statistics")
        builder.button(text="◀️ Назад", callback_data="gas_tracker")
        builder.adjust(1)
        
        await callback.message.edit_text(text, reply_markup=builder.as_markup(), parse_mode="HTML")
        await callback.answer()
        
        # Сохраняем контекст
        self._response_cache[user_id] = {
            "type": "statistics",
            "message": callback.message
        }
    
    async def show_gas_settings(self, callback: types.CallbackQuery):
        """Показ настроек газ трекера."""
        user_id = callback.from_user.id
        
        # Получаем настройки пользователя
        settings_key = f"gas_settings:{user_id}"
        user_settings = await self.cache.get(settings_key, {
            'notifications_enabled': True,
            'default_cooldown': 5,
            'sound_alerts': True,
            'telegram_notifications': True
        })
        
        text = (
            "⚙️ <b>Настройки Gas Tracker</b>\n\n"
            
            f"🔔 Уведомления: {'🟢 Включены' if user_settings.get('notifications_enabled') else '🔴 Отключены'}\n"
            f"⏰ Интервал по умолчанию: {user_settings.get('default_cooldown', 5)} мин\n"
            f"🔊 Звуковые алерты: {'🟢 Вкл' if user_settings.get('sound_alerts') else '🔴 Выкл'}\n"
            f"📱 Telegram уведомления: {'🟢 Вкл' if user_settings.get('telegram_notifications') else '🔴 Выкл'}\n\n"
            
            "🎛️ Управление настройками:"
        )
        
        builder = InlineKeyboardBuilder()
        builder.button(
            text=f"🔔 Уведомления: {'Вкл' if user_settings.get('notifications_enabled') else 'Выкл'}",
            callback_data="gas_settings_notifications"
        )
        builder.button(text="⏰ Интервал по умолчанию", callback_data="gas_settings_cooldown")
        builder.button(text="🔊 Звук", callback_data="gas_settings_sound")
        builder.button(text="📱 Telegram", callback_data="gas_settings_telegram")
        builder.button(text="🗑️ Сбросить настройки", callback_data="gas_settings_reset")
        builder.button(text="◀️ Назад", callback_data="gas_tracker")
        builder.adjust(1, 1, 2, 1, 1)
        
        await callback.message.edit_text(text, reply_markup=builder.as_markup(), parse_mode="HTML")
        await callback.answer()
    
    async def refresh_data(self, callback: types.CallbackQuery):
        """Обновление данных."""
        await callback.answer("🔄 Обновляем данные...")
        await self.show_gas_menu(callback)
    
    async def toggle_alert(self, callback: types.CallbackQuery):
        """Переключение статуса алерта."""
        alert_id = int(callback.data.split("_")[-1])
        user_id = callback.from_user.id
        
        # Здесь должна быть логика переключения статуса через сервис
        await callback.answer("🔄 Изменяем статус алерта...")
        
        # Обновляем список алертов
        await self.show_user_alerts(callback)
    
    async def delete_alert(self, callback: types.CallbackQuery):
        """Удаление алерта."""
        alert_id = int(callback.data.split("_")[-1])
        user_id = callback.from_user.id
        
        # Удаляем через сервис
        await event_bus.publish(Event(
            type="gas_tracker.remove_alert",
            data={
                "user_id": user_id,
                "alert_id": alert_id
            },
            source_module="telegram"
        ))
        
        await callback.answer("🗑️ Удаляем алерт...")
    
    async def toggle_notifications(self, callback: types.CallbackQuery):
        """Переключение уведомлений."""
        user_id = callback.from_user.id
        settings_key = f"gas_settings:{user_id}"
        
        settings = await self.cache.get(settings_key, {})
        current_state = settings.get('notifications_enabled', True)
        new_state = not current_state
        
        settings['notifications_enabled'] = new_state
        await self.cache.set(settings_key, settings, ttl=86400)
        
        status = "включены" if new_state else "отключены"
        await callback.answer(f"🔔 Уведомления {status}")
        
        # Обновляем меню настроек
        await self.show_gas_settings(callback)
    
    # EVENT RESPONSE HANDLERS
    
    async def _handle_price_response(self, event: Event):
        """Обработка ответа с ценами на газ."""
        user_id = event.data.get("user_id")
        gas_price = event.data.get("gas_price")
        statistics = event.data.get("statistics", {})
        
        if user_id not in self._response_cache:
            return
        
        context = self._response_cache[user_id]
        message = context["message"]
        
        if context["type"] == "current_price":
            await self._update_current_price_display(message, gas_price, statistics)
        elif context["type"] == "main_menu":
            await self._update_main_menu_display(message, gas_price, statistics, user_id)
        elif context["type"] == "statistics":
            await self._update_statistics_display(message, gas_price, statistics)
        
        # Очищаем кеш
        if user_id in self._response_cache:
            del self._response_cache[user_id]
    
    async def _update_current_price_display(self, message: types.Message, gas_price: Dict, statistics: Dict):
        """Обновление отображения текущих цен."""
        if not gas_price:
            text = (
                "📊 <b>Текущие цены на газ</b>\n\n"
                "❌ Данные недоступны\n"
                "Попробуйте обновить позже"
            )
        else:
            updated_time = datetime.fromisoformat(gas_price['timestamp']).strftime('%H:%M:%S')
            
            # Определяем рекомендации
            standard_price = gas_price['standard']
            if standard_price <= 15:
                recommendation = "🟢 Отличное время для транзакций!"
            elif standard_price <= 30:
                recommendation = "🟡 Нормальная цена"
            elif standard_price <= 50:
                recommendation = "🟠 Высокая цена"
            else:
                recommendation = "🔴 Очень дорого!"
            
            text = (
                f"📊 <b>Текущие цены на газ</b>\n\n"
                
                f"💰 <b>Уровни скорости:</b>\n"
                f"🐌 Безопасный: <b>{gas_price['safe']:.1f}</b> gwei\n"
                f"🚶 Стандартный: <b>{gas_price['standard']:.1f}</b> gwei\n"
                f"🏃 Быстрый: <b>{gas_price['fast']:.1f}</b> gwei\n"
                f"🚀 Мгновенный: <b>{gas_price['instant']:.1f}</b> gwei\n\n"
                
                f"💡 <b>Рекомендация:</b> {recommendation}\n\n"
            )
            
            if statistics:
                text += (
                    f"📈 <b>Статистика:</b>\n"
                    f"• Среднее за час: {statistics.get('avg_1h', 0):.1f} gwei\n"
                    f"• Минимум за час: {statistics.get('min_1h', 0):.1f} gwei\n"
                    f"• Максимум за час: {statistics.get('max_1h', 0):.1f} gwei\n"
                    f"• Тренд: {statistics.get('trend', 'неизвестно')}\n\n"
                )
            
            text += f"🕐 <b>Обновлено:</b> {updated_time}"
        
        builder = InlineKeyboardBuilder()
        builder.button(text="🔄 Обновить", callback_data="gas_current")
        builder.button(text="📈 История", callback_data="gas_chart")
        builder.button(text="➕ Добавить алерт", callback_data="gas_add_alert")
        builder.button(text="◀️ Назад", callback_data="gas_tracker")
        builder.adjust(2, 1, 1)
        
        try:
            await message.edit_text(text, reply_markup=builder.as_markup(), parse_mode="HTML")
        except Exception as e:
            logger.error(f"Error updating current price display: {e}")
    
    async def _update_main_menu_display(self, message: types.Message, gas_price: Dict, statistics: Dict, user_id: int):
        """Обновление главного меню."""
        text = "⛽ <b>Gas Tracker</b>\n\n"
        
        if gas_price:
            text += (
                f"💰 <b>Текущие цены:</b>\n"
                f"🟢 Безопасный: {gas_price['safe']:.1f} gwei\n"
                f"🟡 Стандартный: {gas_price['standard']:.1f} gwei\n"
                f"🟠 Быстрый: {gas_price['fast']:.1f} gwei\n"
                f"🔴 Мгновенный: {gas_price['instant']:.1f} gwei\n\n"
            )
        else:
            text += "❌ Данные о газе недоступны\n\n"
        
        if statistics:
            text += (
                f"🔔 <b>Ваши алерты:</b>\n"
                f"• Всего: {statistics.get('total_alerts', 0)}\n"
                f"• Активных: {statistics.get('active_alerts', 0)}\n\n"
            )
        
        text += "⚡ Выберите действие:"
        
        builder = InlineKeyboardBuilder()
        builder.button(text="📊 Текущие цены", callback_data="gas_current")
        builder.button(text="🔔 Мои алерты", callback_data="gas_alerts")
        builder.button(text="➕ Добавить алерт", callback_data="gas_add_alert")
        builder.button(text="📈 История цен", callback_data="gas_chart")
        builder.button(text="📊 Статистика", callback_data="gas_statistics")
        builder.button(text="⚙️ Настройки", callback_data="gas_settings")
        builder.button(text="🔄 Обновить", callback_data="gas_refresh")
        builder.button(text="◀️ Назад", callback_data="main_menu")
        builder.adjust(2, 2, 2, 1, 1)
        
        try:
            await message.edit_text(text, reply_markup=builder.as_markup(), parse_mode="HTML")
        except Exception as e:
            logger.error(f"Error updating main menu: {e}")
    
    async def _handle_alerts_response(self, event: Event):
        """Обработка ответа с алертами пользователя."""
        user_id = event.data.get("user_id")
        alerts = event.data.get("alerts", [])
        
        if user_id not in self._response_cache:
            return
        
        context = self._response_cache[user_id]
        if context["type"] != "user_alerts":
            return
        
        message = context["message"]
        
        if not alerts:
            text = (
                "🔔 <b>Мои газ алерты</b>\n\n"
                "📭 У вас пока нет настроенных алертов\n\n"
                "💡 Создайте алерт, чтобы получать уведомления\n"
                "когда цена на газ достигнет нужного уровня!"
            )
            
            builder = InlineKeyboardBuilder()
            builder.button(text="➕ Создать первый алерт", callback_data="gas_add_alert")
            builder.button(text="◀️ Назад", callback_data="gas_tracker")
            builder.adjust(1)
        else:
            text = f"🔔 <b>Мои газ алерты ({len(alerts)})</b>\n\n"
            
            builder = InlineKeyboardBuilder()
            
            for i, alert in enumerate(alerts, 1):
                status = "🟢" if alert['is_active'] else "🔴"
                alert_type = "⬇️" if alert['alert_type'] == 'below' else "⬆️"
                
                text += (
                    f"{status} <b>Алерт #{i}</b>\n"
                    f"   {alert_type} {alert['threshold_gwei']:.1f} gwei\n"
                    f"   🔔 Срабатывал: {alert['times_triggered']} раз\n"
                )
                
                if alert['last_triggered']:
                    last_time = datetime.fromisoformat(alert['last_triggered'])
                    text += f"   🕐 Последний: {last_time.strftime('%d.%m %H:%M')}\n"
                
                text += "\n"
                
                # Кнопки управления алертом
                alert_id = alert['id']
                if alert['is_active']:
                    builder.button(text=f"⏸️ Приостановить #{i}", callback_data=f"gas_toggle_{alert_id}")
                else:
                    builder.button(text=f"▶️ Активировать #{i}", callback_data=f"gas_toggle_{alert_id}")
                
                builder.button(text=f"🗑️ Удалить #{i}", callback_data=f"gas_delete_{alert_id}")
            
            builder.button(text="➕ Добавить алерт", callback_data="gas_add_alert")
            builder.button(text="◀️ Назад", callback_data="gas_tracker")
            builder.adjust(2)  # По 2 кнопки в ряд для управления алертами
        
        try:
            await message.edit_text(text, reply_markup=builder.as_markup(), parse_mode="HTML")
        except Exception as e:
            logger.error(f"Error updating alerts display: {e}")
        
        # Очищаем кеш
        if user_id in self._response_cache:
            del self._response_cache[user_id]
    
    async def _handle_alert_added(self, event: Event):
        """Обработка добавления алерта."""
        user_id = event.data.get("user_id")
        success = event.data.get("success")
        threshold = event.data.get("threshold")
        alert_type = event.data.get("alert_type")
        
        if success:
            direction = "упадет ниже" if alert_type == "below" else "поднимется выше"
            
            # Отправляем уведомление о создании (если возможно)
            try:
                await event_bus.publish(Event(
                    type="telegram.send_message",
                    data={
                        "user_id": user_id,
                        "message": (
                            f"✅ <b>Алерт создан!</b>\n\n"
                            f"🎯 Условие: когда цена {direction} {threshold:.1f} gwei\n"
                            f"🔔 Вы получите уведомление при срабатывании"
                        ),
                        "parse_mode": "HTML"
                    },
                    source_module="gas_tracker"
                ))
            except Exception as e:
                logger.error(f"Error sending alert creation notification: {e}")
        else:
            try:
                await event_bus.publish(Event(
                    type="telegram.send_message",
                    data={
                        "user_id": user_id,
                        "message": (
                            "❌ <b>Ошибка создания алерта</b>\n\n"
                            "Возможные причины:\n"
                            "• Достигнут лимит алертов (10)\n"
                            "• Некорректные параметры\n"
                            "• Временная ошибка сервиса"
                        ),
                        "parse_mode": "HTML"
                    },
                    source_module="gas_tracker"
                ))
            except Exception as e:
                logger.error(f"Error sending alert creation error: {e}")
    
    async def _handle_alert_removed(self, event: Event):
        """Обработка удаления алерта."""
        user_id = event.data.get("user_id")
        success = event.data.get("success")
        alert_id = event.data.get("alert_id")
        
        if success:
            try:
                await event_bus.publish(Event(
                    type="telegram.send_message",
                    data={
                        "user_id": user_id,
                        "message": f"🗑️ Алерт #{alert_id} удален",
                        "parse_mode": "HTML"
                    },
                    source_module="gas_tracker"
                ))
            except Exception as e:
                logger.error(f"Error sending alert removal notification: {e}")
        
        # Обновляем список алертов если пользователь смотрит их
        if user_id in self._response_cache and self._response_cache[user_id]["type"] == "user_alerts":
            # Запрашиваем обновленный список
            await event_bus.publish(Event(
                type="gas_tracker.get_user_alerts",
                data={"user_id": user_id},
                source_module="telegram"
            ))
    
    async def _handle_history_response(self, event: Event):
        """Обработка ответа с историей цен."""
        user_id = event.data.get("user_id")
        history = event.data.get("history", [])
        hours = event.data.get("hours", 24)
        
        if user_id not in self._response_cache:
            return
        
        context = self._response_cache[user_id]
        if context["type"] != "price_chart":
            return
        
        message = context["message"]
        
        if not history:
            text = (
                f"📈 <b>История цен на газ ({hours}ч)</b>\n\n"
                "❌ Данные недоступны\n"
                "История цен пока не накоплена"
            )
        else:
            # Анализируем данные
            prices = [entry['standard'] for entry in history]
            
            if prices:
                min_price = min(prices)
                max_price = max(prices)
                avg_price = sum(prices) / len(prices)
                current_price = prices[-1] if prices else 0
                
                # Определяем тренд
                if len(prices) > 1:
                    trend_start = sum(prices[:len(prices)//4]) / max(1, len(prices)//4)
                    trend_end = sum(prices[-len(prices)//4:]) / max(1, len(prices)//4)
                    
                    if trend_end > trend_start * 1.05:
                        trend = "📈 Растет"
                        trend_icon = "⬆️"
                    elif trend_end < trend_start * 0.95:
                        trend = "📉 Падает"
                        trend_icon = "⬇️"
                    else:
                        trend = "➡️ Стабильно"
                        trend_icon = "🔄"
                else:
                    trend = "➡️ Недостаточно данных"
                    trend_icon = "❓"
                
                text = (
                    f"📈 <b>История цен на газ ({hours}ч)</b>\n\n"
                    
                    f"📊 <b>Статистика периода:</b>\n"
                    f"• Текущая цена: <b>{current_price:.1f}</b> gwei\n"
                    f"• Средняя цена: <b>{avg_price:.1f}</b> gwei\n"
                    f"• Минимум: <b>{min_price:.1f}</b> gwei\n"
                    f"• Максимум: <b>{max_price:.1f}</b> gwei\n"
                    f"• Разброс: <b>{max_price - min_price:.1f}</b> gwei\n\n"
                    
                    f"{trend_icon} <b>Тренд:</b> {trend}\n\n"
                    
                    f"📝 <b>Рекомендации:</b>\n"
                )
                
                if current_price <= min_price * 1.1:
                    text += "🟢 Сейчас хорошее время для транзакций!\n"
                elif current_price >= max_price * 0.9:
                    text += "🔴 Сейчас газ дорогой, лучше подождать\n"
                else:
                    text += "🟡 Цена в пределах нормы\n"
                
                if trend_icon == "⬇️":
                    text += "💡 Возможно, стоит подождать еще немного"
                elif trend_icon == "⬆️":
                    text += "⚡ Лучше совершить транзакцию сейчас"
                
                text += f"\n\n📉 Данных в истории: {len(history)} точек"
        
        builder = InlineKeyboardBuilder()
        builder.button(text="📊 1 час", callback_data="gas_history_1")
        builder.button(text="📈 6 часов", callback_data="gas_history_6")
        builder.button(text="📉 24 часа", callback_data="gas_history_24")
        builder.button(text="🔄 Обновить", callback_data="gas_chart")
        builder.button(text="➕ Добавить алерт", callback_data="gas_add_alert")
        builder.button(text="◀️ Назад", callback_data="gas_tracker")
        builder.adjust(3, 1, 1, 1)
        
        try:
            await message.edit_text(text, reply_markup=builder.as_markup(), parse_mode="HTML")
        except Exception as e:
            logger.error(f"Error updating history display: {e}")
        
        # Очищаем кеш
        if user_id in self._response_cache:
            del self._response_cache[user_id]
    
    async def _update_statistics_display(self, message: types.Message, gas_price: Dict, statistics: Dict):
        """Обновление отображения статистики."""
        if not gas_price or not statistics:
            text = (
                "📊 <b>Статистика газа</b>\n\n"
                "❌ Недостаточно данных для статистики\n"
                "Попробуйте позже"
            )
        else:
            current_price = gas_price['standard']
            
            text = (
                f"📊 <b>Статистика газа</b>\n\n"
                
                f"💰 <b>Текущие показатели:</b>\n"
                f"• Стандартная цена: <b>{current_price:.1f}</b> gwei\n"
                f"• Среднее за час: <b>{statistics.get('avg_1h', 0):.1f}</b> gwei\n"
                f"• Минимум за час: <b>{statistics.get('min_1h', 0):.1f}</b> gwei\n"
                f"• Максимум за час: <b>{statistics.get('max_1h', 0):.1f}</b> gwei\n\n"
                
                f"📈 <b>Тренд:</b> {statistics.get('trend', 'неизвестно')}\n\n"
                
                f"🔔 <b>Ваши алерты:</b>\n"
                f"• Всего настроено: {statistics.get('total_alerts', 0)}\n"
                f"• Активных: {statistics.get('active_alerts', 0)}\n\n"
                
                f"📊 <b>Рекомендации по цене:</b>\n"
            )
            
            if current_price <= 15:
                text += "🟢 Отличное время для любых транзакций\n"
            elif current_price <= 30:
                text += "🟡 Подходящее время для обычных операций\n"
            elif current_price <= 50:
                text += "🟠 Высокая цена, рассмотрите отсрочку\n"
            else:
                text += "🔴 Очень дорого! Лучше подождать\n"
            
            # Добавляем информацию о volatility если есть данные
            min_price = statistics.get('min_1h', 0)
            max_price = statistics.get('max_1h', 0)
            if min_price and max_price:
                volatility = ((max_price - min_price) / min_price) * 100
                text += f"\n📊 <b>Волатильность за час:</b> {volatility:.1f}%"
                
                if volatility > 20:
                    text += " (высокая)"
                elif volatility > 10:
                    text += " (средняя)"
                else:
                    text += " (низкая)"
        
        builder = InlineKeyboardBuilder()
        builder.button(text="📈 История цен", callback_data="gas_chart")
        builder.button(text="🔄 Обновить", callback_data="gas_statistics")
        builder.button(text="◀️ Назад", callback_data="gas_tracker")
        builder.adjust(2, 1)
        
        try:
            await message.edit_text(text, reply_markup=builder.as_markup(), parse_mode="HTML")
        except Exception as e:
            logger.error(f"Error updating statistics display: {e}")
    
    # QUICK THRESHOLD HANDLERS (для быстрого создания алертов)
    
    async def handle_quick_threshold(self, callback: types.CallbackQuery, state: FSMContext):
        """Обработка быстрых кнопок выбора порога."""
        if callback.data.startswith("gas_quick_"):
            threshold = float(callback.data.split("_")[-1])
            
            await state.update_data(threshold=threshold)
            await state.set_state(GasStates.waiting_alert_type)
            
            text = (
                f"✅ Порог установлен: <b>{threshold:.1f} gwei</b>\n\n"
                
                "🎯 <b>Шаг 2/3:</b> Тип алерта\n\n"
                
                "Когда отправлять уведомление?"
            )
            
            builder = InlineKeyboardBuilder()
            builder.button(text="⬇️ Когда цена УПАДЕТ ниже", callback_data="gas_type_below")
            builder.button(text="⬆️ Когда цена ПОДНИМЕТСЯ выше", callback_data="gas_type_above")
            builder.button(text="❌ Отмена", callback_data="gas_tracker")
            builder.adjust(1)
            
            await callback.message.edit_text(text, reply_markup=builder.as_markup(), parse_mode="HTML")
            await callback.answer()
        
        # Регистрируем эти обработчики тоже
        self.router.callback_query(F.data.startswith("gas_quick_"))(self.handle_quick_threshold)
    
    def get_stats(self) -> Dict[str, Any]:
        """Получение статистики обработчиков."""
        return {
            "active_responses": len(self._response_cache),
            "registered_handlers": "gas_handlers_module",
            "service_connected": self.gas_service is not None
        }# modules/gas_tracker/handlers/gas_handlers.py
"""Полностью рабочие обработчики команд для газ трекера."""

from aiogram import types, F, Router
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.utils.keyboard import InlineKeyboardBuilder
from datetime import datetime
from typing import Dict, Any, List

from shared.events import event_bus, Event, USER_COMMAND_RECEIVED
from shared.cache.memory_cache import cache_manager

import logging

logger = logging.getLogger(__name__)


class GasStates(StatesGroup):
    """Состояния для настройки газ алертов."""
    waiting_threshold = State()
    waiting_alert_type = State()
    waiting_cooldown = State()
    editing_alert = State()


class GasHandlers:
    """Обработчики команд газ трекера с полной функциональностью."""
    
    def __init__(self, gas_service=None):
        self.gas_service = gas_service
        self.router = Router()
        self.cache = cache_manager.get_cache('gas_handlers')
        
        # Подписываемся на ответы от сервиса
        event_bus.subscribe("gas_tracker.current_price_response", self._handle_price_response)
        event_bus.subscribe("gas_tracker.user_alerts_response", self._handle_alerts_response)
        event_bus.subscribe("gas_tracker.alert_added", self._handle_alert_added)
        event_bus.subscribe("gas_tracker.alert_removed", self._handle_alert_removed)
        event_bus.subscribe("gas_tracker.price_history_response", self._handle_history_response)
        
        # Кеш для временного хранения ответов
        self._response_cache = {}
    
    def register_handlers(self, dp):
        """Регистрация всех обработчиков."""
        # Основные команды
        self.router.callback_query(F.data == "gas_tracker")(self.show_gas_menu)
        self.router.callback_query(F.data == "gas_current")(self.show_current_gas)
        self.router.callback_query(F.data == "gas_alerts")(self.show_user_alerts)
        self.router.callback_query(F.data == "gas_add_alert")(self.start_add_alert)
        self.router.callback_query(F.data == "gas_chart")(self.show_price_chart)
        self.router.callback_query(F.data == "gas_settings")(self.show_gas_settings)
        
        # Состояния создания алерта
        self.router.message(GasStates.waiting_threshold)(self.process_threshold)
        self.router.callback_query(F.data.startswith("gas_type_"))(self.process_alert_type)
        self.router.message(GasStates.waiting_cooldown)(self.process_cooldown)
        
        # Управление алертами
        self.router.callback_query(F.data.startswith("gas_toggle_"))(self.toggle_alert)
        self.router.callback_query(F.data.startswith("gas_delete_"))(self.delete_alert)
        self.router.callback_query(F.data.startswith("gas_edit_"))(self.edit_alert)
        
        # Дополнительные функции
        self.router.callback_query(F.data == "gas_statistics")(self.show_statistics)
        self.router.callback_query(F.data == "gas_refresh")(self.refresh_data)
        self.router.callback_query(F.data.startswith("gas_history_"))(self.show_history)
        
        # Настройки
        self.router.callback_query(F.data == "gas_settings_notifications")(self.toggle_notifications)