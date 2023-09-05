import time
import urllib.parse
from hashlib import md5

from logger import Logger

from ..base import TaskPointBase
from ..exception import APIError
from ..utils import get_ts

# 接口-课程章节卡片资源
API_CHAPTER_CARD_RESOURCE = "https://mooc1-api.chaoxing.com/ananas/status"

# 接口-视频播放上报
API_VIDEO_PLAYREPORT = "https://mooc1-api.chaoxing.com/multimedia/log/a"


class PointVideoDto(TaskPointBase):
    """任务点视频接口"""

    object_id: str
    fid: int
    dtoken: str
    duration: int  # 视频时长
    job_id: str
    otherInfo: str
    title: str  # 视频标题
    rt: float

    def __init__(self, object_id: str, **kwargs) -> None:
        super().__init__(**kwargs)
        self.logger = Logger("PointVideo")
        self.object_id = object_id

    def __str__(self) -> str:
        return f"PointVideo(title={self.title} duration={self.duration} objectid={self.object_id} dtoken={self.dtoken} jobid={self.job_id})"

    def parse_attachment(self) -> bool:
        """解析任务点卡片 Attachment
        Returns:
            bool: 是否需要完成
        """
        try:
            # 定位资源objectid
            for point in self.attachment["attachments"]:
                if prop := point.get("property"):
                    if prop.get("objectid") == self.object_id:
                        break
            else:
                self.logger.warning("定位任务资源失败")
                return False
            self.fid = self.attachment["defaults"]["fid"]
            if jobid := point.get("jobid"):
                self.job_id = jobid
                self.otherInfo = point["otherInfo"]
                self.rt = float(point["property"].get("rt", 0.9))
                self.logger.info("解析Attachment成功")
                return point.get("isPassed") in (False, None)  # 判断是否已完成
            # 非任务点视频不需要完成
            self.logger.info(f"不存在任务已忽略")
            return False
        except Exception:
            self.logger.error("解析Attachment失败")
            raise RuntimeError("解析视频Attachment出错")

    def fetch(self) -> bool:
        """拉取视频"""
        resp = self.session.get(
            f"{API_CHAPTER_CARD_RESOURCE}/{self.object_id}",
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
                    "jobid": self.job_id,
                    "clipTime": f"0_{self.duration}",
                    "clazzId": self.class_id,
                    "objectId": self.object_id,
                    "userid": self.session.acc.puid,
                    "isdrag": "0",
                    "enc": md5(
                        "[{}][{}][{}][{}][{}][{}][{}][{}]".format(
                            self.class_id,
                            self.session.acc.puid,
                            self.job_id,
                            self.object_id,
                            playing_time * 1000,
                            "d_yHJ!$pdA~5",
                            self.duration * 1000,
                            f"0_{self.duration}",
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
