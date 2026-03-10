"""
盘前分析器
使用 LLM 分析市场数据并生成盘前报告
"""
import os
import json
from datetime import datetime
from typing import Dict, Optional
from loguru import logger

from openai import OpenAI
import httpx


# 预设的 base_url 配置
PROVIDER_BASE_URLS = {
    "minimax": "https://api.minimaxi.com/v1",
    "zhipu": "https://open.bigmodel.cn/api/paas/v4",
    "deepseek": "https://api.deepseek.com/v1",
    "qwen": "https://dashscope.aliyuncs.com/compatible-mode/v1",
    "kimi": "https://api.moonshot.cn/v1",
}


class LLMAnalyzer:
    """LLM 分析器"""

    def __init__(self):
        self.api_key = os.getenv("LLM_API_KEY", "")
        self.model = os.getenv("LLM_MODEL", "MiniMax-M2.5")
        self.base_url = os.getenv("LLM_BASE_URL", PROVIDER_BASE_URLS.get("minimax", "https://api.minimaxi.com/v1"))

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
        logger.info(f"LLM 客户端初始化完成: model={self.model}, base_url={self.base_url}")

    def analyze(self, market_data_text: str) -> str:
        """
        分析市场数据并生成盘前报告

        Args:
            market_data_text: 格式化的市场数据文本

        Returns:
            Markdown 格式的盘前报告
        """
        if not self.client:
            logger.warning("LLM 客户端未初始化，使用默认分析")
            return self._generate_default_report(market_data_text)

        try:
            prompt = self._build_prompt(market_data_text)

            logger.info(f"正在调用 LLM ({self.model})...")
            response = self.client.chat.completions.create(
                model=self.model,
                messages=[
                    {"role": "system", "content": self._get_system_prompt()},
                    {"role": "user", "content": prompt}
                ],
                temperature=0.7,
                max_tokens=2000
            )

            result = response.choices[0].message.content

            # 过滤掉思考过程（如果有的话）
            # 移除 <think>...</think> 或类似的思考标签
            import re
            result = re.sub(r'<think>.*?</think>', '', result, flags=re.DOTALL)
            result = re.sub(r'```thinking.*?```', '', result, flags=re.DOTALL)
            # 移除开头的分析思考文本（直到第一个 # 标题）
            lines = result.strip().split('\n')
            start_idx = 0
            for i, line in enumerate(lines):
                if line.strip().startswith('#'):
                    start_idx = i
                    break
            if start_idx > 0:
                result = '\n'.join(lines[start_idx:])

            logger.info("LLM 分析完成")
            return result.strip()

        except Exception as e:
            logger.error(f"LLM 分析失败: {e}")
            return self._generate_default_report(market_data_text)

    def _get_system_prompt(self) -> str:
        """获取系统提示词"""
        return """你是一位专业的A股短线交易员，擅长分析外围市场对A股的影响。

你的任务是根据美股收盘数据和财经新闻，生成一份简洁、实用的盘前分析报告。

## 分析要点

### 1. 外围市场整体判断
- 分析美股三大指数走势（道指、纳指、标普）
- 关注金龙指数（中概股风向标）
- 关注A50期货（A股先行指标）
- 给出整体影响判断：偏多/偏空/中性

### 2. 美股涨幅榜分析
对于涨幅前5的美股个股：
- 分析其上涨的催化消息/原因
- 识别其所属板块
- 找出A股对标板块

### 3. 美股跌幅榜分析
对于跌幅前5的美股个股：
- 分析其下跌原因
- 识别其对A股相关板块的负面影响

### 4. 今日关注题材（5个）
根据美股涨幅榜和财经新闻，推荐5个核心题材：
- **题材名称**
- **关注原因**：必须引用相关新闻标题作为依据（格式：`> 相关新闻：xxx`）
- **操作建议**：简要建议

### 5. 今日避雷题材（3个）
根据美股跌幅榜和负面新闻，列出3个需要回避的题材：
- **题材名称**
- **避雷原因**：必须引用相关新闻标题作为依据
- **风险提示**：具体风险点

## 输出格式

```markdown
# 盘前简报 - YYYY-MM-DD

## 外围市场概览
[简要描述美股整体走势及对A股影响]

## 美股涨幅榜解读

### 1. 股票名 (涨幅)
- **催化消息**: [上涨原因]
- **A股对标**: [对标板块]

## 美股跌幅榜解读

### 1. 股票名 (跌幅)
- **下跌原因**: [下跌原因]
- **A股影响**: [对A股相关板块的影响]

## 今日关注题材

### ⭐⭐⭐ 题材A
- **关注原因**: [详细说明]
  > 相关新闻：[新闻标题]
- **操作建议**: [简要建议]

### ⭐⭐ 题材B
...

## 今日避雷题材

### ⚠️ 避雷题材A
- **避雷原因**: [详细说明]
  > 相关新闻：[新闻标题]
- **风险提示**: [具体风险]

---

生成时间: HH:MM
```

## 注意事项

1. 每个题材必须引用新闻标题作为依据
2. 关注题材和避雷题材都要有明确的逻辑支撑
3. 保持客观，不过分乐观或悲观
4. 控制在800字以内（不含数据表格）"""

    def _build_prompt(self, market_data_text: str) -> str:
        """构建分析提示词"""
        today = datetime.now().strftime("%Y-%m-%d")

        return f"""请根据以下盘前数据，生成今日A股盘前分析报告：

{market_data_text}

请分析：
1. 外围市场对A股的整体影响
2. 美股涨幅前5个股的催化消息和A股对标分析
3. 美股跌幅前5个股的下跌原因和对A股的影响
4. 今日重点关注5个题材，每个题材必须引用相关新闻标题作为依据
5. 今日避雷3个题材，每个题材必须引用相关新闻标题作为依据

今天是 {today}，请直接输出 Markdown 格式的报告。"""

    def _generate_default_report(self, market_data_text: str) -> str:
        """生成默认报告（LLM不可用时）"""
        time_str = datetime.now().strftime("%H:%M")

        return f"""## 分析说明

由于 LLM 服务暂不可用，无法提供智能分析。

请根据上述数据自行判断市场走势。

---
生成时间: {time_str}
"""


if __name__ == "__main__":
    # 测试分析器
    from collector import DataCollector

    collector = DataCollector()
    data = collector.collect_all()
    market_text = collector.format_data_for_report(data)

    analyzer = LLMAnalyzer()
    report = analyzer.analyze(market_text)

    print("\n" + "="*60)
    print("盘前报告:")
    print("="*60)
    print(report)