"""
新闻筛选报告生成器
生成 TOP 题材分析和博弈建议报告
"""
from datetime import datetime
from typing import List
from dataclasses import dataclass

from src.news_analyzer import AnalyzedNewsItem, TopicCluster


class NewsFilterReportGenerator:
    """新闻筛选报告生成器"""

    def generate_report(self, clusters: List[TopicCluster], top_n: int = 5) -> str:
        """生成新闻筛选报告（默认TOP5）"""
        lines = []

        # 报告头部
        today = datetime.now().strftime("%Y-%m-%d")
        lines.append(f"# 次日主线题材预测 - {today}")
        lines.append("")
        lines.append("> 基于 LLM 多维度评估（时效性、确定性、权威性、新颖度、颗粒度等）")
        lines.append("")

        # 题材概览
        lines.append("## 题材概览")
        lines.append("")
        lines.append("| 排名 | 题材 | 强度 | 新闻数 | 高分新闻 | 平均催化指数 |")
        lines.append("|------|------|------|--------|----------|--------------|")

        for i, cluster in enumerate(clusters[:top_n], 1):
            high_count = cluster.high_score_news
            avg_score = f"{cluster.avg_catalyst_score:.1f}"
            lines.append(
                f"| {i} | {cluster.name} | {cluster.strength_index} | "
                f"{cluster.news_count} | {high_count} | {avg_score} |"
            )

        lines.append("")

        # 如果题材不足5个，显示说明
        if len(clusters) < top_n:
            lines.append(f"> **注**：本次盘后新闻共聚类出 **{len(clusters)}** 个有效题材（目标{top_n}个）")
            lines.append("> 可能原因：盘后新闻数量较少、题材分散度低、或市场处于消息真空期")
            lines.append("")

        lines.append("---")
        lines.append("")

        # 详细题材分析
        lines.append("## 详细题材分析")
        lines.append("")

        for i, cluster in enumerate(clusters[:top_n], 1):
            lines.extend(self._generate_topic_section(cluster, i))
            lines.append("")
            lines.append("---")
            lines.append("")

        # 风险提示
        lines.append("## 整体风险提示")
        lines.append("")

        risks = self._collect_risks(clusters[:top_n])
        for risk in risks:
            lines.append(f"- {risk}")

        lines.append("")

        # 策略建议
        lines.append("## 次日策略建议")
        lines.append("")
        lines.append("### 竞价阶段")
        lines.append("- 观察 TOP3 题材相关个股竞价强度")
        lines.append("- 若题材内多只个股一字或高开5%以上，确认发酵")
        lines.append("")
        lines.append("### 开盘阶段")
        lines.append("- 优先参与强度≥8.0题材的前排标的")
        lines.append("- 强度6.0-8.0题材需看板块联动性再决定")
        lines.append("- 回避强度<6.0的题材")
        lines.append("")

        # 生成时间
        time_str = datetime.now().strftime("%H:%M")
        lines.append(f"---")
        lines.append(f"生成时间: {time_str}")
        lines.append(f"数据来源: 东方财富、财联社、新浪财经")

        return "\n".join(lines)

    def _generate_topic_section(self, cluster: TopicCluster, rank: int) -> List[str]:
        """生成单个题材的详细分析"""
        lines = []

        # 题材标题
        strength_level = "🔥🔥🔥" if cluster.strength_index >= 8 else "🔥🔥" if cluster.strength_index >= 6 else "🔥"
        lines.append(f"## TOP{rank} 题材：{cluster.name} [强度: {cluster.strength_index}] {strength_level}")
        lines.append("")

        # 判断依据
        lines.append("**判断依据**：")
        lines.append(f"- 相关新闻：{cluster.news_count}条（其中≥7分：{cluster.high_score_news}条）")
        lines.append(f"- 平均催化指数：{cluster.avg_catalyst_score:.1f}")

        # 关键词
        if cluster.keywords:
            lines.append(f"- 核心关键词：{', '.join(cluster.keywords[:5])}")

        # 相关标的汇总
        all_stocks = set()
        for news in cluster.news_list:
            all_stocks.update(news.related_stocks)
        if all_stocks:
            lines.append(f"- 相关标的：{', '.join(list(all_stocks)[:8])}")

        lines.append("")

        # 核心新闻（选出3条代表性新闻）
        from src.news_analyzer import TopicClusterer
        clusterer = TopicClusterer()
        representative = clusterer.select_representative_news(cluster, top_n=3)

        lines.append("**核心新闻**（按重要性排序）：")
        lines.append("")

        for j, news in enumerate(representative, 1):
            lines.extend(self._generate_news_detail(news, j))
            lines.append("")

        # 题材风险提示
        topic_risks = [n.risk_warning for n in cluster.news_list if n.risk_warning]
        if topic_risks:
            lines.append("**题材风险提示**：")
            for risk in set(topic_risks):
                lines.append(f"- {risk}")
            lines.append("")

        # 博弈建议
        lines.append("**博弈建议**：")
        if cluster.strength_index >= 8:
            lines.append("✅ **强推** - 次日大概率发酵，可重点参与")
            lines.append("- 优选前排标的，竞价确认强度后可打板或半路")
            lines.append("- 若板块多股一字，可参与换手龙")
        elif cluster.strength_index >= 6:
            lines.append("⚠️ **观察** - 可能发酵，需竞价确认")
            lines.append("- 观察竞价是否有资金抢筹")
            lines.append("- 若有板块效应再参与，避免独苗")
        else:
            lines.append("❌ **回避** - 一日游概率大")
            lines.append("- 见光死风险高，不建议参与")

        return lines

    def _generate_news_detail(self, news: AnalyzedNewsItem, rank: int) -> List[str]:
        """生成单条新闻的详细分析"""
        lines = []

        # 新闻标题
        bet_icon = "✅" if news.worth_betting else "❌"
        lines.append(f"### {rank}. [催化指数: {news.catalyst_score}] {news.title}")
        lines.append("")

        # 基本信息
        lines.append(f"- **来源**：{news.source}")
        lines.append(f"- **时间**：{news.time}")

        # 关键内容（如果有正文）
        if news.content and len(news.content) > 20:
            content = news.content[:100] + "..." if len(news.content) > 100 else news.content
            lines.append(f"- **内容摘要**：{content}")

        # 各维度评分
        lines.append(f"- **权威性**：{news.authority_score}/1.5 | **新颖度**：{news.novelty_score}/0.5 | **颗粒度**：{news.granularity_score}/0.3")

        # 相关标的
        if news.related_stocks:
            lines.append(f"- **相关标的**：{', '.join(news.related_stocks)}")

        # 分析原因
        if news.analysis_reason:
            lines.append(f"- **分析**：{news.analysis_reason}")

        # 博弈建议
        lines.append(f"- **是否博弈**：{bet_icon} {'可博弈' if news.worth_betting else '回避'}（{news.ferment_potential}潜力）")

        # 风险提示
        if news.risk_warning:
            lines.append(f"- **⚠️ 风险**：{news.risk_warning}")

        return lines

    def _collect_risks(self, clusters: List[TopicCluster]) -> List[str]:
        """收集整体风险提示"""
        risks = []

        for cluster in clusters:
            # 独苗风险提示
            all_stocks = set()
            for news in cluster.news_list:
                all_stocks.update(news.related_stocks)

            if len(all_stocks) <= 2:
                risks.append(f"{cluster.name}：标的较少（{len(all_stocks)}只），注意独苗风险")

            # 已发酵风险提示
            high_score_count = sum(1 for n in cluster.news_list if n.catalyst_score >= 8)
            if high_score_count >= 2:
                risks.append(f"{cluster.name}：高分新闻较多，可能已被充分预期")

            # 个股风险提示
            for news in cluster.news_list:
                if news.risk_warning and "涨过" in news.risk_warning:
                    risks.append(f"{news.title[:20]}...：标的近期已大幅上涨，注意追高风险")

        if not risks:
            risks.append("暂无特殊风险，按正常策略执行")

        return risks[:6]  # 最多显示6条

    def generate_simple_summary(self, clusters: List[TopicCluster], top_n: int = 3) -> str:
        """生成简洁摘要（用于飞书推送）"""
        lines = []

        today = datetime.now().strftime("%Y-%m-%d")
        lines.append(f"## 新闻筛选结果 - {today}")
        lines.append("")

        for i, cluster in enumerate(clusters[:top_n], 1):
            strength_emoji = "🔥" * min(int(cluster.strength_index / 2) + 1, 3)
            lines.append(f"### {strength_emoji} TOP{i} {cluster.name} [强度{cluster.strength_index}]")

            # 选一条最重要的新闻
            best_news = max(cluster.news_list, key=lambda n: n.catalyst_score)
            lines.append(f"**{best_news.title}**")

            if best_news.related_stocks:
                lines.append(f"标的：{', '.join(best_news.related_stocks[:4])}")

            lines.append(f"建议：{'可博弈' if cluster.strength_index >= 7 else '观察'}")
            lines.append("")

        return "\n".join(lines)


if __name__ == "__main__":
    # 测试
    from src.news_analyzer import AnalyzedNewsItem, TopicCluster

    # 测试数据
    test_cluster = TopicCluster(
        name="固态电池",
        keywords=["固态电池", "硫化物"],
        news_list=[
            AnalyzedNewsItem(
                title="工信部发布固态电池产业指导意见",
                source="工信部",
                time="15:30",
                content="明确2025年建成10条产线",
                catalyst_score=9.0,
                ferment_potential="高",
                worth_betting=True,
                analysis_reason="顶层设计，有明确量化目标",
                related_stocks=["宁德时代", "亿纬锂能", "赣锋锂业"],
                risk_warning="",
                authority_score=1.5,
                novelty_score=0.5,
                granularity_score=0.3
            ),
            AnalyzedNewsItem(
                title="宁德时代宣布量产时间提前",
                source="公司公告",
                time="16:00",
                content="提前至2025年Q2",
                catalyst_score=8.0,
                ferment_potential="高",
                worth_betting=True,
                analysis_reason="龙头公司超预期",
                related_stocks=["宁德时代", "当升科技"],
                risk_warning="",
                authority_score=0.8,
                novelty_score=0.3,
                granularity_score=0.2
            ),
        ]
    )
    test_cluster.news_count = 2
    test_cluster.avg_catalyst_score = 8.5
    test_cluster.high_score_news = 2
    test_cluster.strength_index = 8.5

    generator = NewsFilterReportGenerator()
    report = generator.generate_report([test_cluster])
    print(report)
