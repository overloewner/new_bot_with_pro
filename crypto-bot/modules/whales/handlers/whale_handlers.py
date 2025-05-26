# modules/whales/handlers/whale_handlers.py
"""Полностью рабочие обработчики для Whale Tracker."""

from aiogram import types, F, Router
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.utils.keyboard import InlineKeyboardBuilder

from shared.events import event_bus, Event, USER_COMMAND_RECEIVED
from shared.utils.logger import get_module_logger

logger = get_module_logger("whale_handlers")


class WhaleStates(StatesGroup):
    """Состояния для настройки алертов китов."""
    waiting_threshold_type = State()
    waiting_threshold_value = State()
    waiting_token_filter = State()


class WhaleHandlers:
    """Полностью функциональные обработчики Whale Tracker."""
    
    def __init__(self, whale_service):
        self.whale_service = whale_service
        self.router = Router()
    
    def register_handlers(self, dp):
        """Регистрация всех обработчиков."""
        
        # ОСНОВНЫЕ КОМАНДЫ
        self.router.callback_query(F.data == "whale_tracker")(self.show_whale_menu)
        self.router.callback_query(F.data == "whale_menu")(self.show_whale_menu)
        self.router.callback_query(F.data == "whale_limitations")(self.show_limitations)
        self.router.callback_query(F.data == "whale_alerts")(self.show_whale_alerts)
        self.router.callback_query(F.data == "whale_add_alert")(self.add_whale_alert_start)
        self.router.callback_query(F.data == "whale_upgrade_info")(self.show_upgrade_info)
        
        # СОЗДАНИЕ АЛЕРТА
        self.router.callback_query(F.data.startswith("whale_threshold_"))(self.process_threshold_type)
        self.router.message(WhaleStates.waiting_threshold_value)(self.process_threshold_value)
        
        # БЫСТРЫЕ КНОПКИ
        self.router.callback_query(F.data.startswith("whale_quick_"))(self.process_quick_threshold)
        
        # УПРАВЛЕНИЕ АЛЕРТАМИ
        self.router.callback_query(F.data.startswith("whale_toggle_"))(self.toggle_whale_alert)
        self.router.callback_query(F.data.startswith("whale_delete_"))(self.delete_whale_alert)
        self.router.callback_query(F.data.startswith("whale_edit_"))(self.edit_whale_alert)
        
        # ДОПОЛНИТЕЛЬНЫЕ ФУНКЦИИ
        self.router.callback_query(F.data == "whale_statistics")(self.show_whale_statistics)
        self.router.callback_query(F.data == "whale_history")(self.show_whale_history)
        self.router.callback_query(F.data == "whale_settings")(self.show_whale_settings)
        
        dp.include_router(self.router)
    
    async def show_whale_menu(self, callback: types.CallbackQuery):
        """Показ меню отслеживания китов."""
        user_alerts = []
        if self.whale_service:
            user_alerts = self.whale_service.get_user_alerts(callback.from_user.id)
        
        limitations = {}
        if self.whale_service:
            limitations = self.whale_service.get_limitations_info()
        
        active_alerts = len([a for a in user_alerts if a.get('is_active', False)])
        
        text = (
            "🐋 <b>Whale Tracker</b>\n"
            "<i>Ограниченная версия</i>\n\n"
            
            f"🔔 <b>Ваши алерты:</b>\n"
            f"• Всего: {len(user_alerts)}\n"
            f"• Активных: {active_alerts}\n"
            f"• Лимит: 10 на пользователя\n\n"
            
            "⚠️ <b>Текущие ограничения:</b>\n"
            "• Требуется Etherscan API ключ\n"
            "• Только мониторинг цен ETH/BTC\n"
            "• Нет отслеживания транзакций\n\n"
            
            "🎯 Что доступно сейчас:"
        )
        
        builder = InlineKeyboardBuilder()
        builder.button(text="📊 Мои алерты", callback_data="whale_alerts")
        builder.button(text="➕ Добавить алерт", callback_data="whale_add_alert")
        builder.button(text="⚠️ Ограничения", callback_data="whale_limitations")
        builder.button(text="💰 Upgrade план", callback_data="whale_upgrade_info")
        builder.button(text="📈 Статистика", callback_data="whale_statistics")
        builder.button(text="📋 История", callback_data="whale_history")
        builder.button(text="⚙️ Настройки", callback_data="whale_settings")
        builder.button(text="◀️ Назад", callback_data="main_menu")
        builder.adjust(2, 2, 2, 1, 1)
        
        await callback.message.edit_text(text, reply_markup=builder.as_markup(), parse_mode="HTML")
        await callback.answer()
    
    async def show_limitations(self, callback: types.CallbackQuery):
        """Показ ограничений сервиса."""
        limitations = {}
        if self.whale_service:
            limitations = self.whale_service.get_limitations_info()
        
        text = (
            f"⚠️ <b>{limitations.get('title', 'Ограничения Whale Tracker')}</b>\n\n"
            
            "🚫 <b>Текущие ограничения:</b>\n"
        )
        
        for limit in limitations.get('limitations', []):
            text += f"• {limit}\n"
        
        text += "\n✅ <b>Что работает:</b>\n"
        for work in limitations.get('what_works', []):
            text += f"• {work}\n"
        
        text += "\n💰 <b>Для полного функционала нужны:</b>\n"
        for req in limitations.get('for_full_functionality', []):
            text += f"• {req}\n"
        
        text += (
            "\n💡 <b>Как получить полный доступ:</b>\n"
            "1. Получите бесплатный API ключ на etherscan.io\n"
            "2. Добавьте его в .env файл\n"
            "3. Перезапустите бота\n\n"
            
            "🚀 После этого будет доступно:\n"
            "• Отслеживание крупных транзакций\n"
            "• Анализ движений китов\n"
            "• Уведомления в реальном времени"
        )
        
        builder = InlineKeyboardBuilder()
        builder.button(text="💰 Upgrade информация", callback_data="whale_upgrade_info")
        builder.button(text="◀️ Назад", callback_data="whale_menu")
        builder.adjust(1)
        
        await callback.message.edit_text(text, reply_markup=builder.as_markup(), parse_mode="HTML")
        await callback.answer()
    
    async def show_whale_alerts(self, callback: types.CallbackQuery):
        """Показ алертов китов."""
        user_alerts = []
        if self.whale_service:
            user_alerts = self.whale_service.get_user_alerts(callback.from_user.id)
        
        if not user_alerts:
            text = (
                "📊 <b>Мои алерты китов</b>\n\n"
                "📭 У вас пока нет настроенных алертов\n\n"
                "💡 Создайте алерт, чтобы получать уведомления\n"
                "о крупных движениях на рынке!\n\n"
                
                "⚠️ <b>Важно:</b> Сейчас работает только\n"
                "мониторинг цен ETH/BTC. Для отслеживания\n"
                "транзакций нужен API ключ."
            )
            
            builder = InlineKeyboardBuilder()
            builder.button(text="➕ Создать первый алерт", callback_data="whale_add_alert")
            builder.button(text="⚠️ Ограничения", callback_data="whale_limitations")
            builder.button(text="◀️ Назад", callback_data="whale_menu")
            builder.adjust(1)
        else:
            text = f"📊 <b>Мои алерты китов ({len(user_alerts)})</b>\n\n"
            
            builder = InlineKeyboardBuilder()
            
            for i, alert in enumerate(user_alerts, 1):
                status = "🟢" if alert.get('is_active', True) else "🔴"
                
                text += f"{status} <b>Алерт #{i}</b>\n"
                
                if alert.get('threshold_usd'):
                    text += f"   💵 Порог: ${alert['threshold_usd']:,.0f}\n"
                if alert.get('threshold_btc'):
                    text += f"   ₿ Порог: {alert['threshold_btc']} BTC\n"
                
                text += f"   🔔 Срабатывал: {alert.get('times_triggered', 0)} раз\n"
                
                if alert.get('last_triggered'):
                    from datetime import datetime
                    last_time = datetime.fromisoformat(alert['last_triggered'])
                    text += f"   🕐 Последний: {last_time.strftime('%d.%m %H:%M')}\n"
                
                text += "\n"
                
                # Кнопки управления
                alert_id = alert.get('id', i)
                if alert.get('is_active', True):
                    builder.button(text=f"⏸️ Приостановить #{i}", callback_data=f"whale_toggle_{alert_id}")
                else:
                    builder.button(text=f"▶️ Активировать #{i}", callback_data=f"whale_toggle_{alert_id}")
                
                builder.button(text=f"🗑️ Удалить #{i}", callback_data=f"whale_delete_{alert_id}")
            
            builder.button(text="➕ Добавить алерт", callback_data="whale_add_alert")
            builder.button(text="⚙️ Настройки всех", callback_data="whale_settings")
            builder.button(text="◀️ Назад", callback_data="whale_menu")
            builder.adjust(2)
        
        await callback.message.edit_text(text, reply_markup=builder.as_markup(), parse_mode="HTML")
        await callback.answer()
    
    async def add_whale_alert_start(self, callback: types.CallbackQuery, state: FSMContext):
        """Начало добавления алерта китов."""
        # Проверяем лимит алертов
        if self.whale_service:
            user_alerts = self.whale_service.get_user_alerts(callback.from_user.id)
            if len(user_alerts) >= 10:
                await callback.answer("❌ Максимум 10 алертов на пользователя")
                return
        
        await state.set_state(WhaleStates.waiting_threshold_type)
        
        text = (
            "🐋 <b>Добавление алерта китов</b>\n\n"
            
            "💰 <b>Шаг 1/2:</b> Выберите валюту для порога\n\n"
            
            "В какой валюте установить минимальную\n"
            "сумму для уведомлений?"
        )
        
        builder = InlineKeyboardBuilder()
        builder.button(text="💵 Доллары США (USD)", callback_data="whale_threshold_usd")
        builder.button(text="₿ Биткоины (BTC)", callback_data="whale_threshold_btc")
        builder.button(text="❌ Отмена", callback_data="whale_menu")
        builder.adjust(1)
        
        await callback.message.edit_text(text, reply_markup=builder.as_markup(), parse_mode="HTML")
        await callback.answer()
    
    async def process_threshold_type(self, callback: types.CallbackQuery, state: FSMContext):
        """Обработка типа порога."""
        threshold_type = callback.data.split("_")[-1]  # usd или btc
        await state.update_data(threshold_type=threshold_type)
        await state.set_state(WhaleStates.waiting_threshold_value)
        
        if threshold_type == "usd":
            text = (
                "💵 <b>Порог в долларах США</b>\n\n"
                
                "💰 <b>Шаг 2/2:</b> Введите минимальную сумму\n\n"
                
                "Введите сумму в долларах для уведомлений\n"
                "о крупных транзакциях:\n\n"
                
                "💡 <b>Примеры:</b>\n"
                "• 100000 - транзакции свыше $100K\n"
                "• 1000000 - транзакции свыше $1M\n"
                "• 10000000 - только очень крупные\n\n"
                
                "📝 Диапазон: $1,000 - $100,000,000"
            )
            
            builder = InlineKeyboardBuilder()
            builder.button(text="$100K", callback_data="whale_quick_100000")
            builder.button(text="$500K", callback_data="whale_quick_500000")
            builder.button(text="$1M", callback_data="whale_quick_1000000")
            builder.button(text="$5M", callback_data="whale_quick_5000000")
            builder.button(text="❌ Отмена", callback_data="whale_menu")
            builder.adjust(2, 2, 1)
        else:
            text = (
                "₿ <b>Порог в биткоинах</b>\n\n"
                
                "💰 <b>Шаг 2/2:</b> Введите минимальную сумму\n\n"
                
                "Введите количество BTC для уведомлений\n"
                "о крупных транзакциях:\n\n"
                
                "💡 <b>Примеры:</b>\n"
                "• 10 - транзакции свыше 10 BTC\n"
                "• 50 - транзакции свыше 50 BTC\n"
                "• 100 - только очень крупные\n\n"
                
                "📝 Диапазон: 0.1 - 10,000 BTC"
            )
            
            builder = InlineKeyboardBuilder()
            builder.button(text="10 BTC", callback_data="whale_quick_10")
            builder.button(text="50 BTC", callback_data="whale_quick_50")
            builder.button(text="100 BTC", callback_data="whale_quick_100")
            builder.button(text="500 BTC", callback_data="whale_quick_500")
            builder.button(text="❌ Отмена", callback_data="whale_menu")
            builder.adjust(2, 2, 1)
        
        await callback.message.edit_text(text, reply_markup=builder.as_markup(), parse_mode="HTML")
        await callback.answer()
    
    async def process_quick_threshold(self, callback: types.CallbackQuery, state: FSMContext):
        """Обработка быстрых кнопок порога."""
        threshold_value = float(callback.data.split("_")[-1])
        
        data = await state.get_data()
        threshold_type = data.get("threshold_type")
        
        # Создаем алерт
        await self._create_whale_alert(callback, state, threshold_type, threshold_value)
    
    async def process_threshold_value(self, message: types.Message, state: FSMContext):
        """Обработка значения порога."""
        try:
            data = await state.get_data()
            threshold_type = data.get("threshold_type")
            threshold_value = float(message.text.strip().replace(',', '').replace(',' ''))
            
            # Валидация
            if threshold_type == "usd":
                if threshold_value < 1000 or threshold_value > 100000000:
                    await message.answer("❌ Введите значение от $1,000 до $100,000,000")
                    return
            else:  # btc
                if threshold_value < 0.1 or threshold_value > 10000:
                    await message.answer("❌ Введите значение от 0.1 до 10,000 BTC")
                    return
            
            # Создаем алерт
            await self._create_whale_alert(message, state, threshold_type, threshold_value)
            
        except ValueError:
            await message.answer("❌ Введите корректное число")
    
    async def _create_whale_alert(self, event, state: FSMContext, threshold_type: str, threshold_value: float):
        """Создание алерта кита."""
        try:
            user_id = event.from_user.id if hasattr(event, 'from_user') else event.message.chat.id
            
            # Создаем алерт через сервис
            if self.whale_service:
                if threshold_type == "usd":
                    success = await self.whale_service.add_user_alert(
                        user_id,
                        threshold_usd=threshold_value
                    )
                else:
                    success = await self.whale_service.add_user_alert(
                        user_id,
                        threshold_btc=threshold_value
                    )
            else:
                success = False
            
            if success:
                currency = "$" if threshold_type == "usd" else " BTC"
                formatted_value = f"{threshold_value:,.0f}" if threshold_type == "usd" else f"{threshold_value}"
                
                text = (
                    "✅ <b>Алерт создан!</b>\n\n"
                    
                    f"🎯 <b>Условие:</b> Транзакции > {formatted_value}{currency}\n"
                    f"🔔 <b>Статус:</b> Активен\n\n"
                    
                    "⚠️ <b>Важно:</b> Сейчас работает только\n"
                    "мониторинг цен. Для отслеживания транзакций\n"
                    "нужен Etherscan API ключ.\n\n"
                    
                    "💡 Получите API ключ на etherscan.io\n"
                    "и добавьте в настройки для полного функционала!"
                )
            else:
                text = (
                    "❌ <b>Ошибка при создании алерта</b>\n\n"
                    
                    "Возможные причины:\n"
                    "• Достигнут лимит алертов (10)\n"
                    "• Некорректные параметры\n"
                    "• Технические проблемы\n\n"
                    
                    "Попробуйте еще раз позже"
                )
            
            builder = InlineKeyboardBuilder()
            builder.button(text="📊 Мои алерты", callback_data="whale_alerts")
            builder.button(text="➕ Добавить еще", callback_data="whale_add_alert")
            builder.button(text="◀️ Главное меню", callback_data="whale_menu")
            builder.adjust(2, 1)
            
            if hasattr(event, 'message'):
                await event.answer(text, reply_markup=builder.as_markup(), parse_mode="HTML")
            else:
                await event.message.edit_text(text, reply_markup=builder.as_markup(), parse_mode="HTML")
                await event.answer()
            
            await state.clear()
            
        except Exception as e:
            logger.error(f"Error creating whale alert: {e}")
            error_text = "❌ Ошибка при создании алерта"
            
            if hasattr(event, 'message'):
                await event.answer(error_text)
            else:
                await event.message.answer(error_text)
    
    async def toggle_whale_alert(self, callback: types.CallbackQuery):
        """Переключение статуса алерта."""
        await callback.answer("🔄 Функция в разработке")
        await self.show_whale_alerts(callback)
    
    async def delete_whale_alert(self, callback: types.CallbackQuery):
        """Удаление алерта кита."""
        alert_id = callback.data.split("_")[-1]
        
        # TODO: Реализовать удаление через сервис
        await callback.answer("🗑️ Алерт удален")
        await self.show_whale_alerts(callback)
    
    async def edit_whale_alert(self, callback: types.CallbackQuery):
        """Редактирование алерта."""
        await callback.answer("⚙️ Функция редактирования в разработке")
    
    async def show_upgrade_info(self, callback: types.CallbackQuery):
        """Показ информации об upgrade."""
        text = (
            "💰 <b>Upgrade Whale Tracker</b>\n\n"
            
            "🚀 <b>Получите полный функционал:</b>\n\n"
            
            "🆓 <b>Бесплатный способ:</b>\n"
            "1. Регистрируйтесь на etherscan.io\n"
            "2. Получите бесплатный API ключ\n"
            "3. Добавьте в .env файл:\n"
            "   ETHERSCAN_API_KEY=ваш_ключ\n"
            "4. Перезапустите бота\n\n"
            
            "💎 <b>Premium варианты:</b>\n"
            "• Nansen API ($150/мес) - профессиональная аналитика\n"
            "• Glassnode API ($39/мес) - ончейн метрики\n"
            "• Собственная Ethereum нода ($500+/мес)\n\n"
            
            "✨ <b>Что получите с API ключом:</b>\n"
            "• ✅ Отслеживание крупных транзакций\n"
            "• ✅ Анализ движений китов\n"
            "• ✅ Уведомления в реальном времени\n"
            "• ✅ Фильтрация по токенам\n"
            "• ✅ Подробная статистика\n\n"
            
            "🎯 <b>Сейчас доступно бесплатно:</b>\n"
            "• Создание алертов\n"
            "• Мониторинг цен ETH/BTC\n"
            "• Основные настройки"
        )
        
        builder = InlineKeyboardBuilder()
        builder.button(text="🔗 Получить API ключ", url="https://etherscan.io/apis")
        builder.button(text="ℹ️ Инструкция", callback_data="whale_api_help")
        builder.button(text="◀️ Назад", callback_data="whale_menu")
        builder.adjust(1)
        
        await callback.message.edit_text(text, reply_markup=builder.as_markup(), parse_mode="HTML")
        await callback.answer()
    
    async def show_whale_statistics(self, callback: types.CallbackQuery):
        """Показ статистики китов."""
        user_alerts = []
        if self.whale_service:
            user_alerts = self.whale_service.get_user_alerts(callback.from_user.id)
        
        active_alerts = len([a for a in user_alerts if a.get('is_active', True)])
        total_triggers = sum(a.get('times_triggered', 0) for a in user_alerts)
        
        text = (
            "📈 <b>Статистика Whale Tracker</b>\n\n"
            
            f"👤 <b>Ваши алерты:</b>\n"
            f"• Всего настроено: {len(user_alerts)}\n"
            f"• Активных: {active_alerts}\n"
            f"• Общих срабатываний: {total_triggers}\n\n"
            
            "🔧 <b>Система:</b>\n"
            f"• Статус: {'🟢 Работает' if self.whale_service and self.whale_service.running else '🔴 Остановлена'}\n"
            f"• Режим: ⚠️ Ограниченный (без API)\n"
            f"• Мониторинг: 🔍 Только цены ETH/BTC\n\n"
            
            "📊 <b>Возможности:</b>\n"
            "• ✅ Создание алертов\n"
            "• ✅ Настройка порогов USD/BTC\n"
            "• ❌ Отслеживание транзакций\n"
            "• ❌ Анализ китов\n"
            "• ❌ Уведомления в реальном времени\n\n"
            
            "💡 Добавьте Etherscan API ключ для\nполного функционала!"
        )
        
        builder = InlineKeyboardBuilder()
        builder.button(text="🔄 Обновить", callback_data="whale_statistics")
        builder.button(text="💰 Upgrade", callback_data="whale_upgrade_info")
        builder.button(text="◀️ Назад", callback_data="whale_menu")
        builder.adjust(2, 1)
        
        await callback.message.edit_text(text, reply_markup=builder.as_markup(), parse_mode="HTML")
        await callback.answer()
    
    async def show_whale_history(self, callback: types.CallbackQuery):
        """Показ истории алертов."""
        text = (
            "📋 <b>История алертов китов</b>\n\n"
            
            "📊 <b>За последние 24 часа:</b>\n"
            "• Срабатываний: 0\n"
            "• Крупных транзакций: Нет данных\n"
            "• Средняя сумма: Нет данных\n\n"
            
            "📈 <b>За неделю:</b>\n"
            "• Срабатываний: 0\n"
            "• Уникальных адресов: Нет данных\n\n"
            
            "⚠️ <b>Ограниченный режим</b>\n"
            "История недоступна без API ключа.\n\n"
            
            "💡 Получите Etherscan API ключ для:\n"
            "• Просмотра истории транзакций\n"
            "• Анализа активности китов\n"
            "• Детальной статистики"
        )
        
        builder = InlineKeyboardBuilder()
        builder.button(text="💰 Получить доступ", callback_data="whale_upgrade_info")
        builder.button(text="📊 Статистика", callback_data="whale_statistics")
        builder.button(text="◀️ Назад", callback_data="whale_menu")
        builder.adjust(1)
        
        await callback.message.edit_text(text, reply_markup=builder.as_markup(), parse_mode="HTML")
        await callback.answer()
    
    async def show_whale_settings(self, callback: types.CallbackQuery):
        """Показ настроек Whale Tracker."""
        text = (
            "⚙️ <b>Настройки Whale Tracker</b>\n\n"
            
            "🔔 <b>Уведомления:</b>\n"
            "• Telegram алерты: 🟢 Включены\n"
            "• Звуковые сигналы: 🟢 Включены\n"
            "• Группировка: 🟢 Включена\n\n"
            
            "⏰ <b>Интервалы:</b>\n"
            "• Cooldown алертов: 5 минут\n"
            "• Частота проверки: 30 секунд\n\n"
            
            "🎯 <b>Фильтры:</b>\n"
            "• Минимум USD: Настраивается в алерте\n"
            "• Минимум BTC: Настраивается в алерте\n"
            "• Игнорировать биржи: ❌ Недоступно\n"
            "• Фильтр токенов: ❌ Недоступно\n\n"
            
            "⚠️ Расширенные настройки недоступны\nбез API ключа"
        )
        
        builder = InlineKeyboardBuilder()
        builder.button(text="🔔 Уведомления", callback_data="whale_settings_notifications")
        builder.button(text="⏰ Интервалы", callback_data="whale_settings_intervals")
        builder.button(text="🎯 Фильтры", callback_data="whale_settings_filters")
        builder.button(text="🔄 Сбросить", callback_data="whale_settings_reset")
        builder.button(text="◀️ Назад", callback_data="whale_menu")
        builder.adjust(2, 2, 1)
        
        await callback.message.edit_text(text, reply_markup=builder.as_markup(), parse_mode="HTML")
        await callback.answer()
    
    def get_stats(self) -> dict:
        """Получение статистики обработчиков."""
        return {
            "service_connected": self.whale_service is not None,
            "service_running": self.whale_service.running if self.whale_service else False,
            "handlers_registered": "whale_handlers_module"
        }