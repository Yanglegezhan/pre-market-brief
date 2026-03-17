"""
盘前数据采集器
采集美股行情、A50期货、大宗商品、汇率、财经新闻等数据

重要原则：
- 只返回真实数据
- 采集失败就报告失败，绝不使用模拟数据
- 新闻筛选只保留昨日15:00之后的新闻
"""
import re
import json
from datetime import datetime, timedelta
from typing import List, Optional, Dict, Tuple
from dataclasses import dataclass
from loguru import logger

import requests

try:
    import akshare as ak
    import pandas as pd
    AKSHARE_AVAILABLE = True
except ImportError:
    AKSHARE_AVAILABLE = False


# 盘后新闻时间范围配置
AFTER_HOURS_START = "15:00"  # 收盘时间（A股收盘15:00，开始统计盘后新闻）
MARKET_OPEN = "08:30"  # 盘前时间（A股开盘前30分钟，结束统计）


def get_news_time_range() -> Tuple[datetime, datetime]:
    """
    获取盘后新闻的时间范围
    返回: (开始时间, 结束时间)
    默认范围：昨天15:00 到 今天08:30
    """
    now = datetime.now()
    today = now.date()
    yesterday = today - timedelta(days=1)

    # 如果现在是8:30之前，说明是盘前时间，范围是前天15:00到昨天8:30
    if now.hour < 8 or (now.hour == 8 and now.minute < 30):
        start_date = yesterday - timedelta(days=1)
        end_date = yesterday
    else:
        # 正常情况：昨天15:00到今天08:30
        start_date = yesterday
        end_date = today

    start_time = datetime.combine(start_date, datetime.strptime(AFTER_HOURS_START, "%H:%M").time())
    end_time = datetime.combine(end_date, datetime.strptime(MARKET_OPEN, "%H:%M").time())

    return start_time, end_time


def parse_news_time(time_str: str) -> Optional[datetime]:
    """解析新闻时间字符串为datetime对象"""
    if not time_str or time_str == "":
        return None

    # 尝试多种时间格式
    formats = [
        "%Y-%m-%d %H:%M:%S",
        "%Y-%m-%d %H:%M",
        "%m-%d %H:%M",
        "%H:%M:%S",
        "%H:%M",
    ]

    for fmt in formats:
        try:
            dt = datetime.strptime(time_str, fmt)
            # 如果没有年份，假设是今年
            if dt.year == 1900:
                dt = dt.replace(year=datetime.now().year)
            return dt
        except ValueError:
            continue

    # 特殊格式：Unix时间戳
    try:
        timestamp = int(time_str)
        if timestamp > 1000000000:  # 判断是否为秒级时间戳
            return datetime.fromtimestamp(timestamp)
    except ValueError:
        pass

    return None


def is_after_hours_news(time_str: str) -> bool:
    """判断新闻是否在盘后时间范围（昨日15:00 - 今日09:30）"""
    news_time = parse_news_time(time_str)
    if not news_time:
        # 如果时间解析失败，默认保留（可能是最新新闻）
        return True

    start_time, end_time = get_news_time_range()

    # 检查是否在范围内
    return start_time <= news_time <= end_time


@dataclass
class MarketData:
    """市场数据结构"""
    symbol: str
    name: str
    price: float
    change: float
    change_pct: float
    timestamp: str
    source: str


@dataclass
class TopStock:
    """涨跌幅股票"""
    symbol: str
    name: str
    price: float
    change_pct: float
    volume: str
    sector: str
    a_share_mapping: str
    catalyst: str  # 催化消息


@dataclass
class Commodity:
    """大宗商品"""
    name: str
    price: float
    change_pct: float
    unit: str
    a_share_impact: str  # 对A股的影响


@dataclass
class ExchangeRate:
    """汇率"""
    name: str
    rate: float
    change_pct: float


@dataclass
class NewsItem:
    """新闻条目"""
    title: str
    source: str
    time: str
    relevance: str  # 相关性判断
    related_stocks: List[str]  # 相关股票
    content: str = ""  # 新闻正文（新增）

    # LLM 评估结果（用于新闻筛选）
    catalyst_score: float = 0.0      # 催化指数
    ferment_potential: str = ""      # 发酵潜力
    worth_betting: bool = False      # 是否值得博弈
    analysis_reason: str = ""        # 分析原因
    risk_warning: str = ""           # 风险提示

    # 权重评分（用于排序）
    weight_score: float = 0.0        # 权重总分
    source_weight: float = 0.0       # 来源权重
    time_weight: float = 0.0         # 时效性权重
    relevance_weight: float = 0.0    # 相关性权重
    hot_weight: float = 0.0          # 热度权重

    def calculate_weight(self, market_open_time: datetime = None):
        """计算新闻权重分数"""
        # 1. 来源权重 (0-30分)
        source_scores = {
            "财联社": 30,      #  fastest, 专业财经
            "同花顺": 28,      #  实时性强
            "华尔街见闻": 25,  #  国际视野
            "新浪财经": 22,    #  老牌财经
            "东方财富": 20,    #  散户关注
            "腾讯财经": 15,
            "网易财经": 15,
            "百度财经": 12,
            "CCTV": 25,        #  权威
            "证券时报": 24,    #  官方
            "第一财经": 23,    #  专业
        }
        self.source_weight = source_scores.get(self.source, 10)

        # 2. 时效性权重 (0-25分) - 越新越重要
        try:
            if self.time:
                # 尝试解析时间
                news_time = self._parse_time(self.time)
                if news_time:
                    now = datetime.now()
                    hours_diff = (now - news_time).total_seconds() / 3600
                    # 1小时内25分，2小时20分，4小时15分，8小时10分，12小时5分
                    if hours_diff <= 1:
                        self.time_weight = 25
                    elif hours_diff <= 2:
                        self.time_weight = 20
                    elif hours_diff <= 4:
                        self.time_weight = 15
                    elif hours_diff <= 8:
                        self.time_weight = 10
                    elif hours_diff <= 12:
                        self.time_weight = 5
                    else:
                        self.time_weight = 2
                else:
                    self.time_weight = 10  # 默认中等
            else:
                self.time_weight = 10
        except:
            self.time_weight = 10

        # 3. 相关性权重 (0-25分)
        relevance_scores = {"高": 25, "中": 15, "低": 5}
        self.relevance_weight = relevance_scores.get(self.relevance, 10)

        # 4. 热度权重 (0-20分) - 关键词匹配
        hot_keywords = {
            "涨停": 20, "跌停": 20, "涨停潮": 20, "跌停潮": 20,
            "暴涨": 18, "暴跌": 18, "大涨": 15, "大跌": 15,
            "利好": 12, "利空": 12, "政策": 15, "新政": 15,
            "涨停梯队": 18, "连板": 16, "龙头": 14, "妖股": 14,
            "板块": 10, "题材": 10, "概念": 10,
            "央行": 14, "证监会": 14, "国务院": 16, "发改委": 14,
            "IPO": 12, "上市": 10, "并购": 12, "重组": 12,
            "芯片": 13, "半导体": 13, "AI": 12, "人工智能": 12,
            "新能源": 11, "光伏": 11, "锂电": 11, "固态电池": 14,
            "黄金": 10, "原油": 10, "油价": 10,
            "美股": 8, "纳指": 8, "道指": 8, "美联储": 10,
        }
        self.hot_weight = 0
        for keyword, score in hot_keywords.items():
            if keyword in self.title:
                self.hot_weight = max(self.hot_weight, score)

        # 5. 如果有LLM催化指数，加入权重 (0-10分额外加分)
        llm_bonus = min(self.catalyst_score, 10) if self.catalyst_score > 0 else 0

        # 计算总分
        self.weight_score = (
            self.source_weight * 0.30 +      # 来源权重30%
            self.time_weight * 0.25 +         # 时效性25%
            self.relevance_weight * 0.25 +    # 相关性25%
            self.hot_weight * 0.20 +          # 热度20%
            llm_bonus                         # LLM额外加分
        )

        return self.weight_score

    def _parse_time(self, time_str: str) -> datetime:
        """解析时间字符串"""
        try:
            # 尝试多种格式
            formats = [
                "%Y-%m-%d %H:%M:%S",
                "%Y-%m-%d %H:%M",
                "%m-%d %H:%M:%S",
                "%m-%d %H:%M",
                "%H:%M:%S",
                "%H:%M",
            ]
            for fmt in formats:
                try:
                    dt = datetime.strptime(time_str, fmt)
                    # 如果只有时间，假设是今天
                    if dt.year == 1900:
                        dt = dt.replace(year=datetime.now().year)
                        # 如果小时大于当前小时，可能是昨天
                        if dt.hour > datetime.now().hour:
                            dt = dt - timedelta(days=1)
                    return dt
                except:
                    continue
        except:
            pass
        return None

    def __lt__(self, other):
        """用于排序：权重高的在前"""
        return self.weight_score > other.weight_score

    def __repr__(self):
        return f"NewsItem(title='{self.title[:30]}...', source='{self.source}', weight={self.weight_score:.1f})"


# 美股代码 -> 中文名称映射
US_STOCK_NAMES = {
    "AAPL": "苹果", "MSFT": "微软", "GOOGL": "谷歌", "AMZN": "亚马逊",
    "NVDA": "英伟达", "TSLA": "特斯拉", "META": "Meta", "AMD": "AMD",
    "INTC": "英特尔", "NFLX": "奈飞", "DIS": "迪士尼", "BA": "波音",
    "NKE": "耐克", "WMT": "沃尔玛", "JPM": "摩根大通", "V": "Visa",
    "MA": "万事达", "PG": "宝洁", "KO": "可口可乐", "PEP": "百事可乐",
}

# 美股板块 -> A股板块映射
US_TO_CN_SECTOR_MAPPING = {
    "Technology": "科技/半导体", "Semiconductors": "半导体",
    "Software": "软件服务", "Internet": "互联网", "E-commerce": "电商",
    "Electric Vehicles": "新能源汽车", "Clean Energy": "新能源/光伏",
    "Biotechnology": "生物医药", "Consumer Electronics": "消费电子",
    "Banking": "银行", "Financial Services": "金融",
}


class DataCollector:
    """数据采集器 - 只返回真实数据"""

    def __init__(self):
        self.session = requests.Session()
        self.session.headers.update({
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36',
            'Accept': '*/*',
            'Accept-Language': 'zh-CN,zh;q=0.9',
        })

    def collect_all(self) -> dict:
        """采集所有数据"""
        logger.info("开始采集盘前数据...")

        result = {
            "us_indices": [],
            "a50": None,
            "top_gainers": [],      # 涨幅前5
            "top_losers": [],       # 跌幅前5
            "commodities": [],      # 大宗商品
            "exchange_rates": [],   # 汇率
            "news": [],             # 财经新闻
            "collect_time": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            "errors": [],
        }

        # 1. 美股指数
        try:
            indices = self._collect_us_indices()
            if indices:
                result["us_indices"] = indices
                logger.info(f"美股指数: {len(indices)} 条")
            else:
                result["errors"].append("美股指数采集失败")
        except Exception as e:
            result["errors"].append(f"美股指数异常: {e}")

        # 2. A50期货
        try:
            a50 = self._collect_a50()
            if a50:
                result["a50"] = a50
                logger.info(f"A50期货: {a50.price:.2f}")
            else:
                result["errors"].append("A50期货采集失败")
        except Exception as e:
            result["errors"].append(f"A50期货异常: {e}")

        # 3. 美股涨跌幅榜
        try:
            gainers, losers = self._collect_us_top_stocks()
            result["top_gainers"] = gainers[:5]
            result["top_losers"] = losers[:5]
            logger.info(f"美股涨跌幅: 涨{len(gainers)}跌{len(losers)}")
        except Exception as e:
            result["errors"].append(f"美股涨跌幅异常: {e}")

        # 4. 大宗商品
        try:
            commodities = self._collect_commodities()
            if commodities:
                result["commodities"] = commodities
                logger.info(f"大宗商品: {len(commodities)} 条")
            else:
                result["errors"].append("大宗商品采集失败")
        except Exception as e:
            result["errors"].append(f"大宗商品异常: {e}")

        # 5. 汇率
        try:
            rates = self._collect_exchange_rates()
            if rates:
                result["exchange_rates"] = rates
                logger.info(f"汇率: {len(rates)} 条")
            else:
                result["errors"].append("汇率采集失败")
        except Exception as e:
            result["errors"].append(f"汇率异常: {e}")

        # 6. 财经新闻
        try:
            news = self._collect_financial_news()
            if news:
                result["news"] = news
                logger.info(f"财经新闻: {len(news)} 条")
        except Exception as e:
            result["errors"].append(f"财经新闻异常: {e}")

        return result

    def _collect_us_indices(self) -> List[MarketData]:
        """采集美股主要指数"""
        results = []
        symbols = [
            ("gb_$dji", "道琼斯"),
            ("gb_$nasdaq", "纳斯达克"),
            ("gb_$spx", "标普500"),
            ("gb_$hxc", "金龙指数"),
        ]

        headers = {
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36',
            'Referer': 'https://finance.sina.com.cn/',
        }

        for symbol, name in symbols:
            try:
                url = f"https://hq.sinajs.cn/list={symbol}"
                r = self.session.get(url, headers=headers, timeout=10)
                r.encoding = 'gbk'
                match = re.search(r'="([^"]*)"', r.text)
                if match:
                    parts = match.group(1).split(',')
                    # 新浪数据格式: 名称,价格,涨跌幅,时间,涨跌额,...
                    if len(parts) >= 5 and parts[1]:
                        try:
                            price = float(parts[1])
                            if price > 0:
                                results.append(MarketData(
                                    symbol=symbol,
                                    name=parts[0] if parts[0] else name,
                                    price=price,
                                    change=float(parts[4]) if len(parts) > 4 and parts[4] else 0,
                                    change_pct=float(parts[2]) if len(parts) > 2 and parts[2] else 0,
                                    timestamp=parts[3] if len(parts) > 3 else "",
                                    source="新浪财经"
                                ))
                        except ValueError:
                            logger.debug(f"{name}: 价格解析失败")
            except Exception as e:
                logger.debug(f"{name}: {e}")

        return results

    def _collect_a50(self) -> Optional[MarketData]:
        """采集富时中国A50期货"""
        headers = {
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36',
            'Referer': 'https://quote.eastmoney.com/gb/zsxin9.html',
        }
        url = 'https://push2.eastmoney.com/api/qt/ulist.np/get'
        params = {'fltt': 2, 'secids': '100.XIN9', 'fields': 'f12,f14,f2,f3,f4,f18'}

        try:
            r = self.session.get(url, params=params, headers=headers, timeout=10)
            data = r.json()
            if data.get('data') and data['data'].get('diff'):
                diff = data['data']['diff'][0]
                price = diff.get('f2', 0)
                if price > 0:
                    return MarketData(
                        symbol="XIN9",
                        name=diff.get('f14', '富时中国A50'),
                        price=float(price),
                        change=float(diff.get('f4', 0)),
                        change_pct=float(diff.get('f3', 0)),
                        timestamp="",
                        source="东方财富"
                    )
        except Exception as e:
            logger.debug(f"A50: {e}")
        return None

    def _collect_us_top_stocks(self) -> tuple:
        """采集美股涨幅前5和跌幅前5"""
        if not AKSHARE_AVAILABLE:
            return [], []

        stocks = []
        # 获取热门美股数据
        hot_stocks = list(US_STOCK_NAMES.keys())[:20]

        for symbol in hot_stocks:
            try:
                df = ak.stock_us_daily(symbol=symbol, adjust="qfq")
                if df.empty or len(df) < 2:
                    continue

                latest = df.iloc[-1]
                prev = df.iloc[-2]

                price = float(latest['close'])
                prev_close = float(prev['close'])
                change_pct = (price - prev_close) / prev_close * 100 if prev_close > 0 else 0
                volume = int(latest['volume']) if latest['volume'] else 0

                vol_str = f"{volume/1000000:.1f}M" if volume >= 1000000 else f"{volume/1000:.0f}K"

                stocks.append(TopStock(
                    symbol=symbol,
                    name=US_STOCK_NAMES.get(symbol, symbol),
                    price=price,
                    change_pct=change_pct,
                    volume=vol_str,
                    sector="",
                    a_share_mapping="",
                    catalyst=""
                ))
            except Exception as e:
                logger.debug(f"{symbol}: {e}")

        # 分离涨跌
        gainers = sorted([s for s in stocks if s.change_pct > 0], key=lambda x: x.change_pct, reverse=True)
        losers = sorted([s for s in stocks if s.change_pct < 0], key=lambda x: x.change_pct)

        return gainers, losers

    def _collect_commodities(self) -> List[Commodity]:
        """采集大宗商品（原油、黄金、铜）- 使用 Yahoo Finance API"""
        results = []

        proxies = {
            'http': 'http://127.0.0.1:7890',
            'https': 'http://127.0.0.1:7890',
        }

        commodities = [
            ('GC=F', '黄金', '美元/盎司', '避险情绪升温，黄金股受益'),
            ('CL=F', '原油', '美元/桶', '油价上涨利好石油化工'),
            ('HG=F', '铜', '美元/磅', '铜价上涨利好有色金属'),
        ]

        for symbol, name, unit, impact in commodities:
            try:
                url = f'https://query1.finance.yahoo.com/v8/finance/chart/{symbol}?interval=1d&range=2d'
                r = self.session.get(url, timeout=10, proxies=proxies)
                data = r.json()

                if data.get('chart', {}).get('result'):
                    result = data['chart']['result'][0]
                    meta = result.get('meta', {})
                    price = meta.get('regularMarketPrice', 0)

                    # 计算涨跌幅
                    quotes = result.get('indicators', {}).get('quote', [])
                    if quotes and quotes[0].get('close'):
                        closes = quotes[0]['close']
                        if len(closes) >= 2 and closes[-1] and closes[-2]:
                            change_pct = (closes[-1] - closes[-2]) / closes[-2] * 100
                        else:
                            change_pct = 0
                    else:
                        change_pct = 0

                    if price > 0:
                        results.append(Commodity(
                            name=name,
                            price=float(price),
                            change_pct=float(change_pct),
                            unit=unit,
                            a_share_impact=impact if change_pct > 0 else "影响有限"
                        ))
            except Exception as e:
                logger.debug(f"{name}: {e}")

        return results

    def _collect_exchange_rates(self) -> List[ExchangeRate]:
        """采集汇率（美元指数、人民币汇率）"""
        results = []

        proxies = {
            'http': 'http://127.0.0.1:7890',
            'https': 'http://127.0.0.1:7890',
        }

        # 美元指数 (Yahoo Finance)
        try:
            url = 'https://query1.finance.yahoo.com/v8/finance/chart/DX-Y.NYB?interval=1d&range=2d'
            r = self.session.get(url, timeout=10, proxies=proxies)
            data = r.json()

            if data.get('chart', {}).get('result'):
                result = data['chart']['result'][0]
                meta = result.get('meta', {})
                price = meta.get('regularMarketPrice', 0)

                quotes = result.get('indicators', {}).get('quote', [])
                change_pct = 0
                if quotes and quotes[0].get('close'):
                    closes = quotes[0]['close']
                    if len(closes) >= 2 and closes[-1] and closes[-2]:
                        change_pct = (closes[-1] - closes[-2]) / closes[-2] * 100

                if price > 0:
                    results.append(ExchangeRate(
                        name="美元指数",
                        rate=float(price),
                        change_pct=float(change_pct)
                    ))
        except Exception as e:
            logger.debug(f"美元指数: {e}")

        # 美元人民币汇率 (新浪财经)
        try:
            url = "https://hq.sinajs.cn/list=fx_susdcny"
            r = self.session.get(url, timeout=10)
            r.encoding = 'gbk'
            match = re.search(r'="([^"]*)"', r.text)
            if match:
                parts = match.group(1).split(',')
                if len(parts) >= 2 and parts[1]:
                    results.append(ExchangeRate(
                        name="美元/人民币",
                        rate=float(parts[1]),
                        change_pct=0
                    ))
        except Exception as e:
            logger.debug(f"人民币汇率: {e}")

        return results

    def _collect_financial_news(self) -> List[NewsItem]:
        """采集财经新闻并过滤（使用所有数据源）"""
        news_list = []

        # 获取时间范围
        start_time, end_time = get_news_time_range()
        logger.info(f"采集盘后新闻时间范围: {start_time.strftime('%Y-%m-%d %H:%M')} 至 {end_time.strftime('%Y-%m-%d %H:%M')}")

        # 1. 采集新浪财经新闻
        try:
            sina_news = self._collect_sina_news()
            filtered = [n for n in sina_news if is_after_hours_news(n.time)]
            logger.info(f"新浪财经: 原始{len(sina_news)}条，盘后{len(filtered)}条")
            news_list.extend(filtered)
        except Exception as e:
            logger.debug(f"新浪财经采集异常: {e}")

        # 2. 采集东方财富新闻
        try:
            em_news = self._collect_eastmoney_news()
            filtered = [n for n in em_news if is_after_hours_news(n.time)]
            logger.info(f"东方财富: 原始{len(em_news)}条，盘后{len(filtered)}条")
            news_list.extend(filtered)
        except Exception as e:
            logger.debug(f"东方财富采集异常: {e}")

        # 3. 采集财联社新闻
        try:
            cls_news = self._collect_cls_news()
            filtered = [n for n in cls_news if is_after_hours_news(n.time)]
            logger.info(f"财联社: 原始{len(cls_news)}条，盘后{len(filtered)}条")
            news_list.extend(filtered)
        except Exception as e:
            logger.debug(f"财联社采集异常: {e}")

        # 4. 采集华尔街见闻新闻
        try:
            wsc_news = self._collect_wallstreetcn_news()
            filtered = [n for n in wsc_news if is_after_hours_news(n.time)]
            logger.info(f"华尔街见闻: 原始{len(wsc_news)}条，盘后{len(filtered)}条")
            news_list.extend(filtered)
        except Exception as e:
            logger.debug(f"华尔街见闻采集异常: {e}")

        # 5. 采集腾讯财经新闻
        try:
            qq_news = self._collect_qq_news()
            filtered = [n for n in qq_news if is_after_hours_news(n.time)]
            logger.info(f"腾讯财经: 原始{len(qq_news)}条，盘后{len(filtered)}条")
            news_list.extend(filtered)
        except Exception as e:
            logger.debug(f"腾讯财经采集异常: {e}")

        # 6. 采集网易财经新闻
        try:
            netease_news = self._collect_netease_news()
            filtered = [n for n in netease_news if is_after_hours_news(n.time)]
            logger.info(f"网易财经: 原始{len(netease_news)}条，盘后{len(filtered)}条")
            news_list.extend(filtered)
        except Exception as e:
            logger.debug(f"网易财经采集异常: {e}")

        # 7. 采集和讯网新闻
        try:
            hexun_news = self._collect_hexun_news()
            filtered = [n for n in hexun_news if is_after_hours_news(n.time)]
            logger.info(f"和讯网: 原始{len(hexun_news)}条，盘后{len(filtered)}条")
            news_list.extend(filtered)
        except Exception as e:
            logger.debug(f"和讯网采集异常: {e}")

        # 8. 采集证券时报新闻
        try:
            stcn_news = self._collect_stcn_news()
            filtered = [n for n in stcn_news if is_after_hours_news(n.time)]
            logger.info(f"证券时报: 原始{len(stcn_news)}条，盘后{len(filtered)}条")
            news_list.extend(filtered)
        except Exception as e:
            logger.debug(f"证券时报采集异常: {e}")

        # 9. 采集雪球新闻
        try:
            xueqiu_news = self._collect_xueqiu_news()
            filtered = [n for n in xueqiu_news if is_after_hours_news(n.time)]
            logger.info(f"雪球: 原始{len(xueqiu_news)}条，盘后{len(filtered)}条")
            news_list.extend(filtered)
        except Exception as e:
            logger.debug(f"雪球采集异常: {e}")

        # 10. 采集akshare新闻（百度财经）
        if AKSHARE_AVAILABLE:
            try:
                ak_news = self._collect_akshare_news()
                filtered = [n for n in ak_news if is_after_hours_news(n.time)]
                logger.info(f"akshare新闻: 原始{len(ak_news)}条，盘后{len(filtered)}条")
                news_list.extend(filtered)
            except Exception as e:
                logger.debug(f"akshare新闻采集异常: {e}")

        # 11. 采集韭菜公社新闻（短线题材）
        try:
            jiagu_news = self._collect_jiagu_news()
            filtered = [n for n in jiagu_news if is_after_hours_news(n.time)]
            logger.info(f"韭菜公社: 原始{len(jiagu_news)}条，盘后{len(filtered)}条")
            news_list.extend(filtered)
        except Exception as e:
            logger.debug(f"韭菜公社采集异常: {e}")

        # 12. 采集36氪新闻（科技）
        try:
            kr36_news = self._collect_36kr_news()
            filtered = [n for n in kr36_news if is_after_hours_news(n.time)]
            logger.info(f"36氪: 原始{len(kr36_news)}条，盘后{len(filtered)}条")
            news_list.extend(filtered)
        except Exception as e:
            logger.debug(f"36氪采集异常: {e}")

        # 13. 采集界面新闻
        try:
            jiemian_news = self._collect_jiemian_news()
            filtered = [n for n in jiemian_news if is_after_hours_news(n.time)]
            logger.info(f"界面新闻: 原始{len(jiemian_news)}条，盘后{len(filtered)}条")
            news_list.extend(filtered)
        except Exception as e:
            logger.debug(f"界面新闻采集异常: {e}")

        # 14. 采集第一财经
        try:
            cbn_news = self._collect_cbn_news()
            filtered = [n for n in cbn_news if is_after_hours_news(n.time)]
            logger.info(f"第一财经: 原始{len(cbn_news)}条，盘后{len(filtered)}条")
            news_list.extend(filtered)
        except Exception as e:
            logger.debug(f"第一财经采集异常: {e}")

        # 15. 采集澎湃新闻
        try:
            thepaper_news = self._collect_thepaper_news()
            filtered = [n for n in thepaper_news if is_after_hours_news(n.time)]
            logger.info(f"澎湃新闻: 原始{len(thepaper_news)}条，盘后{len(filtered)}条")
            news_list.extend(filtered)
        except Exception as e:
            logger.debug(f"澎湃新闻采集异常: {e}")

        # 16. 使用Playwright抓取网页新闻（财联社、东方财富等）
        try:
            playwright_news = self._collect_playwright_news()
            # Playwright新闻时间可能为空，需要处理
            filtered_playwright = []
            for n in playwright_news:
                # 如果时间为空，设置为昨天收盘后时间（确保在盘后范围内）
                if not n.time:
                    # 盘后时间范围：昨天15:30-今天08:30
                    # 设为昨天20:00，确保在盘后范围内
                    yesterday = datetime.now() - timedelta(days=1)
                    n.time = yesterday.strftime("%Y-%m-%d 20:00")
                if is_after_hours_news(n.time):
                    filtered_playwright.append(n)
            logger.info(f"Playwright: 原始{len(playwright_news)}条，盘后{len(filtered_playwright)}条")
            news_list.extend(filtered_playwright)
        except Exception as e:
            logger.debug(f"Playwright采集异常: {e}")

        # 去重（根据标题）
        seen_titles = set()
        unique_news = []
        for news in news_list:
            if news.title not in seen_titles:
                seen_titles.add(news.title)
                unique_news.append(news)

        # 计算权重并排序
        logger.info(f"合计盘后新闻: {len(news_list)}条，去重后: {len(unique_news)}条")
        logger.info("开始计算新闻权重并排序...")

        # 为每条新闻计算权重
        for news in unique_news:
            news.calculate_weight()

        # 按权重排序（高权重在前）
        unique_news.sort(key=lambda x: x.weight_score, reverse=True)

        # 记录权重分布
        top_10 = unique_news[:10] if len(unique_news) >= 10 else unique_news
        logger.info(f"权重评分完成，Top 10新闻权重范围: {top_10[-1].weight_score:.1f} - {top_10[0].weight_score:.1f}")

        # 返回所有新闻（无上限）
        return unique_news

    def _collect_cls_news(self) -> List[NewsItem]:
        """采集财联社新闻（7x24快讯）- API已失效，使用Playwright抓取"""
        # 财联社API需要签名验证，已由Playwright统一抓取
        # 参见 playwright_crawler.py 中的 fetch_cls_news 方法
        return []

        # 备用：爬取财联社网页
        try:
            url = "https://www.cls.cn/telegraph"
            headers = {
                'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36',
            }

            r = self.session.get(url, headers=headers, timeout=10)
            # 提取JSON数据
            import re
            json_match = re.search(r'window\.__INITIAL_STATE__\s*=\s*({.+?});', r.text)
            if json_match:
                data = json.loads(json_match.group(1))
                items = data.get("telegraph", {}).get("list", [])

                for item in items:
                    title = item.get("title", "").strip()
                    content = item.get("content", "").strip()

                    if not title:
                        continue

                    if self._is_valid_news(title):
                        related = self._extract_related_stocks(title + content)
                        relevance = self._judge_relevance(title + content)

                        # 解析时间
                        time_str = ""
                        ctime = item.get("ctime", "")
                        if ctime and str(ctime).isdigit():
                            dt = datetime.fromtimestamp(int(ctime) / 1000)
                            time_str = dt.strftime("%Y-%m-%d %H:%M:%S")

                        news_list.append(NewsItem(
                            title=title,
                            source="财联社",
                            time=time_str,
                            relevance=relevance,
                            related_stocks=related,
                            content=content if content else title
                        ))

        except Exception as e:
            logger.debug(f"财联社网页: {e}")

        return news_list

    def _collect_wallstreetcn_news(self) -> List[NewsItem]:
        """采集华尔街见闻新闻（优先使用本地接口）"""
        news_list = []

        # 首先尝试本地接口
        try:
            url = "http://127.0.0.1:8888/v1/news/wallstreet"
            r = self.session.get(url, timeout=10)
            data = r.json()

            if isinstance(data, list):
                items = data
            elif isinstance(data, dict):
                items = data.get("data", data.get("items", []))
            else:
                items = []

            for item in items:
                title = item.get("title", "").strip()
                content = item.get("content", item.get("summary", "")).strip()[:300]

                if not title:
                    continue

                if self._is_valid_news(title):
                    related = self._extract_related_stocks(title + content)
                    relevance = self._judge_relevance(title + content)

                    # 解析时间
                    time_str = ""
                    pub_time = item.get("pub_time", item.get("time", item.get("display_time", "")))
                    if pub_time:
                        try:
                            if str(pub_time).isdigit():
                                # 时间戳
                                timestamp = int(pub_time) / 1000 if len(str(pub_time)) > 10 else int(pub_time)
                                dt = datetime.fromtimestamp(timestamp)
                                time_str = dt.strftime("%Y-%m-%d %H:%M:%S")
                            else:
                                time_str = pub_time
                        except:
                            time_str = str(pub_time)

                    news_list.append(NewsItem(
                        title=title,
                        source=item.get("source", "华尔街见闻"),
                        time=time_str,
                        relevance=relevance,
                        related_stocks=related,
                        content=content if content else title
                    ))

            if news_list:
                logger.info(f"华尔街见闻本地接口: {len(news_list)} 条")
                return news_list

        except Exception as e:
            logger.debug(f"华尔街见闻本地接口: {e}")

        # 备用：官方API
        try:
            url = "https://api.wallstcn.com/apiv1/content/articles"
            params = {'category': 'global', 'limit': 50}
            headers = {
                'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36',
                'Accept': 'application/json'
            }

            r = self.session.get(url, params=params, headers=headers, timeout=10)
            data = r.json()

            if data.get("code") == 20000:
                items = data.get("data", {}).get("items", [])
                for item in items:
                    title = item.get("title", "").strip()
                    content = item.get("content_short", item.get("content", ""))[:200]

                    if not title:
                        continue

                    if self._is_valid_news(title):
                        related = self._extract_related_stocks(title + content)
                        relevance = self._judge_relevance(title + content)

                        # 解析时间
                        time_str = ""
                        display_time = item.get("display_time", "")
                        if display_time:
                            try:
                                dt = datetime.fromisoformat(display_time.replace('Z', '+00:00'))
                                time_str = dt.strftime("%Y-%m-%d %H:%M:%S")
                            except:
                                pass

                        news_list.append(NewsItem(
                            title=title,
                            source="华尔街见闻",
                            time=time_str,
                            relevance=relevance,
                            related_stocks=related,
                            content=content if content else title
                        ))

                logger.info(f"华尔街见闻官方API: {len(news_list)} 条")

        except Exception as e:
            logger.debug(f"华尔街见闻官方API: {e}")

        return news_list

    def _collect_eastmoney_news(self) -> List[NewsItem]:
        """采集东方财富新闻 - 使用akshare"""
        news_list = []

        # 方案1: 使用akshare获取东方财富要闻
        if AKSHARE_AVAILABLE:
            try:
                import akshare as ak
                df = ak.stock_news_main_cx()

                if not df.empty:
                    for _, row in df.head(50).iterrows():
                        title = str(row.get("summary", ""))
                        if not title or title == "nan":
                            continue

                        # 获取时间
                        time_str = str(row.get("time", "")) if pd.notna(row.get("time")) else ""

                        if self._is_valid_news(title):
                            related = self._extract_related_stocks(title)
                            relevance = self._judge_relevance(title)

                            news_list.append(NewsItem(
                                title=title,
                                source="东方财富",
                                time=time_str,
                                relevance=relevance,
                                related_stocks=related,
                                content=title
                            ))

                    if news_list:
                        logger.info(f"akshare东方财富: {len(news_list)} 条")
                        return news_list
            except Exception as e:
                logger.debug(f"akshare东方财富: {e}")

        # 方案2: 旧的API（可能已经失效，作为备用）
        try:
            url = "https://np-anotice-stock.eastmoney.com/api/security/ann"
            params = {
                "pageSize": 50,
                "pageNo": 1,
                "type": "7x24",
            }
            headers = {
                'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36',
                'Accept': 'application/json',
                'Referer': 'https://data.eastmoney.com/',
            }

            r = self.session.get(url, params=params, headers=headers, timeout=10)
            data = r.json()

            if data.get("success") == True or data.get("code") == 0:
                items = data.get("data", {}).get("list", [])
                for item in items:
                    title = item.get("title", "").strip()
                    content = item.get("content", "").strip()[:200]

                    if not title:
                        continue

                    if self._is_valid_news(title):
                        related = self._extract_related_stocks(title + content)
                        relevance = self._judge_relevance(title + content)

                        time_str = ""
                        notice_date = item.get("notice_date", item.get("time", ""))
                        if notice_date:
                            try:
                                if str(notice_date).isdigit():
                                    dt = datetime.fromtimestamp(int(notice_date))
                                    time_str = dt.strftime("%Y-%m-%d %H:%M:%S")
                                else:
                                    time_str = notice_date
                            except:
                                time_str = str(notice_date)

                        news_list.append(NewsItem(
                            title=title,
                            source="东方财富",
                            time=time_str,
                            relevance=relevance,
                            related_stocks=related,
                            content=content if content else title
                        ))

                if news_list:
                    logger.info(f"东方财富7x24: {len(news_list)} 条")
                    return news_list

        except Exception as e:
            logger.debug(f"东方财富7x24 API: {e}")

        return news_list

    def _collect_10jqka_news(self) -> List[NewsItem]:
        """采集同花顺新闻 - API + Playwright双保险"""
        news_list = []

        # 方案1: 尝试API接口
        try:
            # 同花顺财经新闻API
            url = "https://basic.10jqka.com.cn/api/stockph/lives"
            params = {
                "page": 1,
                "limit": 30,
                "type": "finance"
            }

            r = self.session.get(url, params=params, timeout=10)
            data = r.json()

            if data.get("status") == 0 or data.get("code") == 200:
                items = data.get("data", {}).get("list", []) or data.get("data", [])
                for item in items:
                    title = item.get("title", item.get("content", ""))[:100]
                    if not title:
                        continue

                    if self._is_valid_news(title):
                        related = self._extract_related_stocks(title)
                        relevance = self._judge_relevance(title)

                        news_list.append(NewsItem(
                            title=title,
                            source=item.get("source", "同花顺"),
                            time=item.get("time", ""),
                            relevance=relevance,
                            related_stocks=related,
                            content=item.get("content", title)[:200]
                        ))

                if news_list:
                    logger.info(f"同花顺API采集: {len(news_list)} 条")
                    return news_list
        except Exception as e:
            logger.debug(f"同花顺API: {e}")

        # 方案2: 如果API失败，Playwright会处理（已在_playwright_news中统一处理）
        logger.info("同花顺API未获取到数据，将使用Playwright抓取")
        return []

    def _collect_sina_news(self) -> List[NewsItem]:
        """采集新浪财经新闻"""
        news_list = []

        # 新浪财经多个接口（增加更多源）
        feeds = [
            # 财经要闻
            {"pageid": "153", "lid": "2516", "num": 50},  # 财经频道
            {"pageid": "153", "lid": "2517", "num": 50},  # 股票频道
            {"pageid": "153", "lid": "2515", "num": 30},  # 国内财经
            {"pageid": "153", "lid": "2518", "num": 30},  # 国际财经
        ]

        for feed in feeds:
            try:
                url = "https://feed.sina.com.cn/api/roll/get"
                params = {
                    "pageid": feed["pageid"],
                    "lid": feed["lid"],
                    "num": feed["num"],
                    "page": 1,
                    "versionNumber": "1.2.4",
                    "encode": "utf-8"
                }

                r = self.session.get(url, params=params, timeout=10)
                data = r.json()

                # 处理新浪API返回的状态
                result = data.get("result", {})
                status = result.get("status")
                if isinstance(status, dict):
                    status_code = status.get("code")
                else:
                    status_code = status

                if status_code == 0:
                    items = result.get("data", [])
                    for item in items:
                        title = item.get("title", "").strip()

                        if not title or len(title) < 10:
                            continue

                        if self._is_valid_news(title):
                            related = self._extract_related_stocks(title)
                            relevance = self._judge_relevance(title)

                            news_list.append(NewsItem(
                                title=title,
                                source="新浪财经",
                                time=item.get("time", ""),
                                relevance=relevance,
                                related_stocks=related,
                                content=title
                            ))
            except Exception as e:
                logger.debug(f"新浪财经新闻接口: {e}")

        return news_list

    def _is_valid_news(self, title: str) -> bool:
        """判断新闻是否有效（过滤噪音）- 宽松版本，依靠权重系统排序"""
        if not title or len(title) < 8:
            return False

        # 过滤明显的无效关键词（广告、推广等）
        invalid_keywords = [
            "广告", "推广", "福利", "优惠", "抽奖", "领取",
            "点击查看", "扫码", "关注公众号", "转发",
            "点击这里", "立即购买", "限时优惠", "免费赠送"
        ]
        for kw in invalid_keywords:
            if kw in title:
                return False

        # 宽松的关键词检查 - 只要包含部分财经相关词即可
        # 即使不包含，也返回True，让权重系统去排序
        valid_keywords = [
            "股", "A股", "港", "美", "指数", "期货", "期权",
            "涨", "跌", "涨停", "跌停", "利好", "利空",
            "板块", "概念", "题材", "龙头", "行情",
            "业绩", "财报", "营收", "利润", "分红",
            "上市", "IPO", "并购", "重组", "定增",
            "政策", "监管", "央行", "证监会", "发改委",
            "芯片", "半导体", "AI", "新能源", "光伏", "锂电",
            "原油", "黄金", "油价", "金价",
            "医药", "消费", "地产", "银行", "保险", "券商",
            "美元", "人民币", "汇率", "美联储", "加息", "降息",
            "公司", "集团", "股份", "科技", "产业"
        ]

        # 只要包含至少一个关键词即通过（大幅降低门槛）
        # 如果不包含任何关键词，也返回True但权重会很低
        return True  # 允许所有非垃圾新闻通过，由权重系统排序

        has_valid = any(kw in title for kw in valid_keywords)
        return has_valid

    def _collect_qq_news(self) -> List[NewsItem]:
        """采集腾讯财经新闻 - API已失效，使用Playwright抓取"""
        # 腾讯财经API返回404，已由Playwright统一抓取
        return []

    def _collect_netease_news(self) -> List[NewsItem]:
        """采集网易财经新闻 - API失效，使用akshare百度财经替代"""
        # 网易财经JS接口不稳定，改用akshare百度财经
        return []

    def _collect_hexun_news(self) -> List[NewsItem]:
        """采集和讯网新闻 - SSL错误，使用Playwright抓取"""
        # 和讯网SSL连接失败，已由Playwright统一抓取
        return []

    def _collect_stcn_news(self) -> List[NewsItem]:
        """采集证券时报新闻 - SSL错误，使用Playwright抓取"""
        # 证券时报SSL连接失败，已由Playwright统一抓取
        return []

    def _collect_xueqiu_news(self) -> List[NewsItem]:
        """采集雪球新闻 - API已失效，使用Playwright抓取"""
        # 雪球API返回404，已由Playwright统一抓取
        return []

    def _collect_akshare_news(self) -> List[NewsItem]:
        """采集akshare新闻（百度财经+东方财富+CCTV）"""
        news_list = []

        try:
            import akshare as ak

            # 1. 百度经济新闻
            try:
                df = ak.news_economic_baidu()
                if not df.empty:
                    for _, row in df.iterrows():
                        title = str(row.get("标题", ""))
                        if not title or title == "nan":
                            continue

                        if self._is_valid_news(title):
                            related = self._extract_related_stocks(title)
                            relevance = self._judge_relevance(title)

                            # 解析时间
                            time_str = ""
                            pub_time = row.get("时间", "")
                            if pub_time and str(pub_time) != "nan":
                                time_str = str(pub_time)

                            news_list.append(NewsItem(
                                title=title,
                                source="百度财经",
                                time=time_str,
                                relevance=relevance,
                                related_stocks=related,
                                content=str(row.get("事件", title))[:200]
                            ))
            except Exception as e:
                logger.debug(f"akshare百度财经: {e}")

            # 2. 东方财富主要新闻
            try:
                df = ak.stock_news_main_cx()
                if not df.empty:
                    for _, row in df.iterrows():
                        title = str(row.get("summary", ""))
                        if not title or title == "nan":
                            continue

                        if self._is_valid_news(title):
                            related = self._extract_related_stocks(title)
                            relevance = self._judge_relevance(title)

                            news_list.append(NewsItem(
                                title=title,
                                source="东方财富",
                                time="",
                                relevance=relevance,
                                related_stocks=related,
                                content=title
                            ))
            except Exception as e:
                logger.debug(f"akshare东方财富: {e}")

            # 3. CCTV新闻联播
            try:
                df = ak.news_cctv()
                if not df.empty:
                    for _, row in df.iterrows():
                        title = str(row.get("标题", ""))
                        if not title or title == "nan":
                            continue

                        if self._is_valid_news(title):
                            related = self._extract_related_stocks(title)
                            relevance = self._judge_relevance(title)

                            # CCTV新闻权威性高
                            if relevance == "低":
                                relevance = "中"

                            news_list.append(NewsItem(
                                title=title,
                                source="CCTV",
                                time=str(row.get("日期", "")),
                                relevance=relevance,
                                related_stocks=related,
                                content=str(row.get("内容", title))[:300]
                            ))
            except Exception as e:
                logger.debug(f"akshare CCTV: {e}")

            if news_list:
                logger.info(f"akshare采集: {len(news_list)} 条")

        except ImportError:
            logger.debug("akshare未安装")
        except Exception as e:
            logger.debug(f"akshare采集: {e}")

        return news_list

    def _collect_jiagu_news(self) -> List[NewsItem]:
        """采集韭菜公社新闻 - SSL错误，使用Playwright抓取"""
        # 韭菜公社SSL连接失败，已由Playwright统一抓取
        return []

    def _collect_36kr_news(self) -> List[NewsItem]:
        """采集36氪新闻 - API需要升级，使用Playwright抓取"""
        # 36氪API返回需要升级APP，已由Playwright统一抓取
        return []

    def _collect_jiemian_news(self) -> List[NewsItem]:
        """采集界面新闻 - SSL错误，使用Playwright抓取"""
        # 界面新闻SSL连接失败，已由Playwright统一抓取
        return []

    def _collect_cbn_news(self) -> List[NewsItem]:
        """采集第一财经新闻 - 需要认证，使用Playwright抓取"""
        # 第一财经API返回401，已由Playwright统一抓取
        return []

    def _collect_thepaper_news(self) -> List[NewsItem]:
        """采集澎湃新闻 - 系统繁忙，使用Playwright抓取"""
        # 澎湃新闻API返回系统繁忙，已由Playwright统一抓取
        return []

    def _collect_playwright_news(self) -> List[NewsItem]:
        """使用Playwright抓取网页新闻"""
        try:
            from src.playwright_crawler import fetch_playwright_news_sync
            return fetch_playwright_news_sync()
        except ImportError:
            logger.debug("Playwright爬虫模块未找到")
            return []
        except Exception as e:
            logger.debug(f"Playwright抓取失败: {e}")
            return []

    def _judge_relevance(self, title: str) -> str:
        """判断新闻与A股的相关性"""
        high_relevance = ["A股", "沪深", "创业板", "科创板", "北向资金", "南向资金",
                         "中概股", "港股", "人民币", "央行", "证监会", "发改委"]
        medium_relevance = ["美股", "纳指", "道指", "美联储", "加息", "降息",
                           "原油", "黄金", "芯片", "AI", "新能源"]

        for kw in high_relevance:
            if kw in title:
                return "高"
        for kw in medium_relevance:
            if kw in title:
                return "中"
        return "低"

    def _extract_related_stocks(self, title: str) -> List[str]:
        """从标题中提取相关股票/板块"""
        related = []
        keywords = {
            "半导体": ["中芯国际", "北方华创", "韦尔股份"],
            "芯片": ["中芯国际", "北方华创", "韦尔股份"],
            "AI": ["科大讯飞", "寒武纪", "海光信息"],
            "新能源": ["宁德时代", "比亚迪", "隆基绿能"],
            "光伏": ["隆基绿能", "通威股份", "阳光电源"],
            "锂电": ["宁德时代", "亿纬锂能", "天齐锂业"],
            "医药": ["恒瑞医药", "药明康德", "片仔癀"],
            "白酒": ["贵州茅台", "五粮液", "泸州老窖"],
            "银行": ["招商银行", "宁波银行", "平安银行"],
            "券商": ["中信证券", "东方财富", "海通证券"],
        }

        for kw, stocks in keywords.items():
            if kw in title:
                related.extend(stocks[:2])

        return list(set(related))[:3]

    def format_data_for_report(self, data: dict) -> str:
        """格式化数据为报告文本"""
        lines = []

        lines.append(f"**采集时间**: {data.get('collect_time', '未知')}")
        lines.append("")

        # 错误信息
        if data.get("errors"):
            lines.append("## ⚠️ 数据采集警告")
            lines.append("")
            for err in data["errors"]:
                lines.append(f"- {err}")
            lines.append("")

        # 美股指数
        lines.append("## 美股主要指数")
        lines.append("")
        if data.get("us_indices"):
            lines.append("| 指数 | 收盘价 | 涨跌幅 |")
            lines.append("|------|--------|--------|")
            for idx in data["us_indices"]:
                pct = f"+{idx.change_pct:.2f}%" if idx.change_pct >= 0 else f"{idx.change_pct:.2f}%"
                lines.append(f"| {idx.name} | {idx.price:.2f} | {pct} |")
        else:
            lines.append("**数据采集失败**")
        lines.append("")

        # A50期货
        lines.append("## 富时中国A50期货")
        lines.append("")
        if data.get("a50"):
            a50 = data["a50"]
            pct = f"+{a50.change_pct:.2f}%" if a50.change_pct >= 0 else f"{a50.change_pct:.2f}%"
            lines.append(f"- **最新价**: {a50.price:.2f}")
            lines.append(f"- **涨跌幅**: {pct}")
        else:
            lines.append("**数据采集失败**")
        lines.append("")

        # 大宗商品
        lines.append("## 大宗商品")
        lines.append("")
        if data.get("commodities"):
            lines.append("| 商品 | 价格 | 涨跌幅 | A股影响 |")
            lines.append("|------|------|--------|----------|")
            for c in data["commodities"]:
                pct = f"+{c.change_pct:.2f}%" if c.change_pct >= 0 else f"{c.change_pct:.2f}%"
                lines.append(f"| {c.name} | {c.price:.2f} {c.unit} | {pct} | {c.a_share_impact} |")
        else:
            lines.append("**数据采集失败**")
        lines.append("")

        # 汇率
        lines.append("## 汇率")
        lines.append("")
        if data.get("exchange_rates"):
            for rate in data["exchange_rates"]:
                pct = f" ({rate.change_pct:+.2f}%)" if rate.change_pct != 0 else ""
                lines.append(f"- **{rate.name}**: {rate.rate:.2f}{pct}")
        else:
            lines.append("**数据采集失败**")
        lines.append("")

        # 美股涨幅榜
        lines.append("## 美股涨幅前5")
        lines.append("")
        if data.get("top_gainers"):
            for i, s in enumerate(data["top_gainers"], 1):
                lines.append(f"{i}. **{s.name} ({s.symbol})**: +{s.change_pct:.1f}% (${s.price:.2f})")
        else:
            lines.append("**数据采集失败**")
        lines.append("")

        # 美股跌幅榜
        lines.append("## 美股跌幅前5")
        lines.append("")
        if data.get("top_losers"):
            for i, s in enumerate(data["top_losers"], 1):
                lines.append(f"{i}. **{s.name} ({s.symbol})**: {s.change_pct:.1f}% (${s.price:.2f})")
        else:
            lines.append("**数据采集失败**")
        lines.append("")

        # 财经新闻
        lines.append("## 财经新闻（已过滤）")
        lines.append("")
        if data.get("news"):
            for n in data["news"]:
                relevance = f"[{n.relevance}相关]" if n.relevance != "低" else ""
                lines.append(f"- {relevance} {n.title}")
                if n.related_stocks:
                    lines.append(f"  相关: {', '.join(n.related_stocks)}")
        else:
            lines.append("**暂无重要新闻**")
        lines.append("")

        return "\n".join(lines)


if __name__ == "__main__":
    from loguru import logger
    logger.remove()
    logger.add(lambda msg: print(msg, end=''), level="INFO")

    collector = DataCollector()
    data = collector.collect_all()
    print(collector.format_data_for_report(data))