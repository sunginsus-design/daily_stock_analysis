# -*- coding: utf-8 -*-
"""
AI_CHAIN_WATCHLIST
==================

日本 AI / 半导体成长股研究系统用观察池。
建议保存路径：src/core/ai_chain_watchlist.py

用途：
1. 统一维护全球 AI 核心资产、日本半导体产业链、宏观/指数观察对象
2. 后续可供 market_analyzer.py、analyzer.py 或新增 ai_chain_analyzer.py 调用
3. 避免把研究对象硬编码到 prompt 或报告模板中
"""

from __future__ import annotations

from typing import Dict, List


AI_CHAIN_WATCHLIST: Dict[str, Dict[str, str]] = {
    "global_ai_core": {
        "NVDA": "NVIDIA",
        "TSM": "TSMC ADR",
        "ASML": "ASML Holding",
        "AMD": "Advanced Micro Devices",
        "AVGO": "Broadcom",
        "MU": "Micron Technology",
        "ARM": "Arm Holdings",
        "MSFT": "Microsoft",
        "GOOGL": "Alphabet",
        "AMZN": "Amazon",
        "META": "Meta Platforms",
    },
    "global_semiconductor_indices_macro": {
        "^SOX": "费城半导体指数",
        "^IXIC": "纳斯达克综合指数",
        "^GSPC": "S&P500",
        "^TNX": "美国10年期国债收益率",
        "JPY=X": "美元/日元",
    },
    "japan_market_indices": {
        "^N225": "日经225",
        "^TOPX": "TOPIX",
        "^JPXNK400": "JPX日经400",
    },
    "japan_semiconductor_equipment": {
        "8035.T": "东京电子",
        "6857.T": "Advantest",
        "6920.T": "Lasertec",
        "6315.T": "TOWA",
        "6146.T": "Disco",
        "7735.T": "SCREEN Holdings",
        "6525.T": "KOKUSAI ELECTRIC",
        "6266.T": "Takano",
    },
    "japan_semiconductor_materials_wafers": {
        "4063.T": "信越化学",
        "3436.T": "SUMCO",
        "4186.T": "东京应化工业",
        "4004.T": "Resonac Holdings",
        "4369.T": "Tri Chemical Laboratories",
        "4971.T": "MEC",
        "4975.T": "JCU",
    },
    "japan_electronics_components_power_ai_server": {
        "6723.T": "瑞萨电子",
        "6594.T": "尼得科",
        "6590.T": "芝浦电子",
        "6506.T": "安川电机",
        "6762.T": "TDK",
        "6981.T": "村田制作所",
        "6976.T": "太阳诱电",
        "6645.T": "欧姆龙",
    },
    "japan_pcb_substrate_related": {
        "4062.T": "Ibiden",
        "6967.T": "新光电气工业",
        "6988.T": "日东电工",
        "6807.T": "日本航空电子工业",
        "6755.T": "富士通ゼネラル",
    },
}


AI_CHAIN_KEYWORDS: Dict[str, List[str]] = {
    "global_ai_cycle": [
        "NVIDIA",
        "AI capex",
        "AI server",
        "HBM",
        "CoWoS",
        "TSMC capex",
        "cloud capex",
        "semiconductor cycle",
    ],
    "japan_semiconductor": [
        "日本 半導体",
        "半導体製造装置",
        "半導体材料",
        "シリコンウェーハ",
        "AI 関連株",
        "日経平均 半導体",
    ],
    "macro_risk": [
        "USDJPY",
        "ドル円",
        "米国10年債利回り",
        "BOJ",
        "日銀",
        "NASDAQ",
        "SOX semiconductor index",
    ],
}


def get_all_watchlist_symbols() -> List[str]:
    """Return all unique symbols in AI_CHAIN_WATCHLIST while preserving order."""
    symbols: List[str] = []
    seen = set()
    for group in AI_CHAIN_WATCHLIST.values():
        for symbol in group.keys():
            if symbol not in seen:
                symbols.append(symbol)
                seen.add(symbol)
    return symbols


def get_watchlist_group(group_name: str) -> Dict[str, str]:
    """Return one watchlist group. Unknown group returns an empty dict."""
    return AI_CHAIN_WATCHLIST.get(group_name, {})
