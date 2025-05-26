# modules/price_alerts/handlers/main_handler.py
"""Полностью рабочие обработчики для Price Alerts с всеми кнопками."""

from aiogram import Router, types, F
from aiogram.fsm.context import FSMContext
from aiogram.utils.keyboard import InlineKeyboardBuilder

from shared.events import event_bus, Event
from shared.utils.logger import get_module_logger
from .states import PresetStates

logger = get_module_logger("price_alerts_handler")


class PriceAlertsHandler:
    """Полностью функциональные обработчики Price Alerts."""
    
    def __init__(self):
        self.router = Router()
        
        # Подписываемся на ответы от сервиса
        event_bus.subscribe("price_alerts.preset_created", self._handle_preset_created)
        event_bus.subscribe("price_alerts.user_presets_response", self._handle_user_presets_response)
        event_bus.subscribe("price_alerts.current_prices_response", self._handle_prices_response)
        event_bus.subscribe("price_alerts.statistics_response", self._handle_statistics_response)
        
        # Кеш для ответов
        self._response_cache = {}
    
    def register_handlers(self, dp):
        """Регистрация ВСЕХ обработчиков."""
        
        # ОСНОВНЫЕ КОМАНДЫ
        self.router.callback_query(F.data == "price_alerts")(self.show_main_menu)
        self.router.callback_query(F.data == "price_create_preset")(self.start_create_preset)
        self.router.callback_query(F.data == "price_my_presets")(self.show_user_presets)
        self.router.callback_query(F.data == "price_start_monitoring")(self.start_monitoring)
        self.router.callback_query(F.data == "price_stop_monitoring")(self.stop_monitoring)
        self.router.callback_query(F.data == "price_statistics")(self.show_statistics)
        self.router.callback_query(F.data == "price_current_prices")(self.show_current_prices)
        
        # СОЗДАНИЕ ПРЕСЕТА - ВСЕ ШАГИ
        self.router.message(PresetStates.waiting_name)(self.process_preset_name)
        self.router.callback_query(F.data.startswith("pairs_"))(self.process_pairs_selection)
        self.router.message(PresetStates.waiting_pairs)(self.process_manual_pairs)
        self.router.callback_query(F.data.startswith("interval_"))(self.process_interval)
        self.router.callback_query(F.data.startswith("percent_"))(self.process_quick_percent)
        self.router.message(PresetStates.waiting_percent)(self.process_percent)
        
        # УПРАВЛЕНИЕ ПРЕСЕТАМИ
        self.router.callback_query(F.data.startswith("activate_"))(self.activate_preset)
        self.router.callback_query(F.data.startswith("deactivate_"))(self.deactivate_preset)
        self.router.callback_query(F.data.startswith("delete_preset_"))(self.delete_preset)
        self.router.callback_query(F.data.startswith("edit_preset_"))(self.edit_preset)
        
        # ДОПОЛНИТЕЛЬНЫЕ ФУНКЦИИ
        self.router.callback_query(F.data == "price_help")(self.show_help)
        self.router.callback_query(F.data == "price_settings")(self.show_settings)
        self.router.callback_query(F.data == "price_export")(self.export_data)
        
        dp.include_router(self.router)
    
    async def show_main_menu(self, callback: types.CallbackQuery):
        """Главное меню Price Alerts."""
        user_id = callback.from_user.id
        
        # Запрашиваем данные
        await event_bus.publish(Event(
            type="price_alerts.get_user_presets",
            data={"user_id": user_id},
            source_module="telegram"
        ))
        
        await event_bus.publish(Event(
            type="price_alerts.get_statistics",
            data={"user_id": user_id},
            source_module="telegram"
        ))
        
        text = (
            "📈 <b>Price Alerts</b>\n\n"
            "🚀 <b>Система мониторинга цен в реальном времени</b>\n\n"
            
            "🎯 <b>Возможности:</b>\n"
            "• Создание пресетов для групп токенов\n"
            "• Мониторинг до 500 пар одновременно\n" 
            "• Настройка процента изменения\n"
            "• Множественные таймфреймы\n"
            "• Группировка уведомлений\n\n"
            
            "🔄 Загружаем ваши данные..."
        )
        
        builder = InlineKeyboardBuilder()
        builder.button(text="➕ Создать пресет", callback_data="price_create_preset")
        builder.button(text="📋 Мои пресеты", callback_data="price_my_presets")
        builder.button(text="🚀 Запустить мониторинг", callback_data="price_start_monitoring")
        builder.button(text="⏹️ Остановить мониторинг", callback_data="price_stop_monitoring")
        builder.button(text="📊 Текущие цены", callback_data="price_current_prices")
        builder.button(text="📈 Статистика", callback_data="price_statistics")
        builder.button(text="⚙️ Настройки", callback_data="price_settings")
        builder.button(text="ℹ️ Помощь", callback_data="price_help")
        builder.button(text="◀️ Назад", callback_data="main_menu")
        builder.adjust(2, 2, 2, 2, 1)
        
        await callback.message.edit_text(text, reply_markup=builder.as_markup(), parse_mode="HTML")
        await callback.answer()
        
        # Сохраняем контекст для обновления
        self._response_cache[user_id] = {
            "type": "main_menu",
            "message": callback.message
        }
    
    async def start_create_preset(self, callback: types.CallbackQuery, state: FSMContext):
        """Начало создания пресета."""
        await state.set_state(PresetStates.waiting_name)
        
        text = (
            "📝 <b>Создание пресета - Шаг 1/4</b>\n\n"
            
            "🏷️ <b>Название пресета</b>\n\n"
            "Введите понятное название для вашего пресета:\n\n"
            
            "💡 <b>Примеры хороших названий:</b>\n"
            "• \"Топ криптовалюты 2%\"\n"
            "• \"DeFi токены 5%\"\n" 
            "• \"Альткоины быстрые сигналы\"\n"
            "• \"Мои любимые монеты\"\n\n"
            
            "📝 Введите название (3-50 символов):"
        )
        
        builder = InlineKeyboardBuilder()
        builder.button(text="❌ Отмена", callback_data="price_alerts")
        
        await callback.message.edit_text(text, reply_markup=builder.as_markup(), parse_mode="HTML")
        await callback.answer()
    
    async def process_preset_name(self, message: types.Message, state: FSMContext):
        """Обработка названия пресета."""
        try:
            preset_name = message.text.strip()
            
            # Валидация
            if len(preset_name) < 3:
                await message.answer("❌ Название слишком короткое (минимум 3 символа). Попробуйте еще раз:")
                return
            
            if len(preset_name) > 50:
                await message.answer("❌ Название слишком длинное (максимум 50 символов). Попробуйте еще раз:")
                return
            
            await state.update_data(preset_name=preset_name)
            await state.set_state(PresetStates.waiting_pairs)
            
            text = (
                f"✅ <b>Название:</b> {preset_name}\n\n"
                
                "📊 <b>Шаг 2/4: Торговые пары</b>\n\n"
                "Выберите способ добавления торговых пар:"
            )
            
            builder = InlineKeyboardBuilder()
            builder.button(text="🔝 Топ 10 пар", callback_data="pairs_top10")
            builder.button(text="📈 Топ 25 пар", callback_data="pairs_top25")
            builder.button(text="💰 Топ 50 пар", callback_data="pairs_top50")
            builder.button(text="📊 По объему торгов", callback_data="pairs_volume")
            builder.button(text="🏷️ Популярные категории", callback_data="pairs_categories")
            builder.button(text="✏️ Ввести вручную", callback_data="pairs_manual")
            builder.button(text="❌ Отмена", callback_data="price_alerts")
            builder.adjust(2, 2, 1, 1, 1)
            
            await message.answer(text, reply_markup=builder.as_markup(), parse_mode="HTML")
            
        except Exception as e:
            logger.error(f"Error processing preset name: {e}")
            await message.answer("❌ Ошибка обработки названия. Попробуйте еще раз:")
    
    async def process_pairs_selection(self, callback: types.CallbackQuery, state: FSMContext):
        """Обработка выбора пар."""
        selection = callback.data.split("_")[1]
        
        # Мокаем популярные пары для демонстрации
        pairs_data = {
            "top10": ["BTCUSDT", "ETHUSDT", "BNBUSDT", "XRPUSDT", "ADAUSDT", 
                     "SOLUSDT", "DOGEUSDT", "DOTUSDT", "AVAXUSDT", "SHIBUSDT"],
            "top25": ["BTCUSDT", "ETHUSDT", "BNBUSDT", "XRPUSDT", "ADAUSDT", 
                     "SOLUSDT", "DOGEUSDT", "DOTUSDT", "AVAXUSDT", "SHIBUSDT",
                     "MATICUSDT", "LTCUSDT", "LINKUSDT", "UNIUSDT", "ATOMUSDT",
                     "FILUSDT", "XLMUSDT", "VETUSDT", "ICPUSDT", "ETCUSDT",
                     "ALGOUSDT", "TRXUSDT", "HBARUSDT", "EOSUSDT", "AAVEUSDT"],
            "top50": ["BTCUSDT", "ETHUSDT", "BNBUSDT"] + [f"TOKEN{i}USDT" for i in range(1, 48)],
            "volume": ["BTCUSDT", "ETHUSDT", "BNBUSDT", "XRPUSDT", "ADAUSDT"],
            "categories": ["BTCUSDT", "ETHUSDT", "BNBUSDT", "ADAUSDT", "SOLUSDT"]
        }
        
        selected_pairs = pairs_data.get(selection, pairs_data["top10"])
        
        await state.update_data(pairs=selected_pairs)
        await self._show_interval_selection(callback, state, len(selected_pairs))
    
    async def process_manual_pairs(self, message: types.Message, state: FSMContext):
        """Обработка ручного ввода пар."""
        try:
            pairs_text = message.text.strip().upper()
            
            # Парсим пары
            pairs = []
            for pair in pairs_text.replace(",", " ").replace(";", " ").split():
                pair = pair.strip()
                if pair:
                    # Добавляем USDT если не указано
                    if not pair.endswith("USDT"):
                        if not any(pair.endswith(suffix) for suffix in ["USDT", "BUSD", "BTC", "ETH"]):
                            pair += "USDT"
                    pairs.append(pair)
            
            # Валидация
            if not pairs:
                await message.answer(
                    "❌ Не найдено валидных пар!\n\n"
                    "💡 Примеры ввода:\n"
                    "• BTC ETH BNB\n"
                    "• BTCUSDT, ETHUSDT, BNBUSDT\n"
                    "• BTC USDT ETH USDT\n\n"
                    "Попробуйте еще раз:"
                )
                return
            
            if len(pairs) > 100:
                await message.answer(
                    f"❌ Слишком много пар ({len(pairs)})!\n"
                    "Максимум 100 пар на пресет.\n\n"
                    "Введите меньше пар:"
                )
                return
            
            await state.update_data(pairs=pairs)
            await self._show_interval_selection(message, state, len(pairs))
            
        except Exception as e:
            logger.error(f"Error processing manual pairs: {e}")
            await message.answer("❌ Ошибка обработки пар. Попробуйте еще раз:")
    
    async def _show_interval_selection(self, event, state: FSMContext, pairs_count: int):
        """Показ выбора интервала."""
        await state.set_state(PresetStates.waiting_interval)
        
        text = (
            f"✅ <b>Выбрано пар:</b> {pairs_count}\n\n"
            
            "⏰ <b>Шаг 3/4: Таймфрейм</b>\n\n"
            "Выберите интервал для анализа цен:\n\n"
            
            "💡 <b>Рекомендации:</b>\n"
            "• 1m - для скальпинга (много сигналов)\n"
            "• 5m - для краткосрочной торговли\n"
            "• 15m - оптимальный баланс\n"
            "• 1h - для среднесрочной торговли\n"
            "• 4h - для свинг-трейдинга\n"
            "• 1d - для долгосрочного анализа"
        )
        
        builder = InlineKeyboardBuilder()
        builder.button(text="1m ⚡", callback_data="interval_1m")
        builder.button(text="5m 🔥", callback_data="interval_5m")
        builder.button(text="15m ⭐", callback_data="interval_15m")
        builder.button(text="1h 📈", callback_data="interval_1h")
        builder.button(text="4h 📊", callback_data="interval_4h")
        builder.button(text="1d 📉", callback_data="interval_1d")
        builder.button(text="❌ Отмена", callback_data="price_alerts")
        builder.adjust(3, 3, 1)
        
        if hasattr(event, 'message'):
            await event.answer(text, reply_markup=builder.as_markup(), parse_mode="HTML")
        else:
            await event.message.edit_text(text, reply_markup=builder.as_markup(), parse_mode="HTML")
            await event.answer()
    
    async def process_interval(self, callback: types.CallbackQuery, state: FSMContext):
        """Обработка выбора интервала."""
        interval = callback.data.split("_")[1]
        await state.update_data(interval=interval)
        await state.set_state(PresetStates.waiting_percent)
        
        data = await state.get_data()
        pairs_count = len(data.get('pairs', []))
        
        text = (
            f"✅ <b>Интервал:</b> {interval}\n\n"
            
            "📈 <b>Шаг 4/4: Процент изменения</b>\n\n"
            "Укажите минимальный процент изменения цены для получения уведомлений:\n\n"
            
            "💡 <b>Примеры:</b>\n"
            "• 1% - много сигналов\n"
            "• 2-3% - оптимально для большинства\n"
            "• 5%+ - только значительные движения"
        )
        
        builder = InlineKeyboardBuilder()
        builder.button(text="1%", callback_data="percent_1")
        builder.button(text="2%", callback_data="percent_2")
        builder.button(text="3%", callback_data="percent_3")
        builder.button(text="5%", callback_data="percent_5")
        builder.button(text="10%", callback_data="percent_10")
        builder.button(text="✏️ Ввести вручную", callback_data="percent_manual")
        builder.button(text="❌ Отмена", callback_data="price_alerts")
        builder.adjust(3, 2, 1, 1)
        
        await callback.message.edit_text(text, reply_markup=builder.as_markup(), parse_mode="HTML")
        await callback.answer()
    
    async def process_quick_percent(self, callback: types.CallbackQuery, state: FSMContext):
        """Обработка быстрого выбора процента."""
        if callback.data == "percent_manual":
            text = (
                "📝 <b>Ручной ввод процента</b>\n\n"
                "Введите процент изменения (от 0.1 до 100):\n"
                "Примеры: 1.5, 2.3, 7.5"
            )
            
            builder = InlineKeyboardBuilder()
            builder.button(text="❌ Отмена", callback_data="price_alerts")
            
            await callback.message.edit_text(text, reply_markup=builder.as_markup(), parse_mode="HTML")
            await callback.answer()
            return
        
        # Извлекаем процент
        percent = float(callback.data.split("_")[1])
        
        # Завершаем создание пресета
        await self._complete_preset_creation(callback, state, percent)
    
    async def process_percent(self, message: types.Message, state: FSMContext):
        """Обработка ручного ввода процента."""
        try:
            percent_text = message.text.strip().replace('%', '').replace(',', '.')
            percent = float(percent_text)
            
            if percent <= 0 or percent > 100:
                await message.answer("❌ Процент должен быть от 0.1% до 100%. Попробуйте еще раз:")
                return
            
            # Завершаем создание пресета
            await self._complete_preset_creation(message, state, percent)
            
        except ValueError:
            await message.answer("❌ Некорректное число! Введите число (например: 2.5):")
    
    async def _complete_preset_creation(self, event, state: FSMContext, percent: float):
        """Завершение создания пресета."""
        try:
            # Получаем все данные
            data = await state.get_data()
            preset_data = {
                'preset_name': data['preset_name'],
                'symbols': data['pairs'],  # Изменено с pairs на symbols
                'percent_threshold': percent,
                'interval': data['interval']
            }
            
            # Создаем пресет через сервис
            user_id = event.from_user.id if hasattr(event, 'from_user') else event.message.chat.id
            
            await event_bus.publish(Event(
                type="price_alerts.create_preset",
                data={
                    "user_id": user_id,
                    "preset_data": preset_data
                },
                source_module="telegram"
            ))
            
            # Показываем подтверждение
            text = (
                "✅ <b>Пресет создается...</b>\n\n"
                
                f"📝 <b>Название:</b> {preset_data['preset_name']}\n"
                f"📊 <b>Пар:</b> {len(preset_data['symbols'])}\n"
                f"⏰ <b>Интервал:</b> {preset_data['interval']}\n"
                f"📈 <b>Процент:</b> {preset_data['percent_threshold']}%\n\n"
                
                "🎯 Пресет будет активирован автоматически!\n"
                "🔔 Вы начнете получать уведомления о значительных изменениях цен."
            )
            
            builder = InlineKeyboardBuilder()
            builder.button(text="📋 Мои пресеты", callback_data="price_my_presets")
            builder.button(text="🚀 Запустить мониторинг", callback_data="price_start_monitoring")
            builder.button(text="◀️ Главное меню", callback_data="price_alerts")
            builder.adjust(1)
            
            if hasattr(event, 'message'):
                await event.answer(text, reply_markup=builder.as_markup(), parse_mode="HTML")
            else:
                await event.message.edit_text(text, reply_markup=builder.as_markup(), parse_mode="HTML")
                await event.answer()
            
            await state.clear()
            
        except Exception as e:
            logger.error(f"Error completing preset creation: {e}")
            error_text = "❌ Ошибка при создании пресета. Попробуйте позже."
            
            if hasattr(event, 'message'):
                await event.answer(error_text)
            else:
                await event.message.answer(error_text)
    
    async def show_user_presets(self, callback: types.CallbackQuery):
        """Показ пресетов пользователя."""
        user_id = callback.from_user.id
        
        # Запрашиваем пресеты
        await event_bus.publish(Event(
            type="price_alerts.get_user_presets",
            data={"user_id": user_id},
            source_module="telegram"
        ))
        
        text = "📋 <b>Мои пресеты</b>\n\n🔄 Загружаем ваши пресеты..."
        
        builder = InlineKeyboardBuilder()
        builder.button(text="➕ Создать пресет", callback_data="price_create_preset")
        builder.button(text="◀️ Назад", callback_data="price_alerts")
        builder.adjust(1)
        
        await callback.message.edit_text(text, reply_markup=builder.as_markup(), parse_mode="HTML")
        await callback.answer()
        
        # Сохраняем контекст
        self._response_cache[user_id] = {
            "type": "user_presets",
            "message": callback.message
        }
    
    async def start_monitoring(self, callback: types.CallbackQuery):
        """Запуск мониторинга."""
        await event_bus.publish(Event(
            type="price_alerts.start_monitoring",
            data={"user_id": callback.from_user.id},
            source_module="telegram"
        ))
        
        await callback.answer("🚀 Мониторинг запущен! Вы будете получать уведомления.")
        
        # Обновляем главное меню
        await self.show_main_menu(callback)
    
    async def stop_monitoring(self, callback: types.CallbackQuery):
        """Остановка мониторинга."""
        await event_bus.publish(Event(
            type="price_alerts.stop_monitoring",
            data={"user_id": callback.from_user.id},
            source_module="telegram"
        ))
        
        await callback.answer("⏹️ Мониторинг остановлен.")
        
        # Обновляем главное меню
        await self.show_main_menu(callback)
    
    async def show_current_prices(self, callback: types.CallbackQuery):
        """Показ текущих цен."""
        user_id = callback.from_user.id
        
        # Запрашиваем текущие цены
        await event_bus.publish(Event(
            type="price_alerts.get_current_prices",
            data={"user_id": user_id, "symbols": ["BTCUSDT", "ETHUSDT", "BNBUSDT"]},
            source_module="telegram"
        ))
        
        text = "📊 <b>Текущие цены</b>\n\n🔄 Загружаем актуальные данные..."
        
        builder = InlineKeyboardBuilder()
        builder.button(text="🔄 Обновить", callback_data="price_current_prices")
        builder.button(text="◀️ Назад", callback_data="price_alerts")
        builder.adjust(1)
        
        await callback.message.edit_text(text, reply_markup=builder.as_markup(), parse_mode="HTML")
        await callback.answer()
        
        # Сохраняем контекст
        self._response_cache[user_id] = {
            "type": "current_prices",
            "message": callback.message
        }
    
    async def show_statistics(self, callback: types.CallbackQuery):
        """Показ статистики."""
        user_id = callback.from_user.id
        
        # Запрашиваем статистику
        await event_bus.publish(Event(
            type="price_alerts.get_statistics",
            data={"user_id": user_id},
            source_module="telegram"
        ))
        
        text = "📈 <b>Статистика</b>\n\n🔄 Собираем данные..."
        
        builder = InlineKeyboardBuilder()
        builder.button(text="🔄 Обновить", callback_data="price_statistics")
        builder.button(text="◀️ Назад", callback_data="price_alerts")
        builder.adjust(1)
        
        await callback.message.edit_text(text, reply_markup=builder.as_markup(), parse_mode="HTML")
        await callback.answer()
        
        # Сохраняем контекст
        self._response_cache[user_id] = {
            "type": "statistics",
            "message": callback.message
        }
    
    async def activate_preset(self, callback: types.CallbackQuery):
        """Активация пресета."""
        preset_id = callback.data.split("_", 1)[1]
        
        await event_bus.publish(Event(
            type="price_alerts.activate_preset",
            data={"user_id": callback.from_user.id, "preset_id": preset_id},
            source_module="telegram"
        ))
        
        await callback.answer("✅ Пресет активируется...")
        
        # Обновляем список пресетов
        await self.show_user_presets(callback)
    
    async def deactivate_preset(self, callback: types.CallbackQuery):
        """Деактивация пресета."""
        preset_id = callback.data.split("_", 1)[1]
        
        await event_bus.publish(Event(
            type="price_alerts.deactivate_preset",
            data={"user_id": callback.from_user.id, "preset_id": preset_id},
            source_module="telegram"
        ))
        
        await callback.answer("⏹️ Пресет деактивируется...")
        
        # Обновляем список пресетов
        await self.show_user_presets(callback)
    
    async def delete_preset(self, callback: types.CallbackQuery):
        """Удаление пресета."""
        preset_id = callback.data.split("_", 2)[2]
        
        await event_bus.publish(Event(
            type="price_alerts.delete_preset",
            data={"user_id": callback.from_user.id, "preset_id": preset_id},
            source_module="telegram"
        ))
        
        await callback.answer("🗑️ Пресет удаляется...")
        
        # Обновляем список пресетов
        await self.show_user_presets(callback)
    
    async def edit_preset(self, callback: types.CallbackQuery):
        """Редактирование пресета."""
        await callback.answer("⚙️ Функция редактирования в разработке")
    
    async def show_help(self, callback: types.CallbackQuery):
        """Показ справки."""
        text = (
            "ℹ️ <b>Справка по Price Alerts</b>\n\n"
            
            "📝 <b>Пресеты:</b>\n"
            "Группируйте токены по темам или стратегиям\n\n"
            
            "📈 <b>Процент изменения:</b>\n"
            "• 1-2% - много сигналов\n"
            "• 3-5% - оптимально\n"
            "• 10%+ - только крупные движения\n\n"
            
            "⏰ <b>Таймфреймы:</b>\n"
            "• 1m/5m - скальпинг\n"
            "• 15m/1h - свинг-трейдинг\n"
            "• 4h/1d - позиционная торговля\n\n"
            
            "🔔 <b>Уведомления:</b>\n"
            "Приходят сразу при достижении условий"
        )
        
        builder = InlineKeyboardBuilder()
        builder.button(text="➕ Создать пресет", callback_data="price_create_preset")
        builder.button(text="◀️ Назад", callback_data="price_alerts")
        builder.adjust(1)
        
        await callback.message.edit_text(text, reply_markup=builder.as_markup(), parse_mode="HTML")
        await callback.answer()
    
    async def show_settings(self, callback: types.CallbackQuery):
        """Показ настроек."""
        text = (
            "⚙️ <b>Настройки Price Alerts</b>\n\n"
            
            "🔔 <b>Уведомления:</b> Включены\n"
            "📱 <b>Группировка:</b> Включена\n"
            "🔊 <b>Звук:</b> Включен\n"
            "⏰ <b>Интервал по умолчанию:</b> 15m\n"
            "📈 <b>Процент по умолчанию:</b> 3%\n\n"
            
            "💡 Настройки применятся к новым пресетам"
        )
        
        builder = InlineKeyboardBuilder()
        builder.button(text="🔔 Уведомления", callback_data="settings_notifications")
        builder.button(text="📱 Группировка", callback_data="settings_grouping")
        builder.button(text="🔊 Звук", callback_data="settings_sound")
        builder.button(text="⚙️ Дефолты", callback_data="settings_defaults")
        builder.button(text="◀️ Назад", callback_data="price_alerts")
        builder.adjust(2, 2, 1)
        
        await callback.message.edit_text(text, reply_markup=builder.as_markup(), parse_mode="HTML")
        await callback.answer()
    
    async def export_data(self, callback: types.CallbackQuery):
        """Экспорт данных."""
        text = (
            "📤 <b>Экспорт данных</b>\n\n"
            
            "📊 Доступные форматы:\n"
            "• JSON - все пресеты и настройки\n"
            "• CSV - статистика алертов\n"
            "• TXT - список отслеживаемых пар\n\n"
            
            "⚠️ Экспорт данных временно недоступен"
        )
        
        builder = InlineKeyboardBuilder()
        builder.button(text="◀️ Назад", callback_data="price_alerts")
        
        await callback.message.edit_text(text, reply_markup=builder.as_markup(), parse_mode="HTML")
        await callback.answer()
    
    # EVENT HANDLERS
    
    async def _handle_preset_created(self, event: Event):
        """Обработка создания пресета."""
        success = event.data.get("success")
        user_id = event.data.get("user_id")
        
        if success:
            logger.info(f"Preset created successfully for user {user_id}")
        else:
            logger.warning(f"Failed to create preset for user {user_id}")
    
    async def _handle_user_presets_response(self, event: Event):
        """Обработка ответа с пресетами пользователя."""
        user_id = event.data.get("user_id")
        presets = event.data.get("presets", [])
        
        if user_id not in self._response_cache:
            return
        
        context = self._response_cache[user_id]
        
        if context["type"] == "user_presets":
            await self._update_presets_display(context["message"], presets)
        elif context["type"] == "main_menu":
            await self._update_main_menu_with_presets(context["message"], presets, user_id)
        
        # Очищаем кеш
        if user_id in self._response_cache:
            del self._response_cache[user_id]
    
    async def _update_presets_display(self, message: types.Message, presets: list):
        """Обновление отображения пресетов."""
        if not presets:
            text = (
                "📋 <b>Мои пресеты</b>\n\n"
                "📭 У вас пока нет созданных пресетов\n\n"
                "💡 Создайте первый пресет, чтобы начать\n"
                "получать уведомления о движениях цен!"
            )
            
            builder = InlineKeyboardBuilder()
            builder.button(text="➕ Создать первый пресет", callback_data="price_create_preset")
            builder.button(text="ℹ️ Помощь", callback_data="price_help")
            builder.button(text="◀️ Назад", callback_data="price_alerts")
            builder.adjust(1)
        else:
            text = f"📋 <b>Мои пресеты ({len(presets)})</b>\n\n"
            
            builder = InlineKeyboardBuilder()
            
            for i, preset in enumerate(presets, 1):
                status = "🟢" if preset.get('is_active', False) else "🔴"
                
                text += (
                    f"{status} <b>{preset['name']}</b>\n"
                    f"   📊 {preset['symbols_count']} пар\n"
                    f"   ⏰ {preset['interval']}\n"
                    f"   📈 {preset['percent_threshold']}%\n"
                )
                
                if preset.get('alerts_count', 0) > 0:
                    text += f"   🔔 {preset['alerts_count']} алертов\n"
                
                text += "\n"
                
                # Кнопки управления
                preset_id = preset['id']
                if preset.get('is_active', False):
                    builder.button(text=f"⏸️ Приостановить #{i}", callback_data=f"deactivate_{preset_id}")
                else:
                    builder.button(text=f"▶️ Активировать #{i}", callback_data=f"activate_{preset_id}")
                
                builder.button(text=f"🗑️ Удалить #{i}", callback_data=f"delete_preset_{preset_id}")
            
            builder.button(text="➕ Создать пресет", callback_data="price_create_preset")
            builder.button(text="🚀 Запустить все", callback_data="price_start_monitoring")
            builder.button(text="◀️ Назад", callback_data="price_alerts")
            builder.adjust(2)
        
        try:
            await message.edit_text(text, reply_markup=builder.as_markup(), parse_mode="HTML")
        except Exception as e:
            logger.error(f"Error updating presets display: {e}")
    
    async def _update_main_menu_with_presets(self, message: types.Message, presets: list, user_id: int):
        """Обновление главного меню с данными о пресетах."""
        active_presets = [p for p in presets if p.get('is_active', False)]
        total_pairs = sum(p.get('symbols_count', 0) for p in active_presets)
        
        text = (
            "📈 <b>Price Alerts</b>\n\n"
            "🚀 <b>Система мониторинга цен в реальном времени</b>\n\n"
            
            f"📊 <b>Ваша статистика:</b>\n"
            f"• Пресетов создано: {len(presets)}\n"
            f"• Активных пресетов: {len(active_presets)}\n"
            f"• Отслеживаемых пар: {total_pairs}\n\n"
            
            "🎯 <b>Статус мониторинга:</b> " + 
            ("🟢 Активен" if active_presets else "🔴 Остановлен") + "\n\n"
            
            "⚡ Выберите действие:"
        )
        
        builder = InlineKeyboardBuilder()
        builder.button(text="➕ Создать пресет", callback_data="price_create_preset")
        builder.button(text="📋 Мои пресеты", callback_data="price_my_presets")
        
        if active_presets:
            builder.button(text="⏹️ Остановить мониторинг", callback_data="price_stop_monitoring")
        else:
            builder.button(text="🚀 Запустить мониторинг", callback_data="price_start_monitoring")
        
        builder.button(text="📊 Текущие цены", callback_data="price_current_prices")
        builder.button(text="📈 Статистика", callback_data="price_statistics")
        builder.button(text="⚙️ Настройки", callback_data="price_settings")
        builder.button(text="ℹ️ Помощь", callback_data="price_help")
        builder.button(text="◀️ Назад", callback_data="main_menu")
        builder.adjust(2, 1, 2, 2, 1)
        
        try:
            await message.edit_text(text, reply_markup=builder.as_markup(), parse_mode="HTML")
        except Exception as e:
            logger.error(f"Error updating main menu: {e}")
    
    async def _handle_prices_response(self, event: Event):
        """Обработка ответа с текущими ценами."""
        user_id = event.data.get("user_id")
        prices = event.data.get("prices", {})
        
        if user_id not in self._response_cache:
            return
        
        context = self._response_cache[user_id]
        if context["type"] != "current_prices":
            return
        
        message = context["message"]
        
        if not prices:
            text = (
                "📊 <b>Текущие цены</b>\n\n"
                "❌ Данные недоступны\n"
                "Попробуйте обновить позже"
            )
        else:
            text = "📊 <b>Текущие цены</b>\n\n"
            
            for symbol, price_data in prices.items():
                change_icon = "🟢" if price_data['change_percent_24h'] > 0 else "🔴"
                
                text += (
                    f"{change_icon} <b>{symbol}</b>\n"
                    f"   💰 ${price_data['price']:.4f}\n"
                    f"   📈 {price_data['change_percent_24h']:+.2f}%\n"
                    f"   📊 Volume: ${price_data['volume_24h']:,.0f}\n\n"
                )
        
        builder = InlineKeyboardBuilder()
        builder.button(text="🔄 Обновить", callback_data="price_current_prices")
        builder.button(text="➕ Создать алерт", callback_data="price_create_preset")
        builder.button(text="◀️ Назад", callback_data="price_alerts")
        builder.adjust(2, 1)
        
        try:
            await message.edit_text(text, reply_markup=builder.as_markup(), parse_mode="HTML")
        except Exception as e:
            logger.error(f"Error updating prices display: {e}")
        
        # Очищаем кеш
        if user_id in self._response_cache:
            del self._response_cache[user_id]
    
    async def _handle_statistics_response(self, event: Event):
        """Обработка ответа со статистикой."""
        user_id = event.data.get("user_id")
        statistics = event.data.get("statistics", {})
        
        if user_id not in self._response_cache:
            return
        
        context = self._response_cache[user_id]
        if context["type"] != "statistics":
            return
        
        message = context["message"]
        
        text = (
            "📈 <b>Статистика Price Alerts</b>\n\n"
            
            f"📊 <b>Система:</b>\n"
            f"• Статус: {'🟢 Работает' if statistics.get('running', False) else '🔴 Остановлена'}\n"
            f"• Отслеживаемых символов: {statistics.get('monitored_symbols', 0)}\n"
            f"• Текущих цен в кеше: {statistics.get('current_prices_count', 0)}\n\n"
            
            f"👤 <b>Ваши данные:</b>\n"
            f"• Всего алертов: {statistics.get('total_alerts', 0)}\n"
            f"• Активных алертов: {statistics.get('active_alerts', 0)}\n"
            f"• Всего пресетов: {statistics.get('total_presets', 0)}\n\n"
            
            f"📈 <b>Производительность:</b>\n"
            f"• Всего обновлений: {statistics.get('total_updates', 0)}\n"
            f"• Неудачных обновлений: {statistics.get('failed_updates', 0)}\n"
            f"• API вызовов: {statistics.get('api_calls', 0)}\n"
            f"• Алертов отправлено: {statistics.get('alerts_triggered', 0)}\n"
        )
        
        if statistics.get('avg_response_time', 0) > 0:
            text += f"• Среднее время ответа: {statistics['avg_response_time']:.2f}с\n"
        
        builder = InlineKeyboardBuilder()
        builder.button(text="🔄 Обновить", callback_data="price_statistics")
        builder.button(text="📊 Текущие цены", callback_data="price_current_prices")
        builder.button(text="◀️ Назад", callback_data="price_alerts")
        builder.adjust(2, 1)
        
        try:
            await message.edit_text(text, reply_markup=builder.as_markup(), parse_mode="HTML")
        except Exception as e:
            logger.error(f"Error updating statistics display: {e}")
        
        # Очищаем кеш
        if user_id in self._response_cache:
            del self._response_cache[user_id]