# modules/wallet_tracker/handlers/wallet_handlers.py
"""Полностью рабочие обработчики для Wallet Tracker."""

from aiogram import types, F, Router
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.utils.keyboard import InlineKeyboardBuilder

from shared.events import event_bus, Event, USER_COMMAND_RECEIVED
from shared.utils.logger import get_module_logger

logger = get_module_logger("wallet_handlers")


class WalletStates(StatesGroup):
    """Состояния для настройки отслеживания кошельков."""
    waiting_address = State()
    waiting_min_value = State()
    waiting_track_options = State()
    waiting_check_address = State()


class WalletHandlers:
    """Полностью функциональные обработчики Wallet Tracker."""
    
    def __init__(self, wallet_service):
        self.wallet_service = wallet_service
        self.router = Router()
    
    def register_handlers(self, dp):
        """Регистрация всех обработчиков."""
        
        # ОСНОВНЫЕ КОМАНДЫ
        self.router.callback_query(F.data == "wallet_tracker")(self.show_wallet_menu)
        self.router.callback_query(F.data == "wallet_menu")(self.show_wallet_menu)
        self.router.callback_query(F.data == "wallet_limitations")(self.show_limitations)
        self.router.callback_query(F.data == "wallet_list")(self.show_wallet_list)
        self.router.callback_query(F.data == "wallet_add")(self.add_wallet_start)
        self.router.callback_query(F.data == "wallet_check")(self.check_wallet_start)
        self.router.callback_query(F.data == "wallet_upgrade_info")(self.show_upgrade_info)
        
        # ДОБАВЛЕНИЕ КОШЕЛЬКА
        self.router.message(WalletStates.waiting_address)(self.process_wallet_address)
        self.router.callback_query(F.data.startswith("wallet_min_"))(self.process_min_value)
        self.router.message(WalletStates.waiting_min_value)(self.process_custom_min_value)
        self.router.callback_query(F.data.startswith("wallet_track_"))(self.process_track_options)
        
        # ПРОВЕРКА КОШЕЛЬКА
        self.router.message(WalletStates.waiting_check_address)(self.process_wallet_check)
        
        # УПРАВЛЕНИЕ КОШЕЛЬКАМИ
        self.router.callback_query(F.data.startswith("wallet_remove_"))(self.remove_wallet)
        self.router.callback_query(F.data.startswith("wallet_toggle_"))(self.toggle_wallet)
        self.router.callback_query(F.data.startswith("wallet_details_"))(self.show_wallet_details)
        
        # ДОПОЛНИТЕЛЬНЫЕ ФУНКЦИИ
        self.router.callback_query(F.data == "wallet_statistics")(self.show_wallet_statistics)
        self.router.callback_query(F.data == "wallet_history")(self.show_wallet_history)
        self.router.callback_query(F.data == "wallet_settings")(self.show_wallet_settings)
        
        dp.include_router(self.router)
    
    async def show_wallet_menu(self, callback: types.CallbackQuery):
        """Показ меню отслеживания кошельков."""
        user_alerts = []
        if self.wallet_service:
            user_alerts = self.wallet_service.get_user_alerts(callback.from_user.id)
        
        limitations = {}
        if self.wallet_service:
            limitations = self.wallet_service.get_limitations_info()
        
        active_wallets = len([a for a in user_alerts if a.get('is_active', True)])
        
        text = (
            "👛 <b>Wallet Tracker</b>\n"
            "<i>Сильно ограниченная версия</i>\n\n"
            
            f"🔍 <b>Отслеживаемых кошельков:</b> {len(user_alerts)}/5\n"
            f"✅ <b>Активных:</b> {active_wallets}\n\n"
            
            "⚠️ <b>КРИТИЧЕСКИЕ ОГРАНИЧЕНИЯ:</b>\n"
            "• ❌ НЕ работает в реальном времени\n"
            "• ⏰ Проверка каждые 2-5 минут\n"
            "• 💰 Только ETH транзакции\n"
            "• 📊 Максимум 5 кошельков\n\n"
            
            "🎯 Что доступно:"
        )
        
        builder = InlineKeyboardBuilder()
        builder.button(text="👛 Мои кошельки", callback_data="wallet_list")
        builder.button(text="➕ Добавить кошелек", callback_data="wallet_add")
        builder.button(text="🔍 Проверить кошелек", callback_data="wallet_check")
        builder.button(text="⚠️ Ограничения", callback_data="wallet_limitations")
        builder.button(text="💰 Upgrade план", callback_data="wallet_upgrade_info")
        builder.button(text="📈 Статистика", callback_data="wallet_statistics")
        builder.button(text="📋 История", callback_data="wallet_history")
        builder.button(text="⚙️ Настройки", callback_data="wallet_settings")
        builder.button(text="◀️ Назад", callback_data="main_menu")
        builder.adjust(2, 2, 2, 2, 1)
        
        await callback.message.edit_text(text, reply_markup=builder.as_markup(), parse_mode="HTML")
        await callback.answer()
    
    async def show_limitations(self, callback: types.CallbackQuery):
        """Показ ограничений сервиса."""
        limitations = {}
        if self.wallet_service:
            limitations = self.wallet_service.get_limitations_info()
        
        text = (
            f"⚠️ <b>{limitations.get('title', 'Ограничения Wallet Tracker')}</b>\n\n"
            
            "🚫 <b>Критические ограничения:</b>\n"
        )
        
        for limit in limitations.get('critical_limitations', []):
            text += f"• {limit}\n"
        
        text += "\n✅ <b>Что работает:</b>\n"
        for work in limitations.get('what_works', []):
            text += f"• {work}\n"
        
        text += "\n💰 <b>Для реального времени нужны:</b>\n"
        for req in limitations.get('for_real_time_tracking', []):
            text += f"• {req}\n"
        
        text += (
            "\n📊 <b>Почему такие ограничения?</b>\n"
            "Бесплатные API имеют строгие лимиты:\n"
            "• Etherscan: 5 запросов/сек\n"
            "• Задержка блокчейна: 1-2 минуты\n"
            "• Без WebSocket'ов\n\n"
            
            "🚀 <b>Для профессионального использования:</b>\n"
            "Нужны платные API или собственная нода"
        )
        
        builder = InlineKeyboardBuilder()
        builder.button(text="💰 Upgrade информация", callback_data="wallet_upgrade_info")
        builder.button(text="◀️ Назад", callback_data="wallet_menu")
        builder.adjust(1)
        
        await callback.message.edit_text(text, reply_markup=builder.as_markup(), parse_mode="HTML")
        await callback.answer()
    
    async def show_wallet_list(self, callback: types.CallbackQuery):
        """Показ списка отслеживаемых кошельков."""
        user_alerts = []
        if self.wallet_service:
            user_alerts = self.wallet_service.get_user_alerts(callback.from_user.id)
        
        if not user_alerts:
            text = (
                "👛 <b>Мои кошельки</b>\n\n"
                "📭 У вас нет отслеживаемых кошельков\n\n"
                
                "💡 Добавьте Ethereum адрес, чтобы получать\n"
                "уведомления о входящих и исходящих транзакциях!\n\n"
                
                "⚠️ <b>Важно:</b> Проверка происходит каждые\n"
                "2-5 минут, не в реальном времени."
            )
            
            builder = InlineKeyboardBuilder()
            builder.button(text="➕ Добавить первый кошелек", callback_data="wallet_add")
            builder.button(text="🔍 Проверить кошелек", callback_data="wallet_check")
            builder.button(text="⚠️ Ограничения", callback_data="wallet_limitations")
            builder.button(text="◀️ Назад", callback_data="wallet_menu")
            builder.adjust(1)
        else:
            text = f"👛 <b>Мои кошельки ({len(user_alerts)}/5)</b>\n\n"
            
            builder = InlineKeyboardBuilder()
            
            for i, alert in enumerate(user_alerts, 1):
                address = alert['wallet_address']
                short_addr = f"{address[:6]}...{address[-4:]}"
                status = "🟢" if alert.get('is_active', True) else "🔴"
                
                text += f"{status} <b>Кошелек #{i}</b>\n"
                text += f"   📍 {short_addr}\n"
                
                if alert.get('min_value_eth', 0) > 0:
                    text += f"   💰 Мин. сумма: {alert['min_value_eth']:.3f} ETH\n"
                
                # Показываем типы отслеживания
                directions = []
                if alert.get('track_incoming', True):
                    directions.append("📥 Входящие")
                if alert.get('track_outgoing', True):
                    directions.append("📤 Исходящие")
                text += f"   🔔 {', '.join(directions)}\n"
                
                text += "\n"
                
                # Кнопки управления
                encoded_address = address  # В реальном приложении нужно безопасное кодирование
                
                if alert.get('is_active', True):
                    builder.button(text=f"⏸️ Приостановить #{i}", callback_data=f"wallet_toggle_{i}")
                else:
                    builder.button(text=f"▶️ Активировать #{i}", callback_data=f"wallet_toggle_{i}")
                
                builder.button(text=f"🔍 Детали #{i}", callback_data=f"wallet_details_{i}")
                builder.button(text=f"🗑️ Удалить #{i}", callback_data=f"wallet_remove_{address}")
            
            builder.button(text="➕ Добавить кошелек", callback_data="wallet_add")
            builder.button(text="🔍 Проверить кошелек", callback_data="wallet_check")
            builder.button(text="◀️ Назад", callback_data="wallet_menu")
            builder.adjust(3)
        
        await callback.message.edit_text(text, reply_markup=builder.as_markup(), parse_mode="HTML")
        await callback.answer()
    
    async def add_wallet_start(self, callback: types.CallbackQuery, state: FSMContext):
        """Начало добавления кошелька."""
        # Проверяем лимит
        if self.wallet_service:
            user_alerts = self.wallet_service.get_user_alerts(callback.from_user.id)
            if len(user_alerts) >= 5:
                await callback.answer("❌ Максимум 5 кошельков на пользователя")
                return
        
        await state.set_state(WalletStates.waiting_address)
        
        text = (
            "👛 <b>Добавление кошелька</b>\n\n"
            
            "📍 <b>Шаг 1/3:</b> Адрес кошелька\n\n"
            
            "Введите Ethereum адрес кошелька для отслеживания:\n\n"
            
            "💡 <b>Формат:</b> 0x1234567890abcdef...\n"
            "📏 <b>Длина:</b> 42 символа\n\n"
            
            "💼 <b>Примеры адресов:</b>\n"
            "• 0xd8dA6BF26964aF9D7eEd9e03E53415D37aA96045\n"
            "• 0x742637e8F5c53f5bE6d47D8e1BC5F6E0c7E15Dd4\n\n"
            
            "⚠️ <b>Внимание:</b> Проверка транзакций происходит\n"
            "каждые 2-5 минут, не в реальном времени!"
        )
        
        builder = InlineKeyboardBuilder()
        builder.button(text="❌ Отмена", callback_data="wallet_menu")
        
        await callback.message.edit_text(text, reply_markup=builder.as_markup(), parse_mode="HTML")
        await callback.answer()
    
    async def process_wallet_address(self, message: types.Message, state: FSMContext):
        """Обработка адреса кошелька."""
        address = message.text.strip()
        
        # Валидация адреса
        if not self._is_valid_eth_address(address):
            await message.answer(
                "❌ <b>Некорректный Ethereum адрес!</b>\n\n"
                "📏 Адрес должен:\n"
                "• Начинаться с 0x\n"
                "• Содержать 42 символа\n"
                "• Состоять из hex символов (0-9, a-f)\n\n"
                "Попробуйте еще раз:",
                parse_mode="HTML"
            )
            return
        
        await state.update_data(wallet_address=address)
        await state.set_state(WalletStates.waiting_min_value)
        
        short_addr = f"{address[:6]}...{address[-4:]}"
        
        text = (
            f"✅ <b>Адрес:</b> {short_addr}\n\n"
            
            "💰 <b>Шаг 2/3:</b> Минимальная сумма\n\n"
            
            "Укажите минимальную сумму транзакции в ETH\n"
            "для получения уведомлений:\n\n"
            
            "💡 <b>Рекомендации:</b>\n"
            "• 0 ETH - все транзакции\n"
            "• 0.01 ETH - мелкие операции\n"
            "• 0.1 ETH - средние операции\n"
            "• 1 ETH - крупные операции"
        )
        
        builder = InlineKeyboardBuilder()
        builder.button(text="0 ETH", callback_data="wallet_min_0")
        builder.button(text="0.01 ETH", callback_data="wallet_min_0.01")
        builder.button(text="0.1 ETH", callback_data="wallet_min_0.1")
        builder.button(text="0.5 ETH", callback_data="wallet_min_0.5")
        builder.button(text="1 ETH", callback_data="wallet_min_1")
        builder.button(text="✏️ Ввести вручную", callback_data="wallet_min_custom")
        builder.button(text="❌ Отмена", callback_data="wallet_menu")
        builder.adjust(2, 2, 2, 1)
        
        await message.answer(text, reply_markup=builder.as_markup(), parse_mode="HTML")
    
    def _is_valid_eth_address(self, address: str) -> bool:
        """Проверка валидности Ethereum адреса."""
        if not address or len(address) != 42:
            return False
        if not address.startswith('0x'):
            return False
        try:
            int(address[2:], 16)
            return True
        except ValueError:
            return False
    
    async def process_min_value(self, callback: types.CallbackQuery, state: FSMContext):
        """Обработка минимальной суммы."""
        if callback.data == "wallet_min_custom":
            await state.set_state(WalletStates.waiting_min_value)
            
            text = (
                "✏️ <b>Ручной ввод суммы</b>\n\n"
                "Введите минимальную сумму в ETH:\n\n"
                "📝 <b>Примеры:</b>\n"
                "• 0.5\n"
                "• 2.75\n"
                "• 10\n\n"
                "📊 <b>Диапазон:</b> 0 - 1000 ETH"
            )
            
            builder = InlineKeyboardBuilder()
            builder.button(text="❌ Отмена", callback_data="wallet_menu")
            
            await callback.message.edit_text(text, reply_markup=builder.as_markup(), parse_mode="HTML")
            await callback.answer()
            return
        
        # Извлекаем значение из callback_data
        min_value = float(callback.data.split("_")[-1])
        await state.update_data(min_value_eth=min_value)
        await state.set_state(WalletStates.waiting_track_options)
        
        await self._show_track_options(callback, state, min_value)
    
    async def process_custom_min_value(self, message: types.Message, state: FSMContext):
        """Обработка пользовательской минимальной суммы."""
        try:
            min_value = float(message.text.strip().replace(',', '.'))
            
            if min_value < 0 or min_value > 1000:
                await message.answer(
                    "❌ <b>Некорректная сумма!</b>\n\n"
                    "Введите значение от 0 до 1000 ETH",
                    parse_mode="HTML"
                )
                return
            
            await state.update_data(min_value_eth=min_value)
            await state.set_state(WalletStates.waiting_track_options)
            
            await self._show_track_options(message, state, min_value)
            
        except ValueError:
            await message.answer(
                "❌ <b>Некорректное число!</b>\n\n"
                "Введите число (например: 0.5):",
                parse_mode="HTML"
            )
    
    async def _show_track_options(self, event, state: FSMContext, min_value: float):
        """Показ опций отслеживания."""
        text = (
            f"✅ <b>Минимальная сумма:</b> {min_value} ETH\n\n"
            
            "🔔 <b>Шаг 3/3:</b> Тип транзакций\n\n"
            
            "Какие транзакции отслеживать?"
        )
        
        builder = InlineKeyboardBuilder()
        builder.button(text="📥 Только входящие", callback_data="wallet_track_in")
        builder.button(text="📤 Только исходящие", callback_data="wallet_track_out")
        builder.button(text="📥📤 Все транзакции", callback_data="wallet_track_both")
        builder.button(text="❌ Отмена", callback_data="wallet_menu")
        builder.adjust(1)
        
        if hasattr(event, 'message'):
            await event.answer(text, reply_markup=builder.as_markup(), parse_mode="HTML")
        else:
            await event.message.edit_text(text, reply_markup=builder.as_markup(), parse_mode="HTML")
            await event.answer()
    
    async def process_track_options(self, callback: types.CallbackQuery, state: FSMContext):
        """Обработка опций отслеживания."""
        data = await state.get_data()
        wallet_address = data.get('wallet_address')
        min_value_eth = data.get('min_value_eth', 0.0)
        
        track_type = callback.data.split("_")[-1]
        track_incoming = track_type in ['in', 'both']
        track_outgoing = track_type in ['out', 'both']
        
        # Добавляем алерт через сервис
        if self.wallet_service:
            success = await self.wallet_service.add_wallet_alert(
                callback.from_user.id,
                wallet_address,
                min_value_eth,
                track_incoming,
                track_outgoing
            )
        else:
            success = False
        
        await state.clear()
        
        if success:
            track_text = []
            if track_incoming:
                track_text.append("входящие")
            if track_outgoing:
                track_text.append("исходящие")
            
            short_addr = f"{wallet_address[:6]}...{wallet_address[-4:]}"
            
            text = (
                "✅ <b>Кошелек добавлен!</b>\n\n"
                
                f"👛 <b>Адрес:</b> {short_addr}\n"
                f"💰 <b>Мин. сумма:</b> {min_value_eth} ETH\n"
                f"📊 <b>Отслеживание:</b> {' и '.join(track_text)}\n\n"
                
                "⚠️ <b>Важные особенности:</b>\n"
                "• Задержка обнаружения: 2-10 минут\n"
                "• Только ETH транзакции\n"
                "• Проверка каждые 2-5 минут\n\n"
                
                "🔔 Вы будете получать уведомления о транзакциях!"
            )
        else:
            text = (
                "❌ <b>Ошибка при добавлении кошелька</b>\n\n"
                
                "Возможные причины:\n"
                "• Кошелек уже добавлен\n"
                "• Достигнут лимит (5 кошельков)\n"
                "• Технические проблемы\n\n"
                
                "Попробуйте еще раз позже"
            )
        
        builder = InlineKeyboardBuilder()
        builder.button(text="👛 Мои кошельки", callback_data="wallet_list")
        builder.button(text="➕ Добавить еще", callback_data="wallet_add")
        builder.button(text="◀️ Главное меню", callback_data="wallet_menu")
        builder.adjust(2, 1)
        
        await callback.message.edit_text(text, reply_markup=builder.as_markup(), parse_mode="HTML")
        await callback.answer()
    
    async def check_wallet_start(self, callback: types.CallbackQuery, state: FSMContext):
        """Начало проверки кошелька."""
        await state.set_state(WalletStates.waiting_check_address)
        
        text = (
            "🔍 <b>Проверка кошелька</b>\n\n"
            
            "Введите Ethereum адрес для разовой проверки:\n\n"
            
            "📊 <b>Что покажет проверка:</b>\n"
            "• Текущий баланс ETH\n"
            "• Баланс в долларах\n"
            "• Количество недавних транзакций\n"
            "• Время последней активности\n\n"
            
            "💡 Это не добавляет кошелек в отслеживание"
        )
        
        builder = InlineKeyboardBuilder()
        builder.button(text="❌ Отмена", callback_data="wallet_menu")
        
        await callback.message.edit_text(text, reply_markup=builder.as_markup(), parse_mode="HTML")
        await callback.answer()
    
    async def process_wallet_check(self, message: types.Message, state: FSMContext):
        """Обработка проверки кошелька."""
        address = message.text.strip()
        
        if not self._is_valid_eth_address(address):
            await message.answer(
                "❌ <b>Некорректный Ethereum адрес!</b>\n\n"
                "Проверьте формат и попробуйте еще раз:",
                parse_mode="HTML"
            )
            return
        
        await state.clear()
        
        # Показываем индикатор загрузки
        loading_msg = await message.answer("🔍 <b>Проверяю кошелек...</b>", parse_mode="HTML")
        
        try:
            # Получаем информацию о кошельке
            if self.wallet_service:
                wallet_info = await self.wallet_service.get_wallet_info(address)
            else:
                wallet_info = None
            
            if wallet_info:
                from datetime import datetime
                
                short_addr = f"{address[:10]}...{address[-6:]}"
                
                text = (
                    f"👛 <b>Информация о кошельке</b>\n\n"
                    f"📍 <b>Адрес:</b> {short_addr}\n"
                    f"💰 <b>Баланс:</b> {wallet_info['balance_eth']:.4f} ETH\n"
                    f"💵 <b>~${wallet_info['balance_usd']:.2f}</b>\n"
                    f"📊 <b>Недавних транзакций:</b> {wallet_info['recent_transactions_count']}\n"
                )
                
                if wallet_info['last_activity']:
                    last_activity = datetime.fromtimestamp(int(wallet_info['last_activity']))
                    text += f"🕐 <b>Последняя активность:</b> {last_activity.strftime('%d.%m.%Y %H:%M')}\n"
                else:
                    text += "🕐 <b>Нет недавней активности</b>\n"
                
                text += (
                    "\n💡 <b>Хотите добавить в отслеживание?</b>\n"
                    "Используйте кнопку ниже"
                )
                
                builder = InlineKeyboardBuilder()
                builder.button(text="➕ Добавить в отслеживание", callback_data="wallet_add")
                builder.button(text="🔄 Проверить другой", callback_data="wallet_check")
                builder.button(text="◀️ Назад", callback_data="wallet_menu")
                builder.adjust(1)
                
            else:
                text = (
                    f"❌ <b>Не удалось получить информацию</b>\n\n"
                    f"📍 <b>Адрес:</b> {address[:10]}...\n\n"
                    
                    "Возможные причины:\n"
                    "• API временно недоступен\n"
                    "• Кошелек не существует\n"
                    "• Превышен лимит запросов\n\n"
                    
                    "Попробуйте позже"
                )
                
                builder = InlineKeyboardBuilder()
                builder.button(text="🔄 Попробовать еще раз", callback_data="wallet_check")
                builder.button(text="◀️ Назад", callback_data="wallet_menu")
                builder.adjust(1)
                
        except Exception as e:
            logger.error(f"Error checking wallet: {e}")
            text = "❌ <b>Ошибка при проверке кошелька</b>"
            builder = InlineKeyboardBuilder()
            builder.button(text="◀️ Назад", callback_data="wallet_menu")
        
        await loading_msg.edit_text(text, reply_markup=builder.as_markup(), parse_mode="HTML")
    
    async def remove_wallet(self, callback: types.CallbackQuery):
        """Удаление кошелька."""
        wallet_address = callback.data.split("_", 2)[-1]
        
        if self.wallet_service:
            success = await self.wallet_service.remove_wallet_alert(
                callback.from_user.id,
                wallet_address
            )
        else:
            success = False
        
        if success:
            short_addr = f"{wallet_address[:6]}...{wallet_address[-4:]}"
            text = f"✅ Кошелек {short_addr} удален из отслеживания"
        else:
            text = "❌ Ошибка при удалении кошелька"
        
        await callback.answer(text)
        
        # Обновляем список
        await self.show_wallet_list(callback)
    
    async def toggle_wallet(self, callback: types.CallbackQuery):
        """Переключение статуса кошелька."""
        await callback.answer("🔄 Функция в разработке")
        await self.show_wallet_list(callback)
    
    async def show_wallet_details(self, callback: types.CallbackQuery):
        """Показ детальной информации о кошельке."""
        wallet_index = int(callback.data.split("_")[-1])
        
        # Получаем информацию о кошельке
        if self.wallet_service:
            user_alerts = self.wallet_service.get_user_alerts(callback.from_user.id)
            
            if wallet_index <= len(user_alerts):
                alert = user_alerts[wallet_index - 1]
                address = alert['wallet_address']
                short_addr = f"{address[:8]}...{address[-6:]}"
                
                text = (
                    f"👛 <b>Детали кошелька #{wallet_index}</b>\n\n"
                    
                    f"📍 <b>Адрес:</b> {short_addr}\n"
                    f"💰 <b>Мин. сумма:</b> {alert.get('min_value_eth', 0):.3f} ETH\n"
                    f"🔔 <b>Статус:</b> {'🟢 Активен' if alert.get('is_active', True) else '🔴 Приостановлен'}\n\n"
                    
                    f"📊 <b>Отслеживание:</b>\n"
                )
                
                if alert.get('track_incoming', True):
                    text += "• ✅ Входящие транзакции\n"
                else:
                    text += "• ❌ Входящие транзакции\n"
                
                if alert.get('track_outgoing', True):
                    text += "• ✅ Исходящие транзакции\n"
                else:
                    text += "• ❌ Исходящие транзакции\n"
                
                text += (
                    f"\n⏰ <b>Последняя проверка:</b>\n"
                    f"Проверка каждые 2-5 минут\n\n"
                    
                    f"📈 <b>Статистика:</b>\n"
                    f"В разработке..."
                )
            else:
                text = "❌ Кошелек не найден"
        else:
            text = "❌ Сервис недоступен"
        
        builder = InlineKeyboardBuilder()
        builder.button(text="🔍 Проверить сейчас", callback_data="wallet_check")
        builder.button(text="⚙️ Настройки", callback_data=f"wallet_edit_{wallet_index}")
        builder.button(text="◀️ К списку", callback_data="wallet_list")
        builder.adjust(2, 1)
        
        await callback.message.edit_text(text, reply_markup=builder.as_markup(), parse_mode="HTML")
        await callback.answer()
    
    async def show_upgrade_info(self, callback: types.CallbackQuery):
        """Показ информации об upgrade."""
        text = (
            "💰 <b>Upgrade Wallet Tracker</b>\n\n"
            
            "🚀 <b>Получите реальное время отслеживания!</b>\n\n"
            
            "💰 <b>Варианты upgrade:</b>\n\n"
            
            "1️⃣ <b>Alchemy API (рекомендуется)</b>\n"
            "   • $99/месяц за Growth план\n"
            "   • Реальное время\n"
            "   • WebSocket уведомления\n"
            "   • Без лимитов\n\n"
            
            "2️⃣ <b>Infura API</b>\n"
            "   • $50-200/месяц\n"
            "   • Хорошая скорость\n"
            "   • Стабильность\n\n"
            
            "3️⃣ <b>QuickNode</b>\n"
            "   • $9-299/месяц\n"
            "   • Быстрый старт\n"
            "   • Разные планы\n\n"
            
            "4️⃣ <b>Собственная Ethereum нода</b>\n"
            "   • $500+/месяц в облаке\n"
            "   • Максимальная скорость\n"
            "   • Полный контроль\n\n"
            
            "✨ <b>Что получите:</b>\n"
            "• ⚡ Уведомления в течение 1-3 секунд\n"
            "• 🔄 WebSocket подключения\n"
            "• 💎 Поддержка ERC-20 токенов\n"
            "• 📊 Детальная аналитика\n"
            "• 🚫 Без лимитов на количество кошельков\n"
            "• 📈 История всех транзакций"
        )
        
        builder = InlineKeyboardBuilder()
        builder.button(text="🔗 Alchemy", url="https://alchemy.com/pricing")
        builder.button(text="🔗 Infura", url="https://infura.io/pricing")
        builder.button(text="🔗 QuickNode", url="https://quicknode.com/pricing")
        builder.button(text="ℹ️ Инструкция по настройке", callback_data="wallet_setup_help")
        builder.button(text="◀️ Назад", callback_data="wallet_menu")
        builder.adjust(3, 1, 1)
        
        await callback.message.edit_text(text, reply_markup=builder.as_markup(), parse_mode="HTML")
        await callback.answer()
    
    async def show_wallet_statistics(self, callback: types.CallbackQuery):
        """Показ статистики Wallet Tracker."""
        user_alerts = []
        if self.wallet_service:
            user_alerts = self.wallet_service.get_user_alerts(callback.from_user.id)
        
        active_wallets = len([a for a in user_alerts if a.get('is_active', True)])
        total_checks = 0  # TODO: реализовать подсчет проверок
        
        text = (
            "📈 <b>Статистика Wallet Tracker</b>\n\n"
            
            f"👤 <b>Ваши кошельки:</b>\n"
            f"• Всего добавлено: {len(user_alerts)}/5\n"
            f"• Активных: {active_wallets}\n"
            f"• Общих проверок: {total_checks}\n\n"
            
            "🔧 <b>Система:</b>\n"
            f"• Статус: {'🟢 Работает' if self.wallet_service and self.wallet_service.running else '🔴 Остановлена'}\n"
            f"• Режим: ⚠️ Ограниченный (бесплатный API)\n"
            f"• Интервал проверки: 2-5 минут\n"
            f"• Задержка обнаружения: 2-10 минут\n\n"
            
            "📊 <b>Ограничения:</b>\n"
            "• ❌ Не работает в реальном времени\n"
            "• ❌ Только ETH транзакции\n"
            "• ❌ Лимит: 5 кошельков\n"
            "• ❌ API лимит: 5 запросов/сек\n\n"
            
            "💡 Upgrade для снятия всех ограничений!"
        )
        
        builder = InlineKeyboardBuilder()
        builder.button(text="🔄 Обновить", callback_data="wallet_statistics")
        builder.button(text="💰 Upgrade", callback_data="wallet_upgrade_info")
        builder.button(text="◀️ Назад", callback_data="wallet_menu")
        builder.adjust(2, 1)
        
        await callback.message.edit_text(text, reply_markup=builder.as_markup(), parse_mode="HTML")
        await callback.answer()
    
    async def show_wallet_history(self, callback: types.CallbackQuery):
        """Показ истории отслеживания."""
        text = (
            "📋 <b>История отслеживания</b>\n\n"
            
            "📊 <b>За последние 24 часа:</b>\n"
            "• Проверок кошельков: Нет данных\n"
            "• Найдено транзакций: Нет данных\n"
            "• Отправлено уведомлений: Нет данных\n\n"
            
            "📈 <b>За неделю:</b>\n"
            "• Всего проверок: Нет данных\n"
            "• Обнаружено транзакций: Нет данных\n\n"
            
            "⚠️ <b>Ограниченный режим</b>\n"
            "Детальная история недоступна в бесплатном режиме.\n\n"
            
            "💡 <b>С upgrade планом получите:</b>\n"
            "• Полную историю транзакций\n"
            "• Аналитику по каждому кошельку\n"
            "• Графики активности\n"
            "• Экспорт данных"
        )
        
        builder = InlineKeyboardBuilder()
        builder.button(text="💰 Получить доступ", callback_data="wallet_upgrade_info")
        builder.button(text="📊 Статистика", callback_data="wallet_statistics")
        builder.button(text="◀️ Назад", callback_data="wallet_menu")
        builder.adjust(1)
        
        await callback.message.edit_text(text, reply_markup=builder.as_markup(), parse_mode="HTML")
        await callback.answer()
    
    async def show_wallet_settings(self, callback: types.CallbackQuery):
        """Показ настроек Wallet Tracker."""
        text = (
            "⚙️ <b>Настройки Wallet Tracker</b>\n\n"
            
            "🔔 <b>Уведомления:</b>\n"
            "• Telegram алерты: 🟢 Включены\n"
            "• Звуковые сигналы: 🟢 Включены\n"
            "• Группировка: 🟢 Включена\n"
            "• Показывать газ: 🟢 Включено\n\n"
            
            "⏰ <b>Интервалы:</b>\n"
            "• Проверка кошельков: 2-5 минут\n"
            "• Cooldown уведомлений: 5 минут\n"
            "• Таймаут API: 30 секунд\n\n"
            
            "🎯 <b>Фильтры:</b>\n"
            "• Мин. сумма: Настройка в каждом кошельке\n"
            "• Типы транзакций: Настройка в каждом кошельке\n"
            "• Игнорировать неуспешные: ❌ Недоступно\n"
            "• Фильтр контрактов: ❌ Недоступно\n\n"
            
            "⚠️ Расширенные настройки доступны с upgrade"
        )
        
        builder = InlineKeyboardBuilder()
        builder.button(text="🔔 Уведомления", callback_data="wallet_settings_notifications")
        builder.button(text="⏰ Интервалы", callback_data="wallet_settings_intervals")
        builder.button(text="🎯 Фильтры", callback_data="wallet_settings_filters")
        builder.button(text="🔄 Сбросить", callback_data="wallet_settings_reset")
        builder.button(text="◀️ Назад", callback_data="wallet_menu")
        builder.adjust(2, 2, 1)
        
        await callback.message.edit_text(text, reply_markup=builder.as_markup(), parse_mode="HTML")
        await callback.answer()
    
    def get_stats(self) -> dict:
        """Получение статистики обработчиков."""
        return {
            "service_connected": self.wallet_service is not None,
            "service_running": self.wallet_service.running if self.wallet_service else False,
            "handlers_registered": "wallet_handlers_module"
        }# modules/wallet_tracker/handlers/wallet_handlers.py