# -*- coding: utf-8 -*-
"""线程安全限流器：并发抓取下，多个 worker 共享一个限流器，控制总 QPS。

采用「预约时隙」策略：锁内只更新下一个可请求时刻（预约），锁外 sleep，
避免 sleep 阻塞其他线程预约，也不会让并发请求挤在同一瞬间发出。即使
min_interval 配置较大，并发也能稳定把总请求速率压到约 1/interval。
"""
import random
import threading
import time


class RateLimiter:
    def __init__(self, min_interval=1.0, max_interval=3.0):
        self.min_interval = min_interval
        self.max_interval = max_interval
        self._lock = threading.Lock()
        self._last_ts = 0.0

    def wait(self):
        """预约一个请求时隙，必要时 sleep 到该时隙。"""
        if self.max_interval <= 0:
            return
        wait = random.uniform(self.min_interval, self.max_interval)
        with self._lock:
            now = time.time()
            next_ts = max(self._last_ts + wait, now)
            self._last_ts = next_ts
            sleep_for = next_ts - now
        if sleep_for > 0:
            time.sleep(sleep_for)
