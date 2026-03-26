from __future__ import annotations

from abc import ABC, abstractmethod

from novel_flow.models.schemas import TrendItem


class TrendCrawler(ABC):
    @abstractmethod
    def collect(self, query: str) -> list[TrendItem]:
        raise NotImplementedError


class MockTrendCrawler(TrendCrawler):
    def collect(self, query: str) -> list[TrendItem]:
        return [
            TrendItem(
                source="zhihu",
                title="如果你突然发现伴侣其实在拿你当替身",
                summary="高互动情感讨论，关键词集中在背叛、自尊、反击、成长。",
                url="https://example.com/zhihu/mock-1",
                heat_score=95,
                topic_tags=["情感", "替身文学", "反转"],
                emotional_tags=["委屈", "克制", "觉醒"],
                conflict_tags=["身份误认", "阶层差异", "旧爱回归"],
                audience_preferences=["快节奏", "强反转", "高情绪密度"],
            ),
            TrendItem(
                source="xiaohongshu",
                title="普通女生如何逆袭进入豪门社交圈",
                summary="用户偏好成长线、资源博弈、女性互助与外冷内热男主。",
                url="https://example.com/xhs/mock-2",
                heat_score=89,
                topic_tags=["逆袭", "都市", "豪门"],
                emotional_tags=["野心", "不甘", "浪漫"],
                conflict_tags=["资源争夺", "误会", "名誉风险"],
                audience_preferences=["女主成长", "现实细节", "爽感兑现"],
            ),
            TrendItem(
                source="zhihu",
                title="婚礼当天我发现新郎另有所爱，于是我改嫁了他小叔",
                summary="典型知乎体冲突设定，读者偏好开局爆点、关系禁忌与连续打脸。",
                url="https://example.com/zhihu/mock-3",
                heat_score=97,
                topic_tags=["婚恋", "禁忌关系", "打脸"],
                emotional_tags=["震惊", "报复", "心动"],
                conflict_tags=["婚礼事故", "家族权力", "感情博弈"],
                audience_preferences=["第一章爆点", "强钩子", "高密度评论点"],
            ),
        ]
