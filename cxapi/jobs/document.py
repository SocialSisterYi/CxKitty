import json
import re
import time

import requests
from bs4 import BeautifulSoup
from rich.json import JSON
from rich.layout import Layout
from rich.panel import Panel

from logger import Logger

from .. import get_dc
from ..schema import AccountInfo

# SSR页面-客户端章节任务卡片
PAGE_MOBILE_CHAPTER_CARD = "https://mooc1-api.chaoxing.com/knowledge/cards"

# 接口-课程文档阅读上报
API_DOCUMENT_READINGREPORT = "https://mooc1.chaoxing.com/ananas/job/document"


class ChapterDocument:
    "章节文档"
    logger: Logger
    session: requests.Session
    acc: AccountInfo
    # 基本参数
    clazzid: int
    courseid: int
    knowledgeid: int
    card_index: int  # 卡片索引位置
    cpi: int
    # 文档参数
    objectid: str
    jobid: str
    title: str
    jtoken: str

    def __init__(
        self,
        session: requests.Session,
        acc: AccountInfo,
        clazzid: int,
        courseid: int,
        knowledgeid: int,
        card_index: int,
        objectid: str,
        cpi: int,
    ) -> None:
        self.session = session
        self.acc = acc
        self.clazzid = clazzid
        self.courseid = courseid
        self.knowledgeid = knowledgeid
        self.card_index = card_index
        self.objectid = objectid
        self.cpi = cpi
        self.logger = Logger("PointDocument")
        self.logger.set_loginfo(self.acc.phone)

    def pre_fetch(self) -> bool:
        "预拉取文档  返回是否需要完成"
        resp = self.session.get(
            PAGE_MOBILE_CHAPTER_CARD,
            params={
                "clazzid": self.clazzid,
                "courseid": self.courseid,
                "knowledgeid": self.knowledgeid,
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
                r"window\.AttachmentSetting *= *(.+?)\};",
                html.head.find("script", type="text/javascript").text,
            ):
                attachment = json.loads(r.group(1)+"}")
            else:
                raise ValueError
            self.logger.debug(f"attachment: {attachment}")
            # 定位资源objectid
            for point in attachment["attachments"]:
                if prop := point.get("property"):
                    if prop.get("objectid") == self.objectid:
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

    def fetch(self) -> bool:
        "拉取文档"
        return True  # 文档类型无需二次拉取

    def __report_reading(self):
        "上报文档阅读记录"
        resp = self.session.get(
            API_DOCUMENT_READINGREPORT,
            params={
                "jobid": self.jobid,
                "knowledgeid": self.knowledgeid,
                "courseid": self.courseid,
                "clazzid": self.clazzid,
                "jtoken": self.jtoken,
                "_dc": get_dc(),
            },
        )
        resp.raise_for_status()
        json_content = resp.json()
        self.logger.debug(f"上报 resp: {json_content}")
        return json_content

    def reading(self, tui_ctx: Layout) -> None:
        "开始模拟阅读文档"
        inspect = Layout()
        tui_ctx.split_column(Panel(f"模拟浏览：{self.title}", title="正在模拟浏览"), inspect)
        report_result = self.__report_reading()
        j = JSON.from_data(report_result, ensure_ascii=False)
        if report_result["status"]:
            inspect.update(Panel(j, title="上报成功", border_style="green"))
            self.logger.info(f"文档浏览上报成功 [{self.title}(O.{self.objectid}/J.{self.jobid})]")
        else:
            self.logger.warning(f"文档浏览上报失败 [{self.title}(O.{self.objectid}/J.{self.jobid})]")
            inspect.update(Panel(j, title="上报失败", border_style="red"))
        time.sleep(1.0)


__all__ = ["ChapterDocument"]
