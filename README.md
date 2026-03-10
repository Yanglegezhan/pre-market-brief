# 盘前信息获取系统

每日早上 8:30 自动获取外围市场信息，使用 LLM 生成盘前分析报告，推送至飞书。

**新增：盘后新闻筛选系统** - 自动采集昨日15:00至今日09:30的盘后新闻，使用LLM多维度评估，预测次日主线题材。

## 功能

### 盘前简报模式
- 美股行情采集（道指、纳指、标普、金龙指数）
- A50 期货采集
- **美股涨幅榜前10**（含催化消息）
- **A股对标板块映射**
- **催化消息提取**（从新闻源自动匹配）
- LLM 智能分析生成报告
- 飞书推送

### 新闻筛选模式（新增）
- **时间过滤**：只采集昨日15:00至今日09:30的盘后新闻
- **多源采集**：新浪财经、东方财富、财联社、华尔街见闻
- **9维度新闻评估**：时效性、确定性、权威性、新颖度、颗粒度、资金容纳度等
- **题材聚类**：自动将新闻按题材归类
- **题材强度评估**：计算题材发酵潜力
- **TOP3 主线题材预测**：选出次日最值得关注的题材
- **博弈建议**：给出具体的博弈策略和风险提示

## 快速开始

```bash
# 1. 进入项目目录
cd 2-Projects/pre-market-brief

# 2. 安装依赖
pip install -r requirements.txt

# 3. 配置环境变量
cp .env.example .env
# 编辑 .env 填入 API Keys

# 4. 运行
python main.py

# 测试模式（不推送飞书）
python main.py --test

# 新闻筛选模式（分析次日题材）
python main.py --news-filter

# 新闻筛选测试模式
python main.py --news-filter --test
```

## 配置说明

在 `.env` 文件中配置：

```bash
# 飞书推送（必填，用于接收报告）
FEISHU_WEBHOOK=https://open.feishu.cn/open-apis/bot/v2/hook/your-webhook-url

# LLM 配置（必填，用于智能分析）
LLM_API_KEY=your-api-key
LLM_BASE_URL=https://api.openai.com/v1  # 可选，默认 OpenAI
LLM_MODEL=gpt-4o-mini  # 可选，默认 gpt-4o-mini
```

### 获取飞书 Webhook

1. 在飞书群聊中，点击右上角「设置」→「群机器人」
2. 点击「添加机器人」→ 选择「自定义机器人」
3. 复制 Webhook 地址

### 获取 LLM API Key

- OpenAI: https://platform.openai.com/api-keys
- 其他兼容服务（如 DeepSeek、智谱等）也可使用

## 项目结构

```
pre-market-brief/
├── main.py              # 主入口
├── config.yaml          # 配置文件
├── requirements.txt     # 依赖
├── .env.example         # 环境变量模板
└── src/
    ├── collector.py     # 数据采集（美股+A50+新闻）
    ├── analyzer.py      # LLM 分析（盘前简报）
    ├── news_analyzer.py # 新增：新闻筛选分析器（9维度评估）
    ├── topic_cluster.py # 新增：题材聚类与强度评估
    ├── report_generator.py # 新增：报告生成器
    └── notifier.py      # 飞书推送
```

## 报告示例

## 新闻筛选报告示例

```markdown
# 次日主线题材预测 - 2026-03-09

> 基于 LLM 多维度评估（时效性、确定性、权威性、新颖度、颗粒度等）

## 题材概览

| 排名 | 题材 | 强度 | 新闻数 | 高分新闻 | 平均催化指数 |
|------|------|------|--------|----------|--------------|
| 1 | 固态电池 | 8.5 | 7 | 4 | 7.2 |
| 2 | 低空经济 | 7.2 | 5 | 3 | 6.8 |
| 3 | AI算力 | 6.5 | 4 | 2 | 6.2 |

---

## 详细题材分析

## TOP1 题材：固态电池 [强度: 8.5] 🔥🔥🔥

**判断依据**：
- 相关新闻：7条（其中≥7分：4条）
- 平均催化指数：7.2
- 核心关键词：固态电池, 硫化物, 电解质
- 相关标的：宁德时代, 亿纬锂能, 赣锋锂业

**核心新闻**（按重要性排序）：

### 1. [催化指数: 9.0] 工信部发布固态电池产业指导意见
- **来源**：工信部
- **时间**：15:30
- **权威性**：1.5/1.5 | **新颖度**：0.5/0.5 | **颗粒度**：0.3/0.3
- **相关标的**：宁德时代, 亿纬锂能, 赣锋锂业
- **分析**：顶层设计，有明确量化目标（2025年建成10条产线）
- **是否博弈**：✅ 可博弈（高潜力）

### 2. [催化指数: 8.0] 宁德时代宣布量产时间提前
...

**题材风险提示**：
- 若宁德时代高开超5%需等待分歧

**博弈建议**：
✅ **强推** - 次日大概率发酵，可重点参与
- 优选前排标的，竞价确认强度后可打板或半路
- 若板块多股一字，可参与换手龙

---

## TOP2 题材：低空经济 [强度: 7.2] 🔥🔥
...

## 整体风险提示
- 固态电池：可能已被充分预期
- 低空经济：标的较少（3只），注意独苗风险

## 次日策略建议

### 竞价阶段
- 观察 TOP3 题材相关个股竞价强度
- 若题材内多只个股一字或高开5%以上，确认发酵

### 开盘阶段
- 优先参与强度≥8.0题材的前排标的
- 强度6.0-8.0题材需看板块联动性再决定
- 回避强度<6.0的题材
```

## 数据源

| 数据类型 | 数据源 | 状态 | 说明 |
|---------|--------|------|------|
| 美股指数 | 新浪财经 | 自动 | 实时行情 |
| A50期货 | 东方财富 | 自动 | 富时A50期指 |
| 美股涨幅榜 | akshare | 自动 | 前20美股 |
| **盘后新闻** | **新浪财经** | 自动 | 7x24财经快讯 |
| **盘后新闻** | **东方财富** | 自动 | 7x24快讯+要闻 |
| **盘后新闻** | **财联社** | 自动 | 7x24电报 |
| **盘后新闻** | **华尔街见闻** | 自动 | 全球财经 |

### 新闻时间范围

新闻筛选模式**只采集昨日15:00至今日09:30**的盘后新闻：
- **开始时间**：昨天 15:00（收盘后）
- **结束时间**：今天 09:30（开盘前）
- **自动过滤**：采集后会自动过滤不在此范围内的新闻

### 为什么只采集盘后新闻？

- **15:00-次日09:30**是A股收盘到开盘的空窗期
- 这段时间发布的新闻最可能影响次日开盘
- 盘中新闻已被市场即时反应，次日无预期差

## 评估维度说明

新闻筛选系统使用以下9个维度评估新闻催化潜力：

| 维度 | 权重 | 说明 |
|------|------|------|
| **时效性** | 15% | 新闻距离开盘的时间间隔 |
| **确定性** | 20% | 消息是否确凿，来源权威 |
| **市场认知** | 15% | 是否超预期，有无预期差 |
| **传导路径** | 15% | 对A股的传导逻辑是否清晰 |
| **资金关注** | 10% | 是否吸引大资金关注 |
| **权威性** | 15% | 国常会(1.5)>部委(1.0)>地方(0.5) |
| **新颖度** | 5% | 首次提及(0.5)>超预期(0.3)>炒冷饭(0) |
| **颗粒度** | 3% | 有具体数字目标得分更高 |
| **资金容纳度** | 2% | 3-5只以上标的得分更高 |

### 判断标准
- **催化指数 ≥ 7分**：次日大概率发酵，可重点博弈
- **催化指数 5-7分**：可能发酵，需看竞价强度
- **催化指数 < 5分**：见光死概率大，回避

## 命令行参数

```bash
# 盘前简报模式
python main.py              # 正常运行（推送飞书）
python main.py --test       # 测试模式（不推送）
python main.py --output report.md  # 指定输出文件
python main.py --verbose    # 显示详细日志

# 新闻筛选模式
python main.py --news-filter              # 分析新闻催化潜力
python main.py --news-filter --test       # 测试模式
python main.py --news-filter --output news.md  # 指定输出文件
```

## 定时任务

### GitHub Actions（推荐）

创建 `.github/workflows/pre-market.yml`:

```yaml
name: Pre-Market Brief
on:
  schedule:
    - cron: '30 0 * * 1-5'  # 北京时间 8:30（工作日）
  workflow_dispatch:

jobs:
  build:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - uses: actions/setup-python@v5
        with:
          python-version: '3.12'
      - run: pip install -r requirements.txt
      - run: python main.py
        env:
          FEISHU_WEBHOOK: ${{ secrets.FEISHU_WEBHOOK }}
          LLM_API_KEY: ${{ secrets.LLM_API_KEY }}
```

## 定时任务设置

### Windows 本地定时任务（推荐）

1. **自动设置**（推荐）
```bash
# 右键以管理员身份运行
setup-scheduled-task.bat
```

2. **手动设置**
```powershell
# 创建每天 8:30 运行的任务
schtasks /create /tn "NewsFilter-Daily" /tr "python D:\pythonProject2\2-Projects\pre-market-brief\main.py --news-filter" /sc daily /st 08:30

# 查看任务
schtasks /query /tn "NewsFilter-Daily"

# 删除任务
schtasks /delete /tn "NewsFilter-Daily" /f
```

### GitHub Actions（云端运行）

创建 `.github/workflows/news-filter.yml`（已包含在项目中）：

```yaml
name: News Filter - 盘后新闻筛选
on:
  schedule:
    # 北京时间 8:30 运行（UTC 0:30）
    - cron: '30 0 * * 1-5'
  workflow_dispatch:  # 支持手动触发

jobs:
  news-filter:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - uses: actions/setup-python@v5
        with:
          python-version: '3.11'
      - run: pip install -r requirements.txt
      - run: python main.py --news-filter
        env:
          FEISHU_WEBHOOK: ${{ secrets.FEISHU_WEBHOOK }}
          LLM_API_KEY: ${{ secrets.LLM_API_KEY }}
          LLM_BASE_URL: ${{ secrets.LLM_BASE_URL }}
          LLM_MODEL: ${{ secrets.LLM_MODEL }}
```

**配置GitHub Secrets：**
1. 进入 GitHub 仓库 Settings → Secrets and variables → Actions
2. 添加以下 secrets：
   - `FEISHU_WEBHOOK` - 飞书机器人Webhook地址
   - `LLM_API_KEY` - LLM API密钥
   - `LLM_BASE_URL` - LLM API地址（可选，默认使用Minimax）
   - `LLM_MODEL` - LLM模型名称（可选）

## 注意事项

1. **美股数据时间**: 美股收盘数据在北京时间凌晨4:00-5:00更新
2. **建议运行时间**:
   - 盘前简报：早上 8:30（A股开盘前30分钟）
   - 新闻筛选：收盘后 15:30-16:00（盘后新闻最全）
3. **API限制**: 新浪/东方财富/财联社API可能有请求频率限制
4. **网络问题**: 如果数据采集失败，会报告错误但不会使用模拟数据
5. **LLM调用**: 新闻筛选模式会对每条新闻调用LLM，注意API用量