import json
import re

from bs4 import BeautifulSoup

from logger import Logger

from ..exception import APIError
from ..schema import AccountInfo
from ..session import SessionWraper
from ..utils import get_ts

# SSR页面-客户端章节任务卡片
PAGE_MOBILE_CHAPTER_CARD = "https://mooc1-api.chaoxing.com/knowledge/cards"

# 接口-课程文档阅读上报
API_DOCUMENT_READINGREPORT = "https://mooc1.chaoxing.com/ananas/job/document"


class PointDocumentDto:
    """章节文档接口"""

    logger: Logger
    session: SessionWraper
    acc: AccountInfo
    # 基本参数
    clazz_id: int
    course_id: int
    knowledge_id: int
    card_index: int  # 卡片索引位置
    cpi: int
    # 文档参数
    object_id: str
    jobid: str
    title: str
    jtoken: str

    def __init__(
        self,
        session: SessionWraper,
        acc: AccountInfo,
        clazz_id: int,
        course_id: int,
        knowledge_id: int,
        card_index: int,
        object_id: str,
        cpi: int,
    ) -> None:
        self.logger = Logger("PointDocument")
        self.session = session
        self.acc = acc
        self.clazz_id = clazz_id
        self.course_id = course_id
        self.knowledge_id = knowledge_id
        self.card_index = card_index
        self.object_id = object_id
        self.cpi = cpi

    def __str__(self) -> str:
        return f"PointDocument(title={self.title} jobid={self.object_id} dtoken={self.jtoken})"

    def pre_fetch(self) -> bool:
        """预拉取文档
        Returns:
            bool: 是否需要完成
        """
        resp = self.session.get(
            PAGE_MOBILE_CHAPTER_CARD,
            params={
                "clazzid": self.clazz_id,
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
        try:
            if r := re.search(
                r"window\.AttachmentSetting *= *(.+?);",
                html.head.find("script", type="text/javascript").text,
            ):
                attachment = json.loads(r.group(1))
            else:
                raise ValueError
            self.logger.debug(f"attachment: {attachment}")
            # 定位资源objectid
            for point in attachment["attachments"]:
                if prop := point.get("property"):
                    if prop.get("objectid") == self.object_id:
                        break
            else:
                self.logger.warning("定位任务资源失败")
                return False
            if point.get("job") == True:  # 这里需要忽略非任务点文档
                self.title = point["property"]["name"]
                self.jobid = point["jobid"]
                self.jtoken = point["jtoken"]
                self.logger.info("预拉取成功")
                return True
            self.logger.info(f"不存在任务已忽略")
            return False  # 非任务点文档不需要完成
        except Exception:
            self.logger.error(f"预拉取失败")
            raise RuntimeError("文档预拉取出错")

    def report(self) -> dict:
        """上报文档阅读记录
        Returns:
            dict: json 响应数据
        """
        resp = self.session.get(
            API_DOCUMENT_READINGREPORT,
            params={
                "jobid": self.jobid,
                "knowledgeid": self.knowledge_id,
                "courseid": self.course_id,
                "clazzid": self.clazz_id,
                "jtoken": self.jtoken,
                "_dc": get_ts(),
            },
        )
        resp.raise_for_status()
        json_content = resp.json()
        self.logger.debug(f"上报 resp: {json_content}")
        if error := json_content.get("error"):
            self.logger.error(f"文档上报失败")
            raise APIError(error)
        self.logger.info(f"文档上报成功")
        return json_content


__all__ = ["PointDocumentDto"]
