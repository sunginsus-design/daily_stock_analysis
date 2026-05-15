# -*- coding: utf-8 -*-
"""
===================================
YfinanceFetcher - 兜底数据源 (Priority 4)
===================================

数据来源：Yahoo Finance（通过 yfinance 库）
特点：国际数据源、可能有延迟或缺失
定位：当其他数据源失败时的国际市场兜底数据源

本版本重点补充：
1. region="jp" 时获取日本市场 + 全球 AI/半导体链基准指标
2. 保留日股 4 位代码自动转换为 .T 的逻辑
3. 保留 A 股 / 港股 / 美股 / 日股基础历史行情兼容逻辑
"""

import logging
import os
from typing import Optional, List, Dict, Any

import pandas as pd
from tenacity import (
    retry,
    stop_after_attempt,
    wait_exponential,
    retry_if_exception_type,
    before_sleep_log,
)

from .base import BaseFetcher, DataFetchError, STANDARD_COLUMNS, is_bse_code
from .realtime_types import UnifiedRealtimeQuote, RealtimeSource
from .us_index_mapping import get_us_index_yf_symbol, is_us_stock_code

try:
    from src.data.stock_mapping import STOCK_NAME_MAP, is_meaningful_stock_name
except (ImportError, ModuleNotFoundError):
    STOCK_NAME_MAP = {}

    def is_meaningful_stock_name(name: str | None, stock_code: str) -> bool:
        if not name:
            return False
        n = str(name).strip()
        return bool(n and n.upper() != str(stock_code).strip().upper())


logger = logging.getLogger(__name__)


class YfinanceFetcher(BaseFetcher):
    """Yahoo Finance 数据源实现。"""

    name = "YfinanceFetcher"
    priority = int(os.getenv("YFINANCE_PRIORITY", "4"))

    def __init__(self):
        pass

    def _convert_stock_code(self, stock_code: str) -> str:
        """
        转换股票代码为 Yahoo Finance 格式。

        - A股沪市：600519 -> 600519.SS
        - A股深市：000001 -> 000001.SZ
        - 港股：HK00700 / 700.HK -> 0700.HK
        - 日股：4063 -> 4063.T
        - 美股：AAPL -> AAPL
        - 美股指数：SPX -> ^GSPC 等
        """
        code = (stock_code or "").strip().upper()
        if not code:
            return code

        yf_symbol, _ = get_us_index_yf_symbol(code)
        if yf_symbol:
            logger.debug("识别为美股指数: %s -> %s", code, yf_symbol)
            return yf_symbol

        if is_us_stock_code(code):
            logger.debug("识别为美股代码: %s", code)
            return code

        if code.endswith(".T"):
            logger.debug("识别为日股代码(已带后缀): %s", code)
            return code

        if code.isdigit() and len(code) == 4:
            logger.debug("识别为日股代码: %s -> %s.T", stock_code, code)
            return f"{code}.T"

        if code.endswith(".HK"):
            base = code[:-3].lstrip("0") or "0"
            return f"{base.zfill(4)}.HK"

        if code.startswith("HK"):
            hk_code = code[2:].lstrip("0") or "0"
            return f"{hk_code.zfill(4)}.HK"

        if any(suffix in code for suffix in (".SS", ".SZ", ".BJ")):
            return code

        code = code.replace(".SH", "")

        if len(code) == 6 and code.isdigit():
            if code.startswith(("51", "52", "56", "58")):
                return f"{code}.SS"
            if code.startswith(("15", "16", "18")):
                return f"{code}.SZ"
            if is_bse_code(code):
                return f"{code}.BJ"
            if code.startswith(("600", "601", "603", "605", "688")):
                return f"{code}.SS"
            if code.startswith(("000", "001", "002", "003", "300", "301")):
                return f"{code}.SZ"

        logger.warning("无法确定股票 %s 的市场，默认使用深市", code)
        return f"{code}.SZ"

    @retry(
        stop=stop_after_attempt(3),
        wait=wait_exponential(multiplier=1, min=2, max=30),
        retry=retry_if_exception_type((ConnectionError, TimeoutError)),
        before_sleep=before_sleep_log(logger, logging.WARNING),
    )
    def _fetch_raw_data(self, stock_code: str, start_date: str, end_date: str) -> pd.DataFrame:
        """从 Yahoo Finance 获取原始历史行情。"""
        import yfinance as yf

        yf_code = self._convert_stock_code(stock_code)
        logger.debug("调用 yfinance.download(%s, %s, %s)", yf_code, start_date, end_date)

        try:
            df = yf.download(
                tickers=yf_code,
                start=start_date,
                end=end_date,
                progress=False,
                auto_adjust=True,
                multi_level_index=True,
            )

            if isinstance(df.columns, pd.MultiIndex) and len(df.columns) > 1:
                ticker_level = df.columns.get_level_values(1)
                mask = ticker_level == yf_code
                if mask.any():
                    df = df.loc[:, mask].copy()

            if df.empty:
                raise DataFetchError(f"Yahoo Finance 未查询到 {stock_code} 的数据")

            return df
        except Exception as exc:
            if isinstance(exc, DataFetchError):
                raise
            raise DataFetchError(f"Yahoo Finance 获取数据失败: {exc}") from exc

    def _normalize_data(self, df: pd.DataFrame, stock_code: str) -> pd.DataFrame:
        """标准化 Yahoo Finance 日线数据。"""
        df = df.copy()

        if isinstance(df.columns, pd.MultiIndex):
            df.columns = df.columns.get_level_values(0)

        df = df.reset_index()
        column_mapping = {
            "Date": "date",
            "Datetime": "date",
            "Open": "open",
            "High": "high",
            "Low": "low",
            "Close": "close",
            "Volume": "volume",
        }
        df = df.rename(columns=column_mapping)

        if "close" in df.columns:
            df["pct_chg"] = df["close"].pct_change() * 100
            df["pct_chg"] = df["pct_chg"].fillna(0).round(2)

        if "volume" in df.columns and "close" in df.columns:
            df["amount"] = df["volume"] * df["close"]
        else:
            df["amount"] = 0

        df["code"] = stock_code
        keep_cols = ["code"] + STANDARD_COLUMNS
        existing_cols = [col for col in keep_cols if col in df.columns]
        return df[existing_cols]

    def _fetch_yf_ticker_data(
        self,
        yf,
        yf_code: str,
        name: str,
        return_code: str,
    ) -> Optional[Dict[str, Any]]:
        """通过 yfinance 拉取单个指数、汇率、利率或股票的近两日行情。"""
        ticker = yf.Ticker(yf_code)
        hist = ticker.history(period="5d")
        if hist.empty:
            return None

        today_row = hist.iloc[-1]
        prev_row = hist.iloc[-2] if len(hist) > 1 else today_row

        price = float(today_row["Close"])
        prev_close = float(prev_row["Close"])
        change = price - prev_close
        change_pct = (change / prev_close) * 100 if prev_close else 0.0
        high = float(today_row["High"])
        low = float(today_row["Low"])
        amplitude = ((high - low) / prev_close * 100) if prev_close else 0.0

        volume_value = today_row.get("Volume", 0)
        try:
            volume = float(volume_value) if pd.notna(volume_value) else 0.0
        except Exception:
            volume = 0.0

        return {
            "code": return_code,
            "name": name,
            "current": price,
            "change": change,
            "change_pct": change_pct,
            "open": float(today_row["Open"]),
            "high": high,
            "low": low,
            "prev_close": prev_close,
            "volume": volume,
            "amount": 0.0,
            "amplitude": amplitude,
        }

    def get_main_indices(self, region: str = "cn") -> Optional[List[Dict[str, Any]]]:
        """
        获取主要指数行情。

        region="jp" 时返回日本市场 + 全球 AI/半导体链基准指标，
        用于 AI产业链市场观察，避免继续回落到 A股指数。
        """
        import yfinance as yf

        region = (region or "cn").strip().lower()

        if region == "jp":
            return self._get_jp_ai_main_indices(yf)
        if region == "us":
            return self._get_us_main_indices(yf)
        if region == "hk":
            return self._get_hk_main_indices(yf)

        yf_mapping = {
            "sh000001": ("000001.SS", "上证指数"),
            "sz399001": ("399001.SZ", "深证成指"),
            "sz399006": ("399006.SZ", "创业板指"),
            "sh000688": ("000688.SS", "科创50"),
            "sh000016": ("000016.SS", "上证50"),
            "sh000300": ("000300.SS", "沪深300"),
        }
        return self._fetch_index_mapping(yf, yf_mapping, "A 股指数")

    def _fetch_index_mapping(
        self,
        yf,
        mapping: Dict[str, tuple[str, str]],
        label: str,
    ) -> Optional[List[Dict[str, Any]]]:
        results: List[Dict[str, Any]] = []
        try:
            for code, (yf_symbol, name) in mapping.items():
                try:
                    item = self._fetch_yf_ticker_data(yf, yf_symbol, name, code)
                    if item:
                        results.append(item)
                        logger.debug("[Yfinance] 获取%s %s 成功", label, name)
                except Exception as exc:
                    logger.warning("[Yfinance] 获取%s %s 失败: %s", label, name, exc)

            if results:
                logger.info("[Yfinance] 成功获取 %s 个%s行情", len(results), label)
                return results
        except Exception as exc:
            logger.error("[Yfinance] 获取%s行情失败: %s", label, exc)

        return None

    def _get_jp_ai_main_indices(self, yf) -> Optional[List[Dict[str, Any]]]:
        """
        获取日股与全球 AI/半导体链市场基准指标。

        这些数据会进入 MarketAnalyzer.get_market_overview() 的 overview.indices，
        供后续报告分析日本市场结构、全球 AI 风险偏好、半导体周期、汇率与利率环境。
        """
        jp_ai_indices = {
            "N225": ("^N225", "日经225"),
            "TOPIX": ("^TOPX", "TOPIX"),
            "JPX400": ("^JPXNK400", "JPX日经400"),
            "SOX": ("^SOX", "费城半导体指数"),
            "NASDAQ": ("^IXIC", "纳斯达克综合指数"),
            "SP500": ("^GSPC", "S&P500"),
            "USDJPY": ("JPY=X", "美元/日元"),
            "US10Y": ("^TNX", "美国10年期国债收益率"),
        }
        return self._fetch_index_mapping(yf, jp_ai_indices, "日股/AI市场指标")

    def _get_us_main_indices(self, yf) -> Optional[List[Dict[str, Any]]]:
        """获取美股主要指数行情。"""
        us_indices: Dict[str, tuple[str, str]] = {}
        for code in ["SPX", "IXIC", "DJI", "VIX"]:
            yf_symbol, name = get_us_index_yf_symbol(code)
            if yf_symbol:
                us_indices[code] = (yf_symbol, name)
        return self._fetch_index_mapping(yf, us_indices, "美股指数")

    def _get_hk_main_indices(self, yf) -> Optional[List[Dict[str, Any]]]:
        """获取港股主要指数行情。"""
        hk_indices = {
            "HSI": ("^HSI", "恒生指数"),
            "HSTECH": ("HSTECH.HK", "恒生科技指数"),
            "HSCEI": ("^HSCE", "国企指数"),
        }
        return self._fetch_index_mapping(yf, hk_indices, "港股指数")

    def _is_us_stock(self, stock_code: str) -> bool:
        return is_us_stock_code((stock_code or "").strip().upper())

    def get_realtime_quote(self, stock_code: str) -> Optional[UnifiedRealtimeQuote]:
        """
        获取美股、美股指数、日股的实时/近实时行情。
        Yahoo Finance 数据可能存在延迟，适合作为兜底数据源。
        """
        import yfinance as yf

        normalized_code = (stock_code or "").strip().upper()
        if not normalized_code:
            return None

        yf_symbol, index_name = get_us_index_yf_symbol(normalized_code)
        if yf_symbol:
            symbol = yf_symbol
            display_code = normalized_code
            display_name = index_name or normalized_code
        elif normalized_code.endswith(".T") or (normalized_code.isdigit() and len(normalized_code) == 4):
            symbol = self._convert_stock_code(normalized_code)
            display_code = symbol
            display_name = STOCK_NAME_MAP.get(symbol, "")
        elif self._is_us_stock(normalized_code):
            symbol = normalized_code
            display_code = symbol
            display_name = STOCK_NAME_MAP.get(symbol, "")
        else:
            logger.debug("[Yfinance] 不支持的股票代码: %s", stock_code)
            return None

        try:
            ticker = yf.Ticker(symbol)
            hist = ticker.history(period="5d")
            if hist.empty:
                logger.warning("[Yfinance] 无法获取 %s 的行情数据", symbol)
                return None

            today = hist.iloc[-1]
            prev = hist.iloc[-2] if len(hist) > 1 else today
            price = float(today["Close"])
            prev_close = float(prev["Close"])
            open_price = float(today["Open"])
            high = float(today["High"])
            low = float(today["Low"])
            volume = int(today.get("Volume", 0) or 0)

            change_amount = price - prev_close if prev_close else None
            change_pct = (change_amount / prev_close) * 100 if change_amount is not None and prev_close else None
            amplitude = ((high - low) / prev_close) * 100 if prev_close else None

            try:
                info = ticker.info or {}
                info_name = info.get("shortName", "") or info.get("longName", "") or ""
                if is_meaningful_stock_name(info_name, display_code):
                    display_name = info_name
                market_cap = info.get("marketCap")
            except Exception:
                market_cap = None

            return UnifiedRealtimeQuote(
                code=display_code,
                name=display_name,
                source=RealtimeSource.FALLBACK,
                price=price,
                change_pct=round(change_pct, 2) if change_pct is not None else None,
                change_amount=round(change_amount, 4) if change_amount is not None else None,
                volume=volume,
                amount=None,
                volume_ratio=None,
                turnover_rate=None,
                amplitude=round(amplitude, 2) if amplitude is not None else None,
                open_price=open_price,
                high=high,
                low=low,
                pre_close=prev_close,
                pe_ratio=None,
                pb_ratio=None,
                total_mv=market_cap,
                circ_mv=None,
            )
        except Exception as exc:
            logger.warning("[Yfinance] 获取 %s 实时行情失败: %s", stock_code, exc)
            return None


if __name__ == "__main__":
    logging.basicConfig(level=logging.DEBUG)

    fetcher = YfinanceFetcher()
    try:
        df = fetcher.get_daily_data("4063")
        print(f"获取成功，共 {len(df)} 条数据")
        print(df.tail())
    except Exception as e:
        print(f"获取失败: {e}")
