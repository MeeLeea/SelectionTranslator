"""
划词翻译 - LLM 客户端
轻量封装，只负责将 messages 转发给 LLM 并返回文本响应
基于 openai SDK（智谱 API 兼容 OpenAI 格式）
"""
import os
import json
from typing import List, Dict, Optional
from openai import OpenAI


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
        """
        provider: 提供商标识（对应 llm_config.json 中的 key，或仅作显示用）
        所有连接参数均来自配置文件或环境变量，不再内置任何提供商预设：
          - api_key    : 参数 > 配置文件 api_key > 环境变量（env_key / LLM_API_KEY）
          - base_url   : 配置文件 base_url > 环境变量 LLM_BASE_URL
          - model      : 参数 > 配置文件 model > 环境变量 LLM_MODEL
        """
        self.provider = provider.lower()

        cfg = self._load_provider_config(config_file, self.provider)
        if not isinstance(cfg, dict):
            cfg = None
        env_key = cfg.get("env_key") if cfg else None

        # ---- API Key: 参数 > 配置文件 > 环境变量 ----
        self.api_key = api_key
        if not self.api_key and cfg:
            self.api_key = cfg.get("api_key")
        if not self.api_key:
            self.api_key = os.environ.get(env_key or "LLM_API_KEY")
        if not self.api_key:
            raise ValueError(
                f"未配置 {self.provider} 的 API Key\n"
                f"  方式1: 在 llm_config.json 中配置 api_key\n"
                f"  方式2: 设置环境变量 {env_key or 'LLM_API_KEY'}\n"
                f"  方式3: 初始化时传入 api_key 参数"
            )

        # ---- base_url: 配置文件 > 环境变量 ----
        self.base_url = (cfg.get("base_url") if cfg else None) \
            or os.environ.get("LLM_BASE_URL")
        if not self.base_url:
            raise ValueError(
                f"未配置 {self.provider} 的 base_url\n"
                f"  方式1: 在 llm_config.json 中配置 base_url\n"
                f"  方式2: 设置环境变量 LLM_BASE_URL"
            )

        # ---- 模型名: 参数 > 配置文件 > 环境变量 ----
        self.model = model
        if not self.model and cfg:
            self.model = cfg.get("model")
        if not self.model:
            self.model = os.environ.get("LLM_MODEL")
        if not self.model:
            raise ValueError(
                f"未配置 {self.provider} 的模型名\n"
                f"  方式1: 在 llm_config.json 中配置 model\n"
                f"  方式2: 设置环境变量 LLM_MODEL\n"
                f"  方式3: 初始化时传入 model 参数"
            )

        # 显示名称（用于日志/健康检查），默认取提供商标识
        self.provider_name = (cfg.get("name") if cfg else None) or self.provider

        # 创建 OpenAI 客户端
        self.client = OpenAI(
            api_key=self.api_key,
            base_url=self.base_url,
        )

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

    def get_info(self) -> Dict[str, str]:
        """获取客户端信息"""
        return {
            "provider": self.provider,
            "provider_name": self.provider_name,
            "model": self.model,
            "base_url": self.base_url,
        }

    @staticmethod
    def _load_provider_config(config_file: str, provider: str) -> Optional[dict]:
        """从 llm_config.json 读取指定提供商的配置（无配置时返回 None）"""
        if not config_file or not os.path.exists(config_file):
            return None
        try:
            with open(config_file, "r", encoding="utf-8") as f:
                cfg = json.load(f)
        except (json.JSONDecodeError, IOError):
            return None
        if not isinstance(cfg, dict):
            return None
        return cfg.get(provider)
