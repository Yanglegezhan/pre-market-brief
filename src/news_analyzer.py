"""
新闻筛选系统 - 使用 LLM 对新闻进行多维度评估
评估维度：时效性、确定性、市场认知、传导路径、资金关注、权威性、新颖度、颗粒度、资金容纳度
"""
import os
import json
import re
from datetime import datetime, timedelta
from typing import List, Dict, Optional
from dataclasses import dataclass, field
from loguru import logger

from openai import OpenAI
import httpx


@dataclass
class AnalyzedNewsItem:
    """经过 LLM 分析的新闻条目"""
    # 原始新闻信息
    title: str
    source: str
    time: str
    content: str = ""  # 新闻正文
    relevance: str = ""
    related_stocks: List[str] = field(default_factory=list)

    # LLM 评估结果
    catalyst_score: float = 0.0      # 催化指数 (0-10)
    ferment_potential: str = ""      # 发酵潜力 (高/中/低)
    worth_betting: bool = False      # 是否值得博弈
    analysis_reason: str = ""        # 分析原因
    risk_warning: str = ""           # 风险提示

    # 题材聚合信息
    topic: str = ""                  # 所属题材
    authority_score: float = 0.0     # 权威性得分 (0-1.5)
    novelty_score: float = 0.0       # 新颖度得分 (0-0.5)
    granularity_score: float = 0.0   # 颗粒度得分 (0-0.3)
    capacity_score: float = 0.0      # 资金容纳度得分 (0-0.2)


@dataclass
class TopicCluster:
    """题材聚类"""
    name: str                        # 题材名称
    keywords: List[str] = field(default_factory=list)  # 关键词
    news_list: List[AnalyzedNewsItem] = field(default_factory=list)

    # 聚合指标
    avg_catalyst_score: float = 0.0  # 平均催化指数
    news_count: int = 0              # 新闻数量
    high_score_news: int = 0         # 高分新闻数量(≥7分)
    strength_index: float = 0.0      # 题材强度指数


# 预设的 base_url 配置
PROVIDER_BASE_URLS = {
    "minimax": "https://api.minimaxi.com/v1",
    "zhipu": "https://open.bigmodel.cn/api/paas/v4",
    "deepseek": "https://api.deepseek.com/v1",
    "qwen": "https://dashscope.aliyuncs.com/compatible-mode/v1",
    "kimi": "https://api.moonshot.cn/v1",
}


class NewsAnalyzer:
    """新闻分析器 - 使用 LLM 评估新闻催化潜力"""

    def __init__(self):
        self.api_key = os.getenv("LLM_API_KEY", "")
        self.model = os.getenv("LLM_MODEL", "MiniMax-M2.5")
        self.base_url = os.getenv("LLM_BASE_URL", PROVIDER_BASE_URLS.get("minimax"))

        if not self.api_key:
            logger.warning("未配置 LLM_API_KEY")
            self.client = None
            return

        # 创建 httpx 客户端
        self.http_client = httpx.Client(verify=False, timeout=120.0)

        # 创建 OpenAI 客户端
        self.client = OpenAI(
            api_key=self.api_key,
            base_url=self.base_url,
            timeout=120.0,
            http_client=self.http_client,
        )
        logger.info(f"新闻分析器初始化完成: model={self.model}")

    def analyze_news(self, news_list: List[AnalyzedNewsItem]) -> List[AnalyzedNewsItem]:
        """批量分析新闻列表"""
        if not self.client:
            logger.warning("LLM 客户端未初始化，返回原始新闻")
            return news_list

        analyzed_list = []
        total = len(news_list)

        for i, news in enumerate(news_list, 1):
            logger.info(f"分析新闻 {i}/{total}: {news.title[:30]}...")
            try:
                analyzed = self._analyze_single_news(news)
                analyzed_list.append(analyzed)
            except Exception as e:
                logger.error(f"分析新闻失败: {e}")
                analyzed_list.append(news)

        return analyzed_list

    def _analyze_single_news(self, news: AnalyzedNewsItem) -> AnalyzedNewsItem:
        """分析单条新闻"""
        prompt = self._build_analysis_prompt(news)

        response = self.client.chat.completions.create(
            model=self.model,
            messages=[
                {"role": "system", "content": self._get_system_prompt()},
                {"role": "user", "content": prompt}
            ],
            temperature=0.3,
            max_tokens=1500
        )

        result = response.choices[0].message.content

        # 解析 JSON 结果
        try:
            # 提取 JSON 块
            json_match = re.search(r'```json\s*(.*?)\s*```', result, re.DOTALL)
            if json_match:
                result_json = json.loads(json_match.group(1))
            else:
                # 尝试直接解析
                result_json = json.loads(result)

            # 更新新闻对象
            news.catalyst_score = float(result_json.get("catalyst_score", 0))
            news.ferment_potential = result_json.get("ferment_potential", "低")
            news.worth_betting = result_json.get("worth_betting", False)
            news.analysis_reason = result_json.get("reason", "")
            news.risk_warning = result_json.get("risk_warning", "")

            # 解析相关股票
            related = result_json.get("related_stocks", [])
            if related:
                news.related_stocks = related

            # 提取各维度得分（从分析原因中提取）
            news.authority_score = self._extract_authority_score(news.analysis_reason)
            news.novelty_score = self._extract_novelty_score(news.analysis_reason)
            news.granularity_score = self._extract_granularity_score(news.analysis_reason)
            news.capacity_score = self._extract_capacity_score(news.analysis_reason)

        except Exception as e:
            logger.warning(f"解析 LLM 结果失败: {e}, 结果: {result[:200]}")

        return news

    def _get_system_prompt(self) -> str:
        """获取系统提示词"""
        return """你是一位资深 A 股短线交易员，擅长评估新闻的"催化潜力"。

你的任务是根据给定的评估维度，对新闻进行量化评分，输出 JSON 格式的分析结果。

## 评估维度说明

1. 时效性（0-1.5分）：新闻距离开盘的时间间隔
2. 确定性（0-2分）：消息是否确凿、来源权威
3. 市场认知（0-1.5分）：是否超预期，有无预期差
4. 传导路径（0-1.5分）：对A股的传导逻辑是否清晰
5. 资金关注（0-1分）：是否吸引大资金关注
6. 权威性（0-1.5分）：
   - 顶层设计（国常会、政治局、央行）：1.5分
   - 部委级（工信部、发改委）：1.0分
   - 地方政策/协会：0.5分
   - 媒体猜测：0分
7. 新颖度（0-0.5分）：
   - "首次提及"、0→1突破：0.5分
   - 超预期：0.3分
   - 炒冷饭、再次强调：0分
8. 颗粒度（0-0.3分）：
   - 明确量化目标（如"建成X个"）：0.3分
   - 具体执行指标：0.2分
   - 宏观务虚：0分
9. 资金容纳度（0-0.2分）：
   - 有3-5只以上逻辑硬的对标标的：0.2分
   - 2-3只标的：0.1分
   - 独苗题材：0分

## 判断标准

- 催化指数 ≥ 7分：次日大概率发酵，可重点博弈
- 催化指数 5-7分：可能发酵，需看竞价强度
- 催化指数 < 5分：见光死概率大，回避

## 输出格式

必须输出 JSON 格式：

```json
{
  "catalyst_score": 7.5,
  "ferment_potential": "高",
  "worth_betting": true,
  "reason": "简要说明判断依据（重点说明权威性、新颖度、颗粒度）",
  "related_stocks": ["股票1", "股票2", "股票3"],
  "risk_warning": "风险提示（如独苗、已涨过等）"
}
```

## 注意事项

1. 必须严格按维度评分，计算总分
2. ferment_potential 只能是：高、中、低
3. 相关股票给出3-5只核心标的
4. 理由要简洁，100字以内"""

    def _build_analysis_prompt(self, news: AnalyzedNewsItem) -> str:
        """构建分析提示词"""
        return f"""请评估以下新闻的"催化潜力"：

【新闻信息】
标题：{news.title}
来源：{news.source}
时间：{news.time}
内容：{news.content if news.content else news.title}

请按评估维度进行评分，输出 JSON 格式的分析结果。"""

    def _extract_authority_score(self, reason: str) -> float:
        """从分析原因中提取权威性得分"""
        if "顶层设计" in reason or "国常会" in reason or "政治局" in reason:
            return 1.5
        elif "部委" in reason or "工信部" in reason or "发改委" in reason:
            return 1.0
        elif "地方" in reason or "协会" in reason:
            return 0.5
        return 0.0

    def _extract_novelty_score(self, reason: str) -> float:
        """从分析原因中提取新颖度得分"""
        if "首次" in reason or "突破" in reason or "0→1" in reason:
            return 0.5
        elif "超预期" in reason:
            return 0.3
        return 0.0

    def _extract_granularity_score(self, reason: str) -> float:
        """从分析原因中提取颗粒度得分"""
        if "明确" in reason and ("目标" in reason or "数字" in reason or "量化" in reason):
            return 0.3
        elif "指标" in reason or "具体" in reason:
            return 0.2
        return 0.0

    def _extract_capacity_score(self, reason: str) -> float:
        """从分析原因中提取资金容纳度得分"""
        if "多标的" in reason or "3-5只" in reason or "板块效应" in reason:
            return 0.2
        elif "2-3只" in reason:
            return 0.1
        return 0.0


class TopicClusterer:
    """题材聚类器 - 将新闻按题材归类并评估题材强度"""

    def __init__(self, llm_analyzer: Optional[NewsAnalyzer] = None):
        self.llm_analyzer = llm_analyzer

    def cluster_news(self, news_list: List[AnalyzedNewsItem]) -> List[TopicCluster]:
        """对新闻进行题材聚类"""
        # 使用 LLM 进行题材聚类
        if self.llm_analyzer and self.llm_analyzer.client:
            return self._llm_cluster(news_list)
        else:
            return self._simple_cluster(news_list)

    def _llm_cluster(self, news_list: List[AnalyzedNewsItem]) -> List[TopicCluster]:
        """使用 LLM 进行题材聚类"""
        # 提取所有新闻标题
        news_titles = [f"{i+1}. {n.title}" for i, n in enumerate(news_list)]
        titles_text = "\n".join(news_titles)

        prompt = f"""请将以下新闻按题材归类，输出 JSON 格式：

【新闻列表】
{titles_text}

【输出格式】
```json
{{
  "topics": [
    {{
      "name": "题材名称",
      "keywords": ["关键词1", "关键词2"],
      "news_indices": [1, 3, 5]
    }}
  ]
}}
```

要求：
1. 题材名称简洁（2-6字）
2. 每个题材包含相关的新闻序号（从1开始）
3. 重要题材可以包含多条新闻，次要题材可以只有1条"""

        try:
            response = self.llm_analyzer.client.chat.completions.create(
                model=self.llm_analyzer.model,
                messages=[
                    {"role": "system", "content": "你是一位财经新闻分析师，擅长题材归类。"},
                    {"role": "user", "content": prompt}
                ],
                temperature=0.3,
                max_tokens=1500
            )

            result = response.choices[0].message.content

            # 解析 JSON
            json_match = re.search(r'```json\s*(.*?)\s*```', result, re.DOTALL)
            if json_match:
                result_json = json.loads(json_match.group(1))
            else:
                result_json = json.loads(result)

            # 构建题材聚类
            clusters = []
            for topic_data in result_json.get("topics", []):
                cluster = TopicCluster(
                    name=topic_data.get("name", "其他"),
                    keywords=topic_data.get("keywords", []),
                )

                # 关联新闻
                indices = topic_data.get("news_indices", [])
                for idx in indices:
                    if 1 <= idx <= len(news_list):
                        news_item = news_list[idx - 1]
                        news_item.topic = cluster.name
                        cluster.news_list.append(news_item)

                if cluster.news_list:
                    clusters.append(cluster)

            return clusters

        except Exception as e:
            logger.error(f"LLM 聚类失败: {e}")
            return self._simple_cluster(news_list)

    def _simple_cluster(self, news_list: List[AnalyzedNewsItem]) -> List[TopicCluster]:
        """简单的关键词聚类（LLM 不可用时使用）"""
        # 预定义题材关键词
        topic_keywords = {
            "固态电池": ["固态电池", "固态", "硫化物", "氧化物", "电解质"],
            "低空经济": ["低空", "eVTOL", "飞行汽车", "通航", "无人机"],
            "AI算力": ["AI", "算力", "智算", "数据中心", "GPU", "服务器"],
            "半导体": ["半导体", "芯片", "光刻", "晶圆", "封测"],
            "机器人": ["机器人", "人形机器人", "减速器", "伺服"],
            "新能源": ["新能源", "光伏", "储能", "风电", "锂电"],
            "医药": ["医药", "创新药", "CRO", "疫苗", "医疗"],
            "消费": ["消费", "白酒", "食品", "零售", "餐饮"],
            "地产": ["地产", "房地产", "房企", "物业", "基建"],
            "金融": ["银行", "券商", "保险", "金融科技"],
        }

        clusters = {name: TopicCluster(name=name, keywords=kws)
                   for name, kws in topic_keywords.items()}
        clusters["其他"] = TopicCluster(name="其他", keywords=[])

        # 将新闻归类
        for news in news_list:
            matched = False
            for topic_name, keywords in topic_keywords.items():
                if any(kw in news.title for kw in keywords):
                    news.topic = topic_name
                    clusters[topic_name].news_list.append(news)
                    matched = True
                    break

            if not matched:
                news.topic = "其他"
                clusters["其他"].news_list.append(news)

        # 过滤掉空题材
        return [c for c in clusters.values() if c.news_list]

    def calculate_topic_strength(self, clusters: List[TopicCluster]) -> List[TopicCluster]:
        """计算题材强度"""
        for cluster in clusters:
            news_list = cluster.news_list
            if not news_list:
                continue

            # 基础统计
            cluster.news_count = len(news_list)
            scores = [n.catalyst_score for n in news_list]
            cluster.avg_catalyst_score = sum(scores) / len(scores)
            cluster.high_score_news = sum(1 for s in scores if s >= 7)

            # 计算强度指数
            # 权重：高分新闻占比 30%，平均分 25%，数量 20%，新颖度 15%，颗粒度 10%
            high_score_ratio = cluster.high_score_news / cluster.news_count

            avg_novelty = sum(n.novelty_score for n in news_list) / cluster.news_count
            avg_granularity = sum(n.granularity_score for n in news_list) / cluster.news_count

            # 时间集中度（新闻是否在相近时间发布）
            time_concentration = self._calculate_time_concentration(news_list)

            # 强度计算
            strength = (
                high_score_ratio * 3.0 +           # 高分占比权重最高
                cluster.avg_catalyst_score * 0.25 +  # 平均催化指数
                min(cluster.news_count * 0.2, 1.0) +  # 数量（最多5条满分）
                avg_novelty * 2.0 +                  # 新颖度
                avg_granularity * 2.0 +              # 颗粒度
                time_concentration * 1.0             # 时间集中度
            )

            cluster.strength_index = round(strength, 2)

        # 按强度排序
        clusters.sort(key=lambda x: x.strength_index, reverse=True)
        return clusters

    def _calculate_time_concentration(self, news_list: List[AnalyzedNewsItem]) -> float:
        """计算时间集中度（新闻发布时间的集中程度）"""
        if len(news_list) <= 1:
            return 1.0

        # 解析时间
        timestamps = []
        for news in news_list:
            try:
                # 尝试多种时间格式
                for fmt in ["%Y-%m-%d %H:%M:%S", "%Y-%m-%d %H:%M", "%H:%M:%S", "%H:%M"]:
                    try:
                        ts = datetime.strptime(news.time, fmt)
                        timestamps.append(ts.hour * 60 + ts.minute)
                        break
                    except:
                        continue
            except:
                continue

        if len(timestamps) <= 1:
            return 0.5

        # 计算时间跨度（分钟）
        time_span = max(timestamps) - min(timestamps)

        # 跨度越小越集中，满分跨度30分钟
        concentration = max(0, 1 - time_span / 120)
        return concentration

    def select_representative_news(self, cluster: TopicCluster, top_n: int = 3) -> List[AnalyzedNewsItem]:
        """从题材中选出代表性新闻"""
        if not cluster.news_list:
            return []

        # 排序策略：
        # 1. 催化指数高的优先
        # 2. 权威性高的优先
        # 3. 颗粒度高的优先

        sorted_news = sorted(
            cluster.news_list,
            key=lambda n: (
                n.catalyst_score * 0.5 +
                n.authority_score * 0.3 +
                n.granularity_score * 0.2
            ),
            reverse=True
        )

        return sorted_news[:top_n]


if __name__ == "__main__":
    # 测试
    from loguru import logger
    logger.remove()
    logger.add(lambda msg: print(msg, end=''), level="INFO")

    # 测试数据
    test_news = [
        AnalyzedNewsItem(
            title="工信部发布固态电池产业指导意见",
            source="工信部",
            time="2026-03-09 15:30",
            content="工信部发布《固态电池产业发展指导意见》，明确2025年建成10条产线，补贴标准X万元/条"
        ),
        AnalyzedNewsItem(
            title="宁德时代宣布固态电池量产时间提前",
            source="公司公告",
            time="2026-03-09 16:00",
            content="宁德时代宣布固态电池量产时间从2026年提前至2025年Q2"
        ),
        AnalyzedNewsItem(
            title="某券商固态电池产业链深度报告",
            source="券商研报",
            time="2026-03-09 17:30",
            content="测算市场空间2000亿，重点推荐5家公司"
        ),
    ]

    analyzer = NewsAnalyzer()
    if analyzer.client:
        analyzed = analyzer.analyze_news(test_news)

        for news in analyzed:
            print(f"\n标题: {news.title}")
            print(f"催化指数: {news.catalyst_score}")
            print(f"发酵潜力: {news.ferment_potential}")
            print(f"是否博弈: {news.worth_betting}")
            print(f"原因: {news.analysis_reason}")
            print(f"相关标的: {news.related_stocks}")
