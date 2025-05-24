# modules/wallet_tracker/handlers/wallet_handlers.py
"""Обработчики команд для отслеживания кошельков."""

from aiogram import types, F
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.utils.keyboard import InlineKeyboardBuilder

from shared.events import event_bus, Event, USER_COMMAND_RECEIVED


class WalletStates(StatesGroup):
    """Состояния для настройки отслеживания кошельков."""
    waiting_address = State()
    waiting_min_value = State()
    waiting_track_options = State()


class WalletHandlers:
    """Обработчики команд отслеживания кошельков."""
    
    def __init__(self, wallet_service):
        self.wallet_service = wallet_service
    
    async def show_wallet_menu(self, callback: types.CallbackQuery):
        """Показ меню отслеживания кошельков."""
        user_alerts = self.wallet_service.get_user_alerts(callback.from_user.id)
        limitations = self.wallet_service.get_limitations_info()
        
        builder = InlineKeyboardBuilder()
        builder.button(text="⚠️ Ограничения", callback_data="wallet_limitations")
        builder.button(text="👛 Мои кошельки", callback_data="wallet_list")
        builder.button(text="➕ Добавить кошелек", callback_data="wallet_add")
        builder.button(text="🔍 Проверить кошелек", callback_data="wallet_check")
        builder.button(text="◀️ Назад", callback_data="main_menu")
        builder.adjust(1)
        
        text = (
            "👛 Wallet Tracker (Сильно ограниченная версия)\n\n"
            f"Отслеживаемых кошельков: {len(user_alerts)}/5\n\n"
            "⚠️ НЕ РАБОТАЕТ В РЕАЛЬНОМ ВРЕМЕНИ!\n"
            "Проверка каждые 2-5 минут"
        )
        
        await callback.message.edit_text(text, reply_markup=builder.as_markup())
        await callback.answer()
    
    async def show_limitations(self, callback: types.CallbackQuery):
        """Показ ограничений сервиса."""
        limitations = self.wallet_service.get_limitations_info()
        
        builder = InlineKeyboardBuilder()
        builder.button(text="◀️ Назад", callback_data="wallet_menu")
        
        text = f"⚠️ {limitations['title']}\n\n"
        
        text += "🚫 Критические ограничения:\n"
        for limit in limitations['critical_limitations']:
            text += f"{limit}\n"
        
        text += "\n✅ Что работает:\n"
        for work in limitations['what_works']:
            text += f"{work}\n"
        
        text += "\n💰 Для реального времени нужны:\n"
        for req in limitations['for_real_time_tracking']:
            text += f"{req}\n"
        
        await callback.message.edit_text(text, reply_markup=builder.as_markup())
        await callback.answer()
    
    async def show_wallet_list(self, callback: types.CallbackQuery):
        """Показ списка отслеживаемых кошельков."""
        user_alerts = self.wallet_service.get_user_alerts(callback.from_user.id)
        
        builder = InlineKeyboardBuilder()
        
        if not user_alerts:
            text = "👛 У вас нет отслеживаемых кошельков"
        else:
            text = "👛 Ваши отслеживаемые кошельки:\n\n"
            
            for i, alert in enumerate(user_alerts, 1):
                address = alert['wallet_address']
                short_addr = f"{address[:6]}...{address[-4:]}"
                status = "🟢" if alert['is_active'] else "🔴"
                
                text += f"{i}. {status} {short_addr}\n"
                
                if alert['min_value_eth'] > 0:
                    text += f"   Мин. сумма: {alert['min_value_eth']:.3f} ETH\n"
                
                directions = []
                if alert['track_incoming']:
                    directions.append("📥")
                if alert['track_outgoing']:
                    directions.append("📤")
                text += f"   Отслеживание: {' '.join(directions)}\n"
                
                builder.button(
                    text=f"🗑️ Удалить {i}",
                    callback_data=f"wallet_remove_{address}"
                )
        
        builder.button(text="➕ Добавить", callback_data="wallet_add")
        builder.button(text="◀️ Назад", callback_data="wallet_menu")
        builder.adjust(1)
        
        await callback.message.edit_text(text, reply_markup=builder.as_markup())
        await callback.answer()
    
    async def add_wallet_start(self, callback: types.CallbackQuery, state: FSMContext):
        """Начало добавления кошелька."""
        # Проверяем лимит
        user_alerts = self.wallet_service.get_user_alerts(callback.from_user.id)
        if len(user_alerts) >= 5:
            await callback.answer("❌ Максимум 5 кошельков на пользователя")
            return
        
        await state.set_state(WalletStates.waiting_address)
        
        builder = InlineKeyboardBuilder()
        builder.button(text="❌ Отмена", callback_data="wallet_menu")
        
        await callback.message.edit_text(
            "👛 Добавление кошелька\n\n"
            "Введите Ethereum адрес кошелька:\n"
            "Формат: 0x1234567890abcdef...",
            reply_markup=builder.as_markup()
        )
        await callback.answer()
    
    async def process_wallet_address(self, message: types.Message, state: FSMContext):
        """Обработка адреса кошелька."""
        address = message.text.strip()
        
        # Валидация адреса
        if not self.wallet_service._is_valid_eth_address(address):
            await message.answer("❌ Некорректный Ethereum адрес. Попробуйте еще раз:")
            return
        
        await state.update_data(wallet_address=address)
        await state.set_state(WalletStates.waiting_min_value)
        
        builder = InlineKeyboardBuilder()
        builder.button(text="0 ETH", callback_data="wallet_min_0")
        builder.button(text="0.01 ETH", callback_data="wallet_min_0.01")
        builder.button(text="0.1 ETH", callback_data="wallet_min_0.1")
        builder.button(text="1 ETH", callback_data="wallet_min_1")
        builder.button(text="Ввести вручную", callback_data="wallet_min_custom")
        builder.button(text="❌ Отмена", callback_data="wallet_menu")
        builder.adjust(2)
        
        await message.answer(
            f"✅ Адрес: {address[:6]}...{address[-4:]}\n\n"
            "Минимальная сумма для уведомлений:",
            reply_markup=builder.as_markup()
        )
    
    async def process_min_value(self, callback: types.CallbackQuery, state: FSMContext):
        """Обработка минимальной суммы."""
        if callback.data == "wallet_min_custom":
            await callback.message.answer("Введите минимальную сумму в ETH (например: 0.5):")
            return
        
        # Извлекаем значение из callback_data
        min_value = float(callback.data.split("_")[-1])
        await state.update_data(min_value_eth=min_value)
        await state.set_state(WalletStates.waiting_track_options)
        
        builder = InlineKeyboardBuilder()
        builder.button(text="📥 Только входящие", callback_data="wallet_track_in")
        builder.button(text="📤 Только исходящие", callback_data="wallet_track_out")
        builder.button(text="📥📤 Все транзакции", callback_data="wallet_track_both")
        builder.button(text="❌ Отмена", callback_data="wallet_menu")
        builder.adjust(1)
        
        await callback.message.edit_text(
            f"Минимальная сумма: {min_value} ETH\n\n"
            "Какие транзакции отслеживать?",
            reply_markup=builder.as_markup()
        )
        await callback.answer()
    
    async def process_custom_min_value(self, message: types.Message, state: FSMContext):
        """Обработка пользовательской минимальной суммы."""
        try:
            min_value = float(message.text.strip())
            
            if min_value < 0 or min_value > 1000:
                await message.answer("❌ Введите значение от 0 до 1000 ETH")
                return
            
            await state.update_data(min_value_eth=min_value)
            await state.set_state(WalletStates.waiting_track_options)
            
            builder = InlineKeyboardBuilder()
            builder.button(text="📥 Только входящие", callback_data="wallet_track_in")
            builder.button(text="📤 Только исходящие", callback_data="wallet_track_out")
            builder.button(text="📥📤 Все транзакции", callback_data="wallet_track_both")
            builder.button(text="❌ Отмена", callback_data="wallet_menu")
            builder.adjust(1)
            
            await message.answer(
                f"Минимальная сумма: {min_value} ETH\n\n"
                "Какие транзакции отслеживать?",
                reply_markup=builder.as_markup()
            )
            
        except ValueError:
            await message.answer("❌ Введите корректное число")
    
    async def process_track_options(self, callback: types.CallbackQuery, state: FSMContext):
        """Обработка опций отслеживания."""
        data = await state.get_data()
        wallet_address = data.get('wallet_address')
        min_value_eth = data.get('min_value_eth', 0.0)
        
        track_type = callback.data.split("_")[-1]
        track_incoming = track_type in ['in', 'both']
        track_outgoing = track_type in ['out', 'both']
        
        # Добавляем алерт
        success = await self.wallet_service.add_wallet_alert(
            callback.from_user.id,
            wallet_address,
            min_value_eth,
            track_incoming,
            track_outgoing
        )
        
        await state.clear()
        
        if success:
            track_text = []
            if track_incoming:
                track_text.append("входящие")
            if track_outgoing:
                track_text.append("исходящие")
            
            text = (
                f"✅ Кошелек добавлен!\n\n"
                f"👛 {wallet_address[:6]}...{wallet_address[-4:]}\n"
                f"💰 Мин. сумма: {min_value_eth} ETH\n"
                f"📊 Отслеживание: {' и '.join(track_text)}\n\n"
                f"⚠️ Задержка обнаружения: 2-10 минут"
            )
        else:
            text = "❌ Ошибка при добавлении кошелька"
        
        # Возвращаемся в меню кошельков
        await self.show_wallet_menu(callback)
        
        # Отправляем уведомление
        await callback.message.answer(text)
    
    async def remove_wallet(self, callback: types.CallbackQuery):
        """Удаление кошелька."""
        wallet_address = callback.data.split("_", 2)[-1]
        
        success = await self.wallet_service.remove_wallet_alert(
            callback.from_user.id,
            wallet_address
        )
        
        if success:
            text = f"✅ Кошелек {wallet_address[:6]}...{wallet_address[-4:]} удален"
        else:
            text = "❌ Ошибка при удалении кошелька"
        
        await callback.answer(text)
        
        # Обновляем список
        await self.show_wallet_list(callback)
    
    async def check_wallet(self, callback: types.CallbackQuery, state: FSMContext):
        """Проверка кошелька по запросу."""
        await callback.message.answer("🔍 Введите адрес кошелька для проверки:")
        await state.set_state(WalletStates.waiting_address)
        await callback.answer()
    
    async def process_wallet_check(self, message: types.Message, state: FSMContext):
        """Обработка проверки кошелька."""
        address = message.text.strip()
        
        if not self.wallet_service._is_valid_eth_address(address):
            await message.answer("❌ Некорректный Ethereum адрес")
            return
        
        await state.clear()
        
        # Показываем индикатор загрузки
        loading_msg = await message.answer("🔍 Проверяю кошелек...")
        
        try:
            wallet_info = await self.wallet_service.get_wallet_info(address)
            
            if wallet_info:
                from datetime import datetime
                
                text = (
                    f"👛 Информация о кошельке\n\n"
                    f"📍 Адрес: {address[:10]}...{address[-6:]}\n"
                    f"💰 Баланс: {wallet_info['balance_eth']:.4f} ETH\n"
                    f"💵 ~${wallet_info['balance_usd']:.2f}\n"
                    f"📊 Недавних транзакций: {wallet_info['recent_transactions_count']}\n"
                )
                
                if wallet_info['last_activity']:
                    last_activity = datetime.fromtimestamp(int(wallet_info['last_activity']))
                    text += f"🕐 Последняя активность: {last_activity.strftime('%d.%m.%Y %H:%M')}"
                else:
                    text += "🕐 Нет недавней активности"
                
            else:
                text = f"❌ Не удалось получить информацию о кошельке {address[:10]}..."
                
        except Exception as e:
            text = "❌ Ошибка при проверке кошелька"
        
        await loading_msg.edit_text(text)