import json
import re
from pathlib import Path
from typing import Literal

from bs4 import BeautifulSoup

from logger import Logger

from .exception import APIError, ChapterNotOpened
from .schema import QuestionModel, QuestionsExportSchema
from .session import SessionWraper

# SSR页面-客户端章节任务卡片
PAGE_MOBILE_CHAPTER_CARD = "https://mooc1-api.chaoxing.com/knowledge/cards"


class QAQDtoBase:
    """答题接口基类
    用于定义 问题-回答-查询 类的各种 trait
    """

    current_index: int  # 当前题目索引 用于迭代
    title: str  # 标题

    def __init__(self) -> None:
        self.current_index = 0

    def __iter__(self):
        self.fetch_all()  # 刷新题单缓存
        self.current_index = 0
        return self

    def __next__(self) -> tuple[int, QuestionModel]:
        """迭代返回
        Returns:
            int, QuestionModel: 题目索引 题目模型
        """
        raise NotImplemented

    def fetch(self, index: int) -> QuestionModel:
        """拉取一道题
        Args:
            index: 题目索引 从 0 开始计数
        Returns:
            QuestionModel: 题目模型
        """
        raise NotImplementedError

    def fetch_all(self) -> list[QuestionModel]:
        """拉取全部题单
        Returns:
            list[QuestionModel]: 题目模型列表 (按题号顺序排列)
        """
        raise NotImplementedError

    def submit(self, *, index: int = 0, question: QuestionModel, **kwargs) -> dict:
        """提交试题
        Args:
            index: 题目索引
            question: 题目数据模型
        """
        raise NotImplementedError

    def final_submit(self) -> dict:
        """直接交卷"""
        raise NotImplementedError

    def fallback_save(self) -> dict:
        """临时保存试题"""
        raise NotImplementedError

    def export(
        self,
        format_or_path: Literal["schema", "dict", "json"] | Path = "schema",
    ) -> QuestionsExportSchema | str | dict | None:
        """导出当前试题
        Args:
            format_or_path: 导出格式或路径
        """
        raise NotImplementedError


class TaskPointBase:
    """任务点基类"""

    logger: Logger
    session: SessionWraper
    card_index: int  # 卡片索引位置
    course_id: int
    class_id: int
    knowledge_id: int
    cpi: int

    attachment: dict

    def __init__(
        self,
        session: SessionWraper,
        card_index: int,
        course_id: int,
        class_id: int,
        knowledge_id: int,
        cpi: int,
    ) -> None:
        self.session = session
        self.card_index = card_index
        self.course_id = course_id
        self.class_id = class_id
        self.knowledge_id = knowledge_id
        self.cpi = cpi

    def fetch_attachment(self) -> None:
        """拉取任务卡片 Attachment 数据"""
        resp = self.session.get(
            PAGE_MOBILE_CHAPTER_CARD,
            params={
                "clazzid": self.class_id,
                "courseid": self.course_id,
                "knowledgeid": self.knowledge_id,
                "num": self.card_index,
                "isPhone": 1,
                "control": "true",
                "cpi": self.cpi,
            },
        )
        resp.raise_for_status()
        html = BeautifulSoup(resp.text, "lxml")

        if r := re.search(
            r"window\.AttachmentSetting *= *(?P<json>.+);",
            html.head.find("script", type="text/javascript").text,
        ):
            self.attachment = json.loads(r.group("json"))
            self.logger.debug(f"Attachment: {self.attachment}")
        else:
            if t := html.select_one("p.blankTips"):
                if t.text == "章节未开放！":
                    self.logger.error("章节未开放")
                    raise ChapterNotOpened
                else:
                    raise APIError(t.text)
            raise APIError
        self.logger.info("Attachment拉取成功")

    def parse_attachment(self) -> bool:
        """解析任务点卡片 Attachment
        Returns:
            bool: 是否需要完成
        """
        raise NotImplementedError


__all__ = ["QAQDtoBase", "TaskPointBase"]
