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

    def _is_valid_news(self, title: str) -> bool:
        """简单判断新闻是否有效 - 宽松版本"""
        if not title or len(title) < 8:
            return False

        # 过滤明显的无效关键词
        invalid_keywords = [
            "广告", "推广", "福利", "优惠", "抽奖", "领取",
            "点击查看", "扫码", "关注公众号", "转发",
            "点击这里", "立即购买", "限时优惠", "免费赠送"
        ]
        for kw in invalid_keywords:
            if kw in title:
                return False

        # 允许所有非垃圾新闻通过，由权重系统排序
        return True

    async def fetch_page_news(self, url: str, source_name: str, limit: int = 20) -> List[NewsItem]:
        """通用方法：从页面抓取新闻"""
        news_list = []

        if not self.context:
            return news_list

        try:
            page = await self.context.new_page()
            await page.goto(url, timeout=30000)
            await asyncio.sleep(2)

            # 通用选择器
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
            logger.info(f"{source_name}: {len(news_list)} 条")

        except Exception as e:
            logger.debug(f"{source_name}抓取失败: {e}")

        return news_list

    async def fetch_10jqka_news(self, limit: int = 30) -> List[NewsItem]:
        """抓取同花顺实时新闻"""
        news_list = []

        if not self.context:
            return news_list

        try:
            page = await self.context.new_page()
            url = "https://news.10jqka.com.cn/realtimenews.html"

            logger.info(f"开始抓取同花顺实时新闻: {url}")
            await page.goto(url, timeout=30000, wait_until="networkidle")
            await asyncio.sleep(3)

            news_details = await page.query_selector_all('.newsDetail')
            seen_titles = set()

            for detail in news_details[:limit * 2]:
                try:
                    link_elem = await detail.query_selector('a')
                    if not link_elem:
                        continue

                    title = await link_elem.inner_text()
                    title = title.strip()

                    strong_elem = await link_elem.query_selector('strong')
                    if strong_elem:
                        title = await strong_elem.inner_text()
                        title = title.strip()

                    title = title.replace('【', '').replace('】', '').strip()

                    if not title or len(title) < 10 or title in seen_titles:
                        continue

                    seen_titles.add(title)

                    # 同花顺专用验证
                    if len(title) >= 10:
                        news_list.append(NewsItem(
                            title=title,
                            source="同花顺",
                            time="",
                            relevance="中",
                            related_stocks=[],
                            content=title
                        ))

                        if len(news_list) >= limit:
                            break

                except Exception:
                    continue

            await page.close()
            logger.info(f"同花顺实时新闻抓取: {len(news_list)} 条")

        except Exception as e:
            logger.error(f"同花顺实时新闻抓取失败: {e}")

        return news_list[:limit]


    async def fetch_cls_news(self, limit: int = 30) -> List[NewsItem]:
        """抓取财联社实时新闻"""
        news_list = []

        if not self.context:
            return news_list

        try:
            page = await self.context.new_page()
            url = "https://www.cls.cn/telegraph"

            logger.info(f"开始抓取财联社实时新闻: {url}")
            await page.goto(url, timeout=30000, wait_until="networkidle")
            await asyncio.sleep(3)

            # 财联社页面结构: .telegraph-content-box 或 .telegraph-content
            news_boxes = await page.query_selector_all('.telegraph-content-box, .telegraph-content')
            logger.debug(f"找到 {len(news_boxes)} 个新闻元素")

            seen_titles = set()

            for box in news_boxes[:limit * 2]:
                try:
                    # 获取时间
                    time_elem = await box.query_selector('.telegraph-time-box, [class*="time"]')
                    time_str = await time_elem.inner_text() if time_elem else ""

                    # 获取内容
                    text = await box.inner_text()
                    lines = [l.strip() for l in text.split('\n') if l.strip()]

                    if not lines:
                        continue

                    # 提取标题（第一行是时间，后面是内容）
                    title = ""
                    for line in lines:
                        if ':' in line and len(line) <= 8:  # 跳过时间
                            continue
                        if '财联社' in line or len(line) > 15:
                            title = line
                            break

                    if not title or len(title) < 15 or title in seen_titles:
                        continue

                    seen_titles.add(title)

                    news_list.append(NewsItem(
                        title=title,
                        source="财联社",
                        time=time_str.strip() if time_str else "",
                        relevance="高",
                        related_stocks=[],
                        content=title
                    ))

                    if len(news_list) >= limit:
                        break

                except Exception:
                    continue

            await page.close()
            logger.info(f"财联社实时新闻抓取: {len(news_list)} 条")

        except Exception as e:
            logger.error(f"财联社实时新闻抓取失败: {e}")

        return news_list[:limit]


async def crawl_all_playwright_news() -> List[NewsItem]:
    """抓取所有网页新闻"""
    if not PLAYWRIGHT_AVAILABLE:
        return []

    crawler = PlaywrightNewsCrawler()

    if not await crawler.init_browser():
        return []

    all_news = []

    sites = [
        ("https://www.cls.cn/telegraph", "财联社"),
        ("https://kuaixun.eastmoney.com/", "东方财富"),
        ("https://wallstreetcn.com/news/global", "华尔街见闻"),
        ("https://www.36kr.com/information/web_news", "36氪"),
    ]

    try:
        # 同花顺专门抓取
        try:
            jqka_news = await crawler.fetch_10jqka_news(limit=30)
            all_news.extend(jqka_news)
        except Exception as e:
            logger.debug(f"同花顺抓取失败: {e}")

        # 财联社专门抓取
        try:
            cls_news = await crawler.fetch_cls_news(limit=30)
            all_news.extend(cls_news)
        except Exception as e:
            logger.debug(f"财联社抓取失败: {e}")

        # 其他网站通用抓取
        for url, name in sites:
            if name == "财联社":  # 已专门处理
                continue
            try:
                news = await crawler.fetch_page_news(url, name, limit=20)
                all_news.extend(news)
                await asyncio.sleep(1)
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
