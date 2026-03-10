"""
飞书推送模块
"""
import os
import requests
from loguru import logger


class FeishuNotifier:
    """飞书推送器"""

    def __init__(self, webhook: str = None):
        self.webhook = webhook or os.getenv("FEISHU_WEBHOOK", "")

    def send_report(self, content: str, title: str = "盘前简报") -> bool:
        """
        发送报告到飞书

        Args:
            content: Markdown格式内容
            title: 标题

        Returns:
            是否发送成功
        """
        if not self.webhook:
            logger.warning("未配置飞书Webhook")
            return False

        # 截断内容（飞书限制）
        if len(content) > 8000:
            content = content[:8000] + "\n\n... (内容已截断)"

        payload = {
            "msg_type": "interactive",
            "card": {
                "config": {
                    "wide_screen_mode": True
                },
                "header": {
                    "title": {
                        "tag": "plain_text",
                        "content": title
                    },
                    "template": "blue"
                },
                "elements": [
                    {
                        "tag": "div",
                        "text": {
                            "tag": "lark_md",
                            "content": content
                        }
                    }
                ]
            }
        }

        try:
            response = requests.post(
                self.webhook,
                json=payload,
                headers={"Content-Type": "application/json"},
                timeout=30
            )

            if response.status_code == 200:
                result = response.json()
                if result.get("code") == 0:
                    logger.info("飞书推送成功")
                    return True
                else:
                    logger.error(f"飞书推送失败: {result}")
                    return False
            else:
                logger.error(f"飞书推送失败: HTTP {response.status_code}")
                return False

        except Exception as e:
            logger.error(f"飞书推送异常: {e}")
            return False


def send_to_feishu(content: str, title: str = "盘前简报", webhook: str = None) -> bool:
    """
    发送消息到飞书（兼容旧接口）

    Args:
        content: Markdown格式内容
        title: 标题
        webhook: 飞书Webhook地址

    Returns:
        是否发送成功
    """
    notifier = FeishuNotifier(webhook)
    return notifier.send_report(content, title)


if __name__ == "__main__":
    # 测试推送
    test_content = """
# 盘前简报测试

## 外围市场
- 道琼斯: +0.5%
- 纳斯达克: -0.3%

## 今日关注
测试推送是否正常
"""
    send_to_feishu(test_content, "盘前简报测试")