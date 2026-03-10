"""
Playwright 新闻爬虫模块（简化版）
使用通用选择器抓取财经新闻
"""
import asyncio
import re
from datetime import datetime
from typing import List
from loguru import logger

try:
    from playwright.async_api import async_playwright
    PLAYWRIGHT_AVAILABLE = True
except ImportError:
    PLAYWRIGHT_AVAILABLE = False
    logger.warning("Playwright 未安装")

from src.collector import NewsItem


class PlaywrightNewsCrawler:
    """Playwright 新闻爬虫 - 简化版"""

    def __init__(self):
        self.browser = None
        self.context = None

    async def init_browser(self):
        """初始化浏览器"""
        if not PLAYWRIGHT_AVAILABLE:
            return False

        try:
            self.playwright = await async_playwright().start()
            self.browser = await self.playwright.chromium.launch(
                headless=True,
                executable_path=r"C:\Program Files\Google\Chrome\Application\chrome.exe",
                args=['--no-sandbox', '--disable-setuid-sandbox', '--disable-dev-shm-usage']
            )
            self.context = await self.browser.new_context(
                viewport={'width': 1920, 'height': 1080},
                user_agent='Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.0'
            )
            logger.info("Playwright 浏览器初始化成功")
            return True
        except Exception as e:
            logger.error(f"Playwright 初始化失败: {e}")
            return False

    async def close(self):
        """关闭浏览器"""
        if self.context:
            await self.context.close()
        if self.browser:
            await self.browser.close()
        if hasattr(self, 'playwright'):
            await self.playwright.stop()

    async def fetch_page_news(self, url: str, source_name: str, limit: int = 20) -> List[NewsItem]:
        """
        通用方法：从页面抓取新闻
        通过分析页面文本内容提取新闻标题
        """
        news_list = []

        if not self.context:
            return news_list

        try:
            page = await self.context.new_page()
            await page.goto(url, timeout=30000)
            await asyncio.sleep(2)  # 等待页面加载

            # 获取页面文本
            content = await page.content()

            # 提取所有可能的标题（通过常见的HTML标签）
            # 查找 h1-h6, a 标签中的文本
            titles = await page.eval_on_selector_all(
                "h1, h2, h3, h4, h5, h6, a[href*='news'], a[href*='article']",
                "elements => elements.map(e => ({text: e.textContent.trim(), href: e.href || ''})).filter(e => e.text.length > 15 && e.text.length < 100)"
            )

            seen = set()
            for item in titles[:limit]:
                title = item['text']
                if not title or title in seen:
                    continue
                seen.add(title)

                # 简单过滤：检查是否包含财经关键词
                if self._is_valid_news(title):
                    news_list.append(NewsItem(
                        title=title,
                        source=source_name,
                        time="",
                        relevance="中",
                        related_stocks=[],
                        content=title
                    ))

            await page.close()
            logger.info(f"{source_name}抓取: {len(news_list)} 条")

        except Exception as e:
            logger.debug(f"{source_name}抓取失败: {e}")

        return news_list

    def _is_valid_news(self, title: str) -> bool:
        """简单判断新闻是否有效"""
        if not title or len(title) < 15:
            return False

        # 财经关键词
        keywords = [
            "股", "A股", "涨停", "跌停", "涨", "跌", "板块", "概念",
            "财报", "业绩", "营收", "利润", "分红",
            "上市", "IPO", "定增", "并购", "重组",
            "政策", "央行", "证监会", "发改委",
            "芯片", "半导体", "AI", "新能源", "光伏", "锂电",
            "原油", "黄金", "油价", "金价",
            "医药", "创新药", "疫苗",
            "汽车", "电动车", "新能源", "电池",
            "美元", "人民币", "汇率", "美联储", "加息", "降息"
        ]

        return any(kw in title for kw in keywords)


async def crawl_all_playwright_news() -> List[NewsItem]:
    """抓取所有网页新闻"""
    if not PLAYWRIGHT_AVAILABLE:
        return []

    crawler = PlaywrightNewsCrawler()

    if not await crawler.init_browser():
        return []

    all_news = []

    # 要抓取的网站列表
    sites = [
        ("https://www.cls.cn/telegraph", "财联社"),
        ("https://kuaixun.eastmoney.com/", "东方财富"),
        ("https://wallstreetcn.com/news/global", "华尔街见闻"),
        ("https://www.36kr.com/information/web_news", "36氪"),
    ]

    try:
        for url, name in sites:
            try:
                news = await crawler.fetch_page_news(url, name, limit=20)
                all_news.extend(news)
                await asyncio.sleep(1)  # 避免请求过快
            except Exception as e:
                logger.debug(f"抓取 {name} 失败: {e}")

    finally:
        await crawler.close()

    logger.info(f"Playwright 合计抓取: {len(all_news)} 条")
    return all_news


def fetch_playwright_news_sync() -> List[NewsItem]:
    """同步接口"""
    if not PLAYWRIGHT_AVAILABLE:
        return []

    try:
        return asyncio.run(crawl_all_playwright_news())
    except Exception as e:
        logger.error(f"Playwright 同步抓取失败: {e}")
        return []
