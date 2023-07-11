import json
import re
import time
import urllib.parse
from hashlib import md5

from bs4 import BeautifulSoup

from logger import Logger

from .. import get_ts
from ..schema import AccountInfo
from ..session import SessionWraper
from ..exception import APIError

# SSR页面-客户端章节任务卡片
PAGE_MOBILE_CHAPTER_CARD = "https://mooc1-api.chaoxing.com/knowledge/cards"

# 接口-课程章节卡片资源
API_CHAPTER_CARD_RESOURCE = "https://mooc1-api.chaoxing.com/ananas/status"

# 接口-视频播放上报
API_VIDEO_PLAYREPORT = "https://mooc1-api.chaoxing.com/multimedia/log/a"


class PointVideoDto:
    """任务点视频接口
    """
    logger: Logger
    session: SessionWraper
    acc: AccountInfo
    # 基本参数
    clazzid: int
    courseid: int
    knowledgeid: int
    card_index: int  # 卡片索引位置
    cpi: int
    # 视频参数
    objectid: str
    fid: int
    dtoken: str
    duration: int   # 视频时长
    jobid: str
    otherInfo: str
    title: str      # 视频标题
    rt: float

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
        self.logger = Logger("PointVideo")
        self.session = session
        self.acc = acc
        self.clazzid = clazz_id
        self.courseid = course_id
        self.knowledgeid = knowledge_id
        self.card_index = card_index
        self.objectid = object_id
        self.cpi = cpi

    def __str__(self) -> str:
        return f"PointVideo(title={self.title} duration={self.duration} objectid={self.objectid} dtoken={self.dtoken} jobid={self.jobid})"
    
    def pre_fetch(self) -> bool:
        "预拉取视频  返回是否需要完成"
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
                r"window\.AttachmentSetting *= *(.+?);",
                html.head.find("script", type="text/javascript").text,
            ):
                attachment = json.loads(r.group(1))
            else:
                raise ValueError
            self.logger.debug(f"attachment: {attachment}")
            self.fid = attachment["defaults"]["fid"]
            # 定位资源objectid
            for point in attachment["attachments"]:
                if prop := point.get("property"):
                    if prop.get("objectid") == self.objectid:
                        break
            else:
                self.logger.warning("定位任务资源失败")
                return False
            if jobid := point.get("jobid"):
                self.jobid = jobid
                self.otherInfo = point["otherInfo"]
                self.rt = float(point["property"].get("rt", 0.9))
                self.logger.info("预拉取成功")
                return point.get("isPassed") in (False, None)  # 判断是否已完成
            # 非任务点视频不需要完成
            self.logger.info(f"不存在任务已忽略")
            return False
        except Exception:
            self.logger.error("预拉取失败")
            raise RuntimeError("视频预拉取出错")

    def fetch(self) -> bool:
        """拉取视频
        """
        resp = self.session.get(
            f"{API_CHAPTER_CARD_RESOURCE}/{self.objectid}",
            params={
                "k": self.fid,
                "flag": "normal",
                "_dc": get_ts(),
            },
        )
        resp.raise_for_status()
        json_content = resp.json()
        self.dtoken = json_content["dtoken"]
        self.duration = json_content["duration"]
        self.title = json_content["filename"]
        self.logger.debug(f"视频 schema: {json_content}")
        if json_content.get("status") == "success":
            self.logger.info(f"拉取成功 {self}")
            return True
        else:
            self.logger.info(f"拉取失败")
            return False
    
    def play_report(self, playing_time: int) -> dict:
        """播放进度上报
        Args:
            playing_time: 当前播放进度
        Returns:
            dict: json 响应数据
        """
        resp = self.session.get(
            f"{API_VIDEO_PLAYREPORT}/{self.cpi}/{self.dtoken}",
            params=urllib.parse.urlencode(
                query={
                    "otherInfo": self.otherInfo,
                    "playingTime": playing_time,
                    "duration": self.duration,
                    # 'akid': None,
                    "jobid": self.jobid,
                    "clipTime": f"0_{self.duration}",
                    "clazzId": self.clazzid,
                    "objectId": self.objectid,
                    "userid": self.acc.puid,
                    "isdrag": "0",
                    "enc": md5(
                        "[{}][{}][{}][{}][{}][{}][{}][{}]".format(
                            self.clazzid,
                            self.acc.puid,
                            self.jobid,
                            self.objectid,
                            playing_time * 1000,
                            "d_yHJ!$pdA~5",
                            self.duration * 1000,
                            f"0_{self.duration}"
                        ).encode()
                    ).hexdigest(),
                    "rt": self.rt,
                    "dtype": "Video",
                    "view": "pc",
                    "_t": int(time.time() * 1000),
                },
                # 这里不需要编码`&`和`=`否则报403
                safe="&=",
            ),
        )
        resp.raise_for_status()
        json_content = resp.json()
        self.logger.debug(f"上报 resp: {json_content}")
        if error := json_content.get("error"):
            self.logger.error(f"播放上报失败 {playing_time}/{self.duration}")
            raise APIError(error)
        self.logger.info(f"播放上报成功 {playing_time}/{self.duration}")
        return json_content

__all__ = ["PointVideoDto"]
