# shared/utils/rate_limiter.py
"""Полный ограничитель запросов для модульной архитектуры."""

import asyncio
import time
from typing import Dict, Optional, Any, List, Callable
from dataclasses import dataclass
from collections import defaultdict, deque
from enum import Enum
import logging

logger = logging.getLogger(__name__)


class RateLimitStrategy(Enum):
    """Стратегии ограничения запросов."""
    TOKEN_BUCKET = "token_bucket"
    SLIDING_WINDOW = "sliding_window"
    FIXED_WINDOW = "fixed_window"
    LEAKY_BUCKET = "leaky_bucket"


@dataclass
class RateLimitConfig:
    """Конфигурация ограничителя запросов."""
    requests_per_second: float = 5.0
    burst_size: int = 10
    window_size: int = 60  # seconds
    backoff_factor: float = 1.5
    max_backoff: float = 300.0  # 5 minutes
    strategy: RateLimitStrategy = RateLimitStrategy.TOKEN_BUCKET
    
    # API specific configs
    api_timeout: float = 30.0
    retry_attempts: int = 3
    cooldown_after_failures: int = 5  # consecutive failures before cooldown


@dataclass
class RateLimitResult:
    """Результат проверки rate limit."""
    allowed: bool
    wait_time: float = 0.0
    remaining: int = 0
    reset_time: float = 0.0
    retry_after: Optional[float] = None


class TokenBucket:
    """Реализация алгоритма Token Bucket."""
    
    def __init__(self, capacity: int, refill_rate: float):
        self.capacity = capacity
        self.tokens = capacity
        self.refill_rate = refill_rate
        self.last_refill = time.time()
        self._lock = asyncio.Lock()
    
    async def consume(self, tokens: int = 1) -> bool:
        """Попытка получить токены."""
        async with self._lock:
            self._refill()
            
            if self.tokens >= tokens:
                self.tokens -= tokens
                return True
            return False
    
    def _refill(self):
        """Пополнение токенов."""
        now = time.time()
        elapsed = now - self.last_refill
        
        tokens_to_add = elapsed * self.refill_rate
        self.tokens = min(self.capacity, self.tokens + tokens_to_add)
        self.last_refill = now
    
    def get_wait_time(self, tokens: int = 1) -> float:
        """Время ожидания до доступности токенов."""
        if self.tokens >= tokens:
            return 0.0
        
        needed_tokens = tokens - self.tokens
        return needed_tokens / self.refill_rate
    
    @property
    def available_tokens(self) -> int:
        """Количество доступных токенов."""
        self._refill()
        return int(self.tokens)


class SlidingWindowLimiter:
    """Реализация Sliding Window алгоритма."""
    
    def __init__(self, max_requests: int, window_size: int):
        self.max_requests = max_requests
        self.window_size = window_size
        self.requests: deque = deque()
        self._lock = asyncio.Lock()
    
    async def is_allowed(self) -> bool:
        """Проверка разрешения запроса."""
        async with self._lock:
            now = time.time()
            cutoff = now - self.window_size
            
            # Удаляем старые запросы
            while self.requests and self.requests[0] <= cutoff:
                self.requests.popleft()
            
            # Проверяем лимит
            if len(self.requests) < self.max_requests:
                self.requests.append(now)
                return True
            
            return False
    
    def get_reset_time(self) -> float:
        """Время до сброса окна."""
        if not self.requests:
            return 0.0
        
        return self.requests[0] + self.window_size - time.time()


class ApiCallTracker:
    """Трекер API вызовов с метриками."""
    
    def __init__(self, api_name: str):
        self.api_name = api_name
        self.total_calls = 0
        self.successful_calls = 0
        self.failed_calls = 0
        self.rate_limited_calls = 0
        self.last_call_time: Optional[float] = None
        self.consecutive_failures = 0
        self.avg_response_time = 0.0
        self.call_history: deque = deque(maxlen=1000)
        self._lock = asyncio.Lock()
    
    async def record_call(self, success: bool, response_time: float, rate_limited: bool = False):
        """Запись результата API вызова."""
        async with self._lock:
            now = time.time()
            self.total_calls += 1
            self.last_call_time = now
            
            if success:
                self.successful_calls += 1
                self.consecutive_failures = 0
            else:
                self.failed_calls += 1
                self.consecutive_failures += 1
            
            if rate_limited:
                self.rate_limited_calls += 1
            
            # Обновляем среднее время ответа
            self.avg_response_time = (
                (self.avg_response_time * (self.total_calls - 1) + response_time) / 
                self.total_calls
            )
            
            # Сохраняем в историю
            self.call_history.append({
                'timestamp': now,
                'success': success,
                'response_time': response_time,
                'rate_limited': rate_limited
            })
    
    def get_success_rate(self, window_minutes: int = 60) -> float:
        """Процент успешных вызовов за указанный период."""
        if not self.call_history:
            return 1.0
        
        cutoff = time.time() - (window_minutes * 60)
        recent_calls = [
            call for call in self.call_history 
            if call['timestamp'] > cutoff
        ]
        
        if not recent_calls:
            return 1.0
        
        successful = sum(1 for call in recent_calls if call['success'])
        return successful / len(recent_calls)
    
    def should_circuit_break(self, failure_threshold: int = 5, success_rate_threshold: float = 0.5) -> bool:
        """Проверка необходимости circuit breaker."""
        if self.consecutive_failures >= failure_threshold:
            return True
        
        recent_success_rate = self.get_success_rate(window_minutes=10)
        return recent_success_rate < success_rate_threshold


class ModularRateLimiter:
    """Ограничитель запросов для модульной архитектуры."""
    
    def __init__(self, config: RateLimitConfig):
        self.config = config
        self._buckets: Dict[str, TokenBucket] = {}
        self._sliding_windows: Dict[str, SlidingWindowLimiter] = {}
        self._api_trackers: Dict[str, ApiCallTracker] = {}
        self._attempt_history: Dict[str, deque] = defaultdict(lambda: deque(maxlen=100))
        self._backoff_times: Dict[str, float] = defaultdict(float)
        self._circuit_breakers: Dict[str, bool] = defaultdict(bool)
        self._lock = asyncio.Lock()
        
        # Коллбеки для различных событий
        self._on_rate_limit_callbacks: List[Callable] = []
        self._on_circuit_break_callbacks: List[Callable] = []
    
    def add_rate_limit_callback(self, callback: Callable):
        """Добавление коллбека при rate limit."""
        self._on_rate_limit_callbacks.append(callback)
    
    def add_circuit_break_callback(self, callback: Callable):
        """Добавление коллбека при circuit break."""
        self._on_circuit_break_callbacks.append(callback)
    
    async def acquire(self, key: str, tokens: int = 1) -> RateLimitResult:
        """Получение разрешения на выполнение запроса."""
        # Проверяем circuit breaker
        if await self._is_circuit_broken(key):
            return RateLimitResult(
                allowed=False,
                wait_time=self._get_circuit_break_time(key),
                retry_after=self._get_circuit_break_time(key)
            )
        
        # Проверяем backoff
        if await self._is_in_backoff(key):
            backoff_time = self._backoff_times.get(key, 0) - time.time()
            return RateLimitResult(
                allowed=False,
                wait_time=backoff_time,
                retry_after=backoff_time
            )
        
        # Выбираем стратегию ограничения
        if self.config.strategy == RateLimitStrategy.TOKEN_BUCKET:
            return await self._token_bucket_check(key, tokens)
        elif self.config.strategy == RateLimitStrategy.SLIDING_WINDOW:
            return await self._sliding_window_check(key)
        else:
            # Fallback на token bucket
            return await self._token_bucket_check(key, tokens)
    
    async def _token_bucket_check(self, key: str, tokens: int) -> RateLimitResult:
        """Проверка через Token Bucket."""
        bucket = await self._get_bucket(key)
        
        if await bucket.consume(tokens):
            await self._record_success(key)
            return RateLimitResult(
                allowed=True,
                remaining=bucket.available_tokens,
                reset_time=time.time() + (bucket.capacity / bucket.refill_rate)
            )
        else:
            await self._record_failure(key)
            wait_time = bucket.get_wait_time(tokens)
            
            # Вызываем коллбеки
            for callback in self._on_rate_limit_callbacks:
                try:
                    await callback(key, wait_time)
                except Exception as e:
                    logger.error(f"Rate limit callback error: {e}")
            
            return RateLimitResult(
                allowed=False,
                wait_time=wait_time,
                remaining=bucket.available_tokens,
                retry_after=wait_time
            )
    
    async def _sliding_window_check(self, key: str) -> RateLimitResult:
        """Проверка через Sliding Window."""
        window = await self._get_sliding_window(key)
        
        if await window.is_allowed():
            await self._record_success(key)
            return RateLimitResult(
                allowed=True,
                reset_time=time.time() + self.config.window_size
            )
        else:
            await self._record_failure(key)
            wait_time = window.get_reset_time()
            
            return RateLimitResult(
                allowed=False,
                wait_time=wait_time,
                retry_after=wait_time
            )
    
    async def acquire_with_wait(self, key: str, tokens: int = 1, max_wait: float = 10.0) -> RateLimitResult:
        """Получение разрешения с ожиданием."""
        result = await self.acquire(key, tokens)
        
        if not result.allowed and result.wait_time <= max_wait:
            logger.debug(f"Waiting {result.wait_time:.2f}s for rate limit: {key}")
            await asyncio.sleep(result.wait_time)
            
            # Повторная попытка после ожидания
            return await self.acquire(key, tokens)
        
        return result
    
    async def record_api_call(self, key: str, success: bool, response_time: float, rate_limited: bool = False):
        """Запись результата API вызова."""
        tracker = await self._get_api_tracker(key)
        await tracker.record_call(success, response_time, rate_limited)
        
        # Проверяем необходимость circuit breaker
        if tracker.should_circuit_break():
            await self._activate_circuit_breaker(key)
    
    async def _get_bucket(self, key: str) -> TokenBucket:
        """Получение bucket для ключа."""
        async with self._lock:
            if key not in self._buckets:
                self._buckets[key] = TokenBucket(
                    capacity=self.config.burst_size,
                    refill_rate=self.config.requests_per_second
                )
            return self._buckets[key]
    
    async def _get_sliding_window(self, key: str) -> SlidingWindowLimiter:
        """Получение sliding window для ключа."""
        async with self._lock:
            if key not in self._sliding_windows:
                max_requests = int(self.config.requests_per_second * self.config.window_size)
                self._sliding_windows[key] = SlidingWindowLimiter(
                    max_requests=max_requests,
                    window_size=self.config.window_size
                )
            return self._sliding_windows[key]
    
    async def _get_api_tracker(self, key: str) -> ApiCallTracker:
        """Получение API tracker для ключа."""
        async with self._lock:
            if key not in self._api_trackers:
                self._api_trackers[key] = ApiCallTracker(key)
            return self._api_trackers[key]
    
    async def _is_in_backoff(self, key: str) -> bool:
        """Проверка, находится ли ключ в состоянии backoff."""
        current_time = time.time()
        backoff_until = self._backoff_times.get(key, 0)
        return current_time < backoff_until
    
    async def _is_circuit_broken(self, key: str) -> bool:
        """Проверка состояния circuit breaker."""
        return self._circuit_breakers.get(key, False)
    
    def _get_circuit_break_time(self, key: str) -> float:
        """Время до восстановления circuit breaker."""
        # Circuit breaker открыт на время backoff
        return max(0, self._backoff_times.get(key, 0) - time.time())
    
    async def _activate_circuit_breaker(self, key: str):
        """Активация circuit breaker."""
        self._circuit_breakers[key] = True
        
        # Устанавливаем время восстановления
        recovery_time = time.time() + self.config.max_backoff
        self._backoff_times[key] = recovery_time
        
        logger.warning(f"Circuit breaker activated for {key}, recovery at {recovery_time}")
        
        # Вызываем коллбеки
        for callback in self._on_circuit_break_callbacks:
            try:
                await callback(key, recovery_time)
            except Exception as e:
                logger.error(f"Circuit break callback error: {e}")
        
        # Планируем восстановление
        asyncio.create_task(self._schedule_circuit_recovery(key, recovery_time))
    
    async def _schedule_circuit_recovery(self, key: str, recovery_time: float):
        """Планирование восстановления circuit breaker."""
        wait_time = recovery_time - time.time()
        if wait_time > 0:
            await asyncio.sleep(wait_time)
        
        # Половинчатое открытие circuit breaker
        self._circuit_breakers[key] = False
        logger.info(f"Circuit breaker recovered for {key}")
    
    async def _record_success(self, key: str):
        """Запись успешного запроса."""
        self._attempt_history[key].append((time.time(), True))
        
        # Сбрасываем backoff при успехе
        if key in self._backoff_times:
            del self._backoff_times[key]
        
        # Сбрасываем circuit breaker при успехе
        if key in self._circuit_breakers:
            del self._circuit_breakers[key]
    
    async def _record_failure(self, key: str):
        """Запись неудачного запроса."""
        current_time = time.time()
        self._attempt_history[key].append((current_time, False))
        
        # Вычисляем процент неудач за последнюю минуту
        recent_attempts = [
            (timestamp, success) for timestamp, success in self._attempt_history[key]
            if current_time - timestamp <= self.config.window_size
        ]
        
        if len(recent_attempts) >= self.config.cooldown_after_failures:
            failures = sum(1 for _, success in recent_attempts if not success)
            failure_rate = failures / len(recent_attempts)
            
            # Если много неудач, включаем backoff
            if failure_rate > 0.5:  # Более 50% неудач
                consecutive_failures = 0
                for _, success in reversed(recent_attempts):
                    if not success:
                        consecutive_failures += 1
                    else:
                        break
                
                backoff_duration = min(
                    self.config.backoff_factor ** consecutive_failures,
                    self.config.max_backoff
                )
                self._backoff_times[key] = current_time + backoff_duration
                
                logger.warning(
                    f"Rate limiter backoff activated for {key}: "
                    f"failure_rate={failure_rate:.2f}, backoff={backoff_duration:.2f}s"
                )
    
    async def get_stats(self) -> Dict[str, Any]:
        """Получение статистики ограничителя."""
        current_time = time.time()
        
        stats = {
            "total_buckets": len(self._buckets),
            "active_backoffs": sum(
                1 for backoff_time in self._backoff_times.values()
                if current_time < backoff_time
            ),
            "circuit_breakers": sum(1 for cb in self._circuit_breakers.values() if cb),
            "strategy": self.config.strategy.value,
            "buckets": {},
            "api_trackers": {}
        }
        
        # Статистика buckets
        for key, bucket in self._buckets.items():
            recent_attempts = [
                (timestamp, success) for timestamp, success in self._attempt_history[key]
                if current_time - timestamp <= 60  # Последняя минута
            ]
            
            success_count = sum(1 for _, success in recent_attempts if success)
            total_attempts = len(recent_attempts)
            
            stats["buckets"][key] = {
                "available_tokens": bucket.available_tokens,
                "capacity": bucket.capacity,
                "recent_attempts": total_attempts,
                "recent_successes": success_count,
                "success_rate": success_count / max(1, total_attempts),
                "in_backoff": await self._is_in_backoff(key),
                "circuit_broken": await self._is_circuit_broken(key)
            }
        
        # Статистика API trackers
        for key, tracker in self._api_trackers.items():
            stats["api_trackers"][key] = {
                "total_calls": tracker.total_calls,
                "successful_calls": tracker.successful_calls,
                "failed_calls": tracker.failed_calls,
                "rate_limited_calls": tracker.rate_limited_calls,
                "consecutive_failures": tracker.consecutive_failures,
                "avg_response_time": tracker.avg_response_time,
                "success_rate_1h": tracker.get_success_rate(60),
                "success_rate_10m": tracker.get_success_rate(10)
            }
        
        return stats
    
    async def reset_limits(self, key: str):
        """Сброс лимитов для ключа."""
        async with self._lock:
            if key in self._buckets:
                self._buckets[key].tokens = self._buckets[key].capacity
            
            if key in self._backoff_times:
                del self._backoff_times[key]
            
            if key in self._circuit_breakers:
                del self._circuit_breakers[key]
            
            if key in self._attempt_history:
                self._attempt_history[key].clear()
        
        logger.info(f"Reset rate limits for {key}")
    
    async def cleanup_expired(self):
        """Очистка истекших данных."""
        current_time = time.time()
        expired_keys = []
        
        # Находим истекшие backoffs
        for key, backoff_time in self._backoff_times.items():
            if current_time > backoff_time:
                expired_keys.append(key)
        
        # Удаляем истекшие
        for key in expired_keys:
            del self._backoff_times[key]
            if key in self._circuit_breakers:
                del self._circuit_breakers[key]
        
        logger.debug(f"Cleaned up {len(expired_keys)} expired rate limit entries")
        return len(expired_keys)


# Предустановленные конфигурации для разных API
API_CONFIGS = {
    "etherscan_free": RateLimitConfig(
        requests_per_second=0.2,  # 1 request per 5 seconds
        burst_size=1,
        window_size=300,  # 5 minutes
        backoff_factor=2.0,
        max_backoff=3600,  # 1 hour
        retry_attempts=3
    ),
    
    "etherscan_paid": RateLimitConfig(
        requests_per_second=5.0,
        burst_size=10,
        window_size=60,
        backoff_factor=1.5,
        max_backoff=300,
        retry_attempts=3
    ),
    
    "coingecko_free": RateLimitConfig(
        requests_per_second=0.5,  # 30 requests per minute
        burst_size=5,
        window_size=60,
        backoff_factor=2.0,
        max_backoff=900,  # 15 minutes
        retry_attempts=2
    ),
    
    "telegram_bot": RateLimitConfig(
        requests_per_second=30.0,  # Telegram limit
        burst_size=30,
        window_size=1,
        backoff_factor=1.2,
        max_backoff=60,
        retry_attempts=1
    ),
    
    "user_commands": RateLimitConfig(
        requests_per_second=0.1,  # 6 commands per minute
        burst_size=3,
        window_size=60,
        backoff_factor=1.5,
        max_backoff=300,
        retry_attempts=0  # No retry for user limits
    )
}


def get_rate_limiter(api_name: str) -> ModularRateLimiter:
    """Получение настроенного rate limiter для API."""
    config = API_CONFIGS.get(api_name, RateLimitConfig())
    return ModularRateLimiter(config)