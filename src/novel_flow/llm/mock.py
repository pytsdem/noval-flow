from __future__ import annotations

from novel_flow.llm.base import LLMClient, LLMMessage


class MockLLMClient(LLMClient):
    def generate(self, messages: list[LLMMessage], temperature: float = 0.7) -> str:
        last_prompt = messages[-1].content if messages else ""
        return (
            "化妆镜前的灯把我的脸照得过分清楚，连嘴角那点僵硬都无处可藏。"
            "直到休息室的门没有关严，我听见里面有人轻声笑，说我不过是拿来顶替白月光的合适人选。"
            "我攥紧捧花，忽然明白这场婚礼不是我的归宿，而是他们替我写好的笑话。\n\n"
            f"[mock_prompt_ref]: {last_prompt[:120]}"
        )
