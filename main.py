"""
盘前信息获取系统 - 主入口
每日早上8:30自动获取外围市场信息，生成盘前分析报告并推送飞书

新增功能：新闻筛选模式（--news-filter）
- 使用 LLM 多维度评估新闻催化潜力
- 题材聚类与强度评估
- 生成次日主线题材预测
"""
import argparse
import sys
from datetime import datetime
from pathlib import Path
from dotenv import load_dotenv

# 加载环境变量
env_path = Path(__file__).parent / ".env"
if env_path.exists():
    load_dotenv(env_path)
else:
    load_dotenv()

from src.collector import DataCollector
from src.analyzer import LLMAnalyzer
from src.news_analyzer import NewsAnalyzer, TopicClusterer, AnalyzedNewsItem
from src.report_generator import NewsFilterReportGenerator
from src.notifier import FeishuNotifier
from loguru import logger


def run(test_mode: bool = False, output_file: str = None, news_filter: bool = False):
    """
    运行盘前信息获取流程

    Args:
        test_mode: 测试模式，不推送飞书
        output_file: 输出文件路径（可选）
        news_filter: 运行新闻筛选分析
    """
    logger.info("="*60)
    logger.info("盘前信息获取系统启动")
    logger.info(f"时间: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    if test_mode:
        logger.info("[测试模式] 不会推送飞书")
    if news_filter:
        logger.info("[新闻筛选模式] 分析新闻催化潜力")
    logger.info("="*60)

    # 1. 采集数据
    logger.info("\n[Step 1] 开始采集市场数据...")
    collector = DataCollector()
    data = collector.collect_all()

    # 新闻筛选模式
    if news_filter:
        return _run_news_filter(data, test_mode, output_file)

    # 标准盘前简报模式
    return _run_standard_brief(data, collector, test_mode, output_file)


def _run_news_filter(data: dict, test_mode: bool, output_file: str):
    """运行新闻筛选分析"""
    logger.info("\n[新闻筛选模式] 开始分析新闻催化潜力...")

    # 转换 NewsItem 为 AnalyzedNewsItem
    news_list = data.get("news", [])
    if not news_list:
        logger.warning("没有采集到新闻")
        return ""

    logger.info(f"共采集 {len(news_list)} 条新闻")

    analyzed_items = []
    for news in news_list:
        analyzed_items.append(AnalyzedNewsItem(
            title=news.title,
            source=news.source,
            time=news.time,
            content=news.content if news.content else news.title,
            relevance=news.relevance,
            related_stocks=news.related_stocks
        ))

    # 2. LLM 分析新闻
    logger.info(f"\n[Step 2] LLM 分析 {len(analyzed_items)} 条新闻...")
    analyzer = NewsAnalyzer()
    analyzed_news = analyzer.analyze_news(analyzed_items)

    # 3. 题材聚类
    logger.info("\n[Step 3] 题材聚类...")
    clusterer = TopicClusterer(analyzer)
    clusters = clusterer.cluster_news(analyzed_news)

    # 4. 计算题材强度
    logger.info("\n[Step 4] 计算题材强度...")
    clusters = clusterer.calculate_topic_strength(clusters)

    logger.info(f"发现 {len(clusters)} 个题材")
    for c in clusters[:5]:
        logger.info(f"  - {c.name}: 强度{c.strength_index}, {c.news_count}条新闻")

    # 5. 生成报告（TOP5题材）
    logger.info("\n[Step 5] 生成新闻筛选报告...")
    report_gen = NewsFilterReportGenerator()
    full_report = report_gen.generate_report(clusters, top_n=5)

    # 6. 输出报告
    logger.info("\n[Step 6] 输出报告...")
    print("\n" + "="*60)
    print("【新闻筛选报告】")
    print("="*60)
    try:
        print(full_report)
    except UnicodeEncodeError:
        safe_report = full_report.encode('gbk', errors='replace').decode('gbk')
        print(safe_report)

    # 保存到文件
    today = datetime.now().strftime("%Y%m%d")
    default_file = f"news_filter_{today}.md"
    save_path = output_file or default_file
    Path(save_path).write_text(full_report, encoding='utf-8')
    logger.info(f"报告已保存到: {save_path}")

    # 7. 推送飞书
    if not test_mode:
        logger.info("\n[Step 7] 推送飞书...")
        notifier = FeishuNotifier()

        # 生成简洁版本用于飞书（TOP5）
        simple_report = report_gen.generate_simple_summary(clusters, top_n=5)
        success = notifier.send_report(
            simple_report,
            title=f"次日主线题材预测 - {datetime.now().strftime('%Y-%m-%d')}"
        )

        if success:
            logger.info("推送成功！")
        else:
            logger.warning("推送失败，请检查 Webhook 配置")
    else:
        logger.info("\n[Step 7] 跳过飞书推送（测试模式）")

    logger.info("\n" + "="*60)
    logger.info("新闻筛选分析完成")
    logger.info("="*60)

    return full_report


def _run_standard_brief(data: dict, collector: DataCollector, test_mode: bool, output_file: str):
    """运行标准盘前简报"""
    # 2. 格式化数据
    logger.info("\n[Step 2] 格式化数据...")
    market_text = collector.format_data_for_report(data)

    # 3. LLM 分析
    logger.info("\n[Step 3] LLM 分析生成报告...")
    analyzer = LLMAnalyzer()
    llm_report = analyzer.analyze(market_text)

    # 添加元信息
    today = datetime.now().strftime("%Y-%m-%d")
    time_str = datetime.now().strftime("%H:%M:%S")

    # 构建完整报告
    full_report = f"""# 盘前简报 - {today}

{market_text}

---

## LLM 智能分析

{llm_report}

---
生成时间: {time_str}
数据来源: 新浪财经、东方财富、Yahoo Finance
"""

    # 4. 输出报告
    logger.info("\n[Step 4] 输出报告...")
    print("\n" + "="*60)
    print("【盘前简报】")
    print("="*60)
    try:
        print(full_report)
    except UnicodeEncodeError:
        safe_report = full_report.encode('gbk', errors='replace').decode('gbk')
        print(safe_report)

    # 保存到文件
    if output_file:
        Path(output_file).write_text(full_report, encoding='utf-8')
        logger.info(f"报告已保存到: {output_file}")
    else:
        default_file = f"pre_market_brief_{datetime.now().strftime('%Y%m%d_%H%M')}.md"
        Path(default_file).write_text(full_report, encoding='utf-8')
        logger.info(f"报告已保存到: {default_file}")

    # 5. 推送飞书
    if not test_mode:
        logger.info("\n[Step 5] 推送飞书...")
        notifier = FeishuNotifier()
        success = notifier.send_report(full_report, title=f"盘前简报 - {today}")

        if success:
            logger.info("推送成功！")
        else:
            logger.warning("推送失败，请检查 Webhook 配置")
    else:
        logger.info("\n[Step 5] 跳过飞书推送（测试模式）")

    logger.info("\n" + "="*60)
    logger.info("盘前信息获取完成")
    logger.info("="*60)

    return full_report


def main():
    parser = argparse.ArgumentParser(
        description="盘前信息获取系统 - 自动获取外围市场信息并生成分析报告",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
示例:
  # 正常运行（推送飞书）
  python main.py

  # 测试模式（不推送飞书）
  python main.py --test

  # 新闻筛选模式（分析次日题材）
  python main.py --news-filter

  # 指定输出文件
  python main.py --output report.md

  # 显示详细日志
  python main.py --verbose
        """
    )

    parser.add_argument(
        "--test", "-t",
        action="store_true",
        help="测试模式，不推送飞书"
    )

    parser.add_argument(
        "--news-filter", "-n",
        action="store_true",
        help="新闻筛选模式，分析新闻催化潜力"
    )

    parser.add_argument(
        "--output", "-o",
        type=str,
        default=None,
        help="输出文件路径"
    )

    parser.add_argument(
        "--verbose", "-v",
        action="store_true",
        help="显示详细日志"
    )

    args = parser.parse_args()

    # 配置日志
    if args.verbose:
        logger.remove()
        logger.add(sys.stderr, level="DEBUG")
    else:
        logger.remove()
        logger.add(sys.stderr, level="INFO", format="<green>{time:HH:mm:ss}</green> | <level>{message}</level>")

    # 运行
    try:
        run(test_mode=args.test, output_file=args.output, news_filter=args.news_filter)
    except KeyboardInterrupt:
        logger.info("\n用户中断")
        sys.exit(0)
    except Exception as e:
        logger.error(f"运行出错: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)


if __name__ == "__main__":
    main()
