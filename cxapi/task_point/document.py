from logger import Logger

from ..base import TaskPointBase
from ..exception import APIError
from ..utils import get_ts

# 接口-课程文档阅读上报
API_DOCUMENT_READINGREPORT = "https://mooc1.chaoxing.com/ananas/job/document"


class PointDocumentDto(TaskPointBase):
    """章节文档任务点接口"""

    object_id: str
    jobid: str
    title: str
    jtoken: str

    def __init__(self, object_id: str, **kwargs) -> None:
        super().__init__(**kwargs)
        self.logger = Logger("PointDocument")
        self.object_id = object_id

    def __str__(self) -> str:
        return f"PointDocument(title={self.title} jobid={self.object_id} dtoken={self.jtoken})"

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
            if point.get("job") == True:  # 这里需要忽略非任务点文档
                self.title = point["property"]["name"]
                self.jobid = point["jobid"]
                self.jtoken = point["jtoken"]
                self.logger.info("解析Attachment成功")
                return True
            self.logger.info(f"不存在任务已忽略")
            return False  # 非任务点文档不需要完成
        except Exception:
            self.logger.error(f"解析Attachment失败")
            raise RuntimeError("解析文档Attachment出错")

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
                "clazzid": self.class_id,
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
