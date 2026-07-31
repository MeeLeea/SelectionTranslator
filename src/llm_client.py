"""
划词翻译 - LLM 客户端
轻量封装，只负责将 messages 转发给 LLM 并返回文本响应
基于 openai SDK（智谱 API 兼容 OpenAI 格式）
"""
import os
import json
from typing import List, Dict, Optional
from openai import OpenAI


# 提供商预设（均兼容 OpenAI API 格式）
PROVIDERS = {
    "zhipu": {
        "name": "智谱AI",
        "base_url": "https://open.bigmodel.cn/api/paas/v4/",
        "env_key": "ZHIPU_API_KEY",
        "default_model": "glm-4-flash",
    },
    "deepseek": {
        "name": "DeepSeek",
        "base_url": "https://api.deepseek.com",
        "env_key": "DEEPSEEK_API_KEY",
        "default_model": "deepseek-chat",
    },
    "qwen": {
        "name": "通义千问",
        "base_url": "https://dashscope.aliyuncs.com/compatible-mode/v1",
        "env_key": "DASHSCOPE_API_KEY",
        "default_model": "qwen-plus",
    },
    "kimi": {
        "name": "Kimi (Moonshot)",
        "base_url": "https://api.moonshot.cn/v1",
        "env_key": "MOONSHOT_API_KEY",
        "default_model": "moonshot-v1-8k",
    },
}


class LLMClient:
    """
    轻量 LLM 客户端：只做 message 转发
    不含工具调用、Agent 循环等复杂逻辑
    """

    def __init__(
        self,
        provider: str = "zhipu",
        api_key: Optional[str] = None,
        model: Optional[str] = None,
        config_file: Optional[str] = None,
    ):
        provider = provider.lower()
        if provider not in PROVIDERS:
            raise ValueError(
                f"不支持的提供商: {provider}，可选: {', '.join(PROVIDERS.keys())}"
            )

        self.provider = provider
        self.cfg = PROVIDERS[provider]

        # 获取 API Key：参数 > 配置文件 > 环境变量
        self.api_key = api_key
        if not self.api_key and config_file:
            self.api_key = self._read_config(config_file, provider, "api_key")
        if not self.api_key:
            self.api_key = os.environ.get(self.cfg["env_key"])
        if not self.api_key:
            raise ValueError(
                f"未配置 {self.cfg['name']} 的 API Key\n"
                f"  方式1: 设置环境变量 {self.cfg['env_key']}\n"
                f"  方式2: 在 llm_config.json 中配置\n"
                f"  方式3: 初始化时传入 api_key 参数"
            )

        # 获取模型名
        self.model = model
        if not self.model and config_file:
            self.model = self._read_config(config_file, provider, "model")
        if not self.model:
            self.model = self.cfg["default_model"]

        # 创建 OpenAI 客户端
        self.client = OpenAI(
            api_key=self.api_key,
            base_url=self.cfg["base_url"],
        )

    def chat(
        self,
        messages: List[Dict[str, str]],
        temperature: float = 0.3,
        max_tokens: int = 512,
    ) -> str:
        """
        转发 messages 给 LLM，返回响应文本

        Args:
            messages: [{"role": "system/user/assistant", "content": "..."}]
            temperature: 温度
            max_tokens: 最大 token

        Returns:
            LLM 响应文本
        """
        resp = self.client.chat.completions.create(
            model=self.model,
            messages=messages,
            temperature=temperature,
            max_tokens=max_tokens,
        )
        return resp.choices[0].message.content or ""

    def chat_stream(
        self,
        messages: List[Dict[str, str]],
        temperature: float = 0.3,
        max_tokens: int = 512,
    ):
        """
        流式转发 messages 给 LLM，逐 token 返回

        Args:
            messages: 同 chat()
            temperature: 温度
            max_tokens: 最大 token

        Yields:
            每个 delta 文本片段（str）
        """
        stream = self.client.chat.completions.create(
            model=self.model,
            messages=messages,
            temperature=temperature,
            max_tokens=max_tokens,
            stream=True,
        )
        for chunk in stream:
            if not chunk.choices:
                continue
            delta = chunk.choices[0].delta
            if delta and delta.content:
                yield delta.content

    def extract_json(self, text: str) -> Optional[Dict]:
        """从文本中提取 JSON 对象（容错处理）"""
        text = text.strip()
        # 去除可能的 markdown 代码块标记
        if text.startswith("```"):
            lines = text.split("\n")
            lines = [l for l in lines if not l.strip().startswith("```")]
            text = "\n".join(lines).strip()
        try:
            return json.loads(text)
        except json.JSONDecodeError:
            start = text.find("{")
            end = text.rfind("}") + 1
            if start != -1 and end > start:
                try:
                    return json.loads(text[start:end])
                except json.JSONDecodeError:
                    pass
        return None

    def get_info(self) -> Dict[str, str]:
        """获取客户端信息"""
        return {
            "provider": self.provider,
            "provider_name": self.cfg["name"],
            "model": self.model,
            "base_url": self.cfg["base_url"],
        }

    @staticmethod
    def _read_config(config_file: str, provider: str, field: str) -> Optional[str]:
        """从 llm_config.json 读取字段"""
        if not os.path.exists(config_file):
            return None
        try:
            with open(config_file, "r", encoding="utf-8") as f:
                cfg = json.load(f)
            return cfg.get(provider, {}).get(field)
        except (json.JSONDecodeError, IOError):
            return None
