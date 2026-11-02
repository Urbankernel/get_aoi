# -*- coding: utf-8 -*-
"""HTTP 请求工具：随机 UA、代理、重试、限流降频。

说明：两类接口防护重点不同——
  * 官方检索接口（place/text、place/v2/search）：防"配额/QPS"，控制频率即可；
  * 网页隐藏接口（getPoiInfo、qt=ext）：防"反爬"，需 UA/Cookie/代理 + 降频。
二者通过 HttpClient 的参数分别配置，不混用。
"""
import random
import time

import requests

from .logger import get_logger

logger = get_logger()


class AntiBotError(RuntimeError):
    """目标站点返回人机验证/风控页，继续重试无意义。"""


USER_AGENTS = [
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/123.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:125.0) "
    "Gecko/20100101 Firefox/125.0",
]


class HttpClient:
    def __init__(self, min_interval=1.0, max_interval=3.0, retries=3,
                 timeout=15, proxies=None, cookie=None, random_ua=True,
                 user_agent=None, limiter=None):
        self.min_interval = min_interval
        self.max_interval = max_interval
        self.retries = retries
        self.timeout = timeout
        self.proxies = proxies or {}
        self.cookie = cookie
        self.random_ua = random_ua
        self.user_agent = user_agent
        self.limiter = limiter  # 共享限流器（并发时由各 HttpClient 共用）
        self.session = requests.Session()
        self._last_ts = 0.0

    def _throttle(self):
        if self.limiter is not None:
            self.limiter.wait()
            return
        if self.max_interval <= 0:
            return
        wait = random.uniform(self.min_interval, self.max_interval)
        elapsed = time.time() - self._last_ts
        if elapsed < wait:
            time.sleep(wait - elapsed)

    def _headers(self):
        headers = {
            "Accept": "application/json, text/plain, */*",
            "Accept-Language": "zh-CN,zh;q=0.9",
        }
        if self.user_agent:
            headers["User-Agent"] = self.user_agent
        else:
            headers["User-Agent"] = (random.choice(USER_AGENTS)
                                     if self.random_ua else USER_AGENTS[0])
        if self.cookie:
            headers["Cookie"] = self.cookie
        return headers

    @staticmethod
    def _check_antibot(resp, data=None):
        """识别高德/百度的人机验证响应，避免把 HTML 当 JSON 反复重试。"""
        text = resp.text or ""
        lowered = text[:20000].lower()
        ret = data.get("ret", []) if isinstance(data, dict) else []
        ret_text = " ".join(str(v) for v in ret) if isinstance(ret, list) else str(ret)
        data_url = str((data.get("data") or {}).get("url", "")) \
            if isinstance(data, dict) and isinstance(data.get("data"), dict) else ""
        if ("punish" in lowered or "awsc/captcha" in lowered
                or "FAIL_SYS_USER_VALIDATE" in ret_text
                or "RGV587_ERROR" in ret_text or "punish" in data_url):
            raise AntiBotError(
                "目标接口触发人机验证/访问风控。请先在浏览器正常打开对应地点并完成验证，"
                "再将同一成功 GET 请求中的 Cookie、User-Agent 写入 .env；"
                "高德还可按 README 配置 Bx-Ua 等动态请求头。上述值必须来自同一浏览器会话。"
                "若仍失败，请稍后重试、降低频率或更换合规网络/官方高阶服务。")

    def get_json(self, url, params=None, referer=None, extra_headers=None):
        """GET 并解析 JSON，带限流与重试。失败返回 None，风控直接抛错。

        extra_headers 仅用于当前请求，供网页边界接口复用同一次浏览器会话的
        动态请求头；不会写入 Session，也不会打印其敏感值。
        """
        headers = self._headers()
        if referer:
            headers["Referer"] = referer
        if extra_headers:
            headers.update(extra_headers)
        last_error = None
        for attempt in range(1, self.retries + 1):
            self._throttle()
            try:
                resp = self.session.get(
                    url, params=params, headers=headers,
                    proxies=self.proxies or None, timeout=self.timeout)
                self._last_ts = time.time()
                resp.raise_for_status()
                content_type = (resp.headers.get("Content-Type") or "").lower()
                if "html" in content_type or resp.text.lstrip().lower().startswith(("<!doctype html", "<html")):
                    self._check_antibot(resp)
                    raise ValueError("接口返回 HTML 而非 JSON，可能已改版或需要登录")
                data = resp.json()
                self._check_antibot(resp, data)
                return data
            except AntiBotError:
                raise
            except Exception as exc:  # 网络/JSON/HTTP 错误统一重试
                last_error = exc
                logger.debug("请求失败(%s/%s)：%s %s", attempt, self.retries,
                             url, exc)
                self._last_ts = time.time()
                if attempt < self.retries:
                    time.sleep(min(2 * attempt, 5))
        logger.warning("多次重试仍失败：%s；最后错误：%s", url, last_error)
        return None
