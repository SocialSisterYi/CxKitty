from os import PathLike
from pathlib import Path

import cv2
import numpy as np

from logger import Logger
from utils import get_face_path_by_puid

from .exception import APIError, FaceDetectionError
from .utils import get_ts

# 接口-获取云盘 token
API_GET_PAN_TOKEN = "https://pan-yz.chaoxing.com/api/token/uservalid"

# 接口-上传人脸图片
API_UPLOAD_FACE = "https://pan-yz.chaoxing.com/upload"

# 接口-提交人脸识别(旧)
API_FACE_SUBMIT = "https://mooc1-api.chaoxing.com/mooc-ans/knowledge/uploadInfo"

# 接口-提交人脸识别(新)
API_FACE_SUBMIT_NEW = "https://mooc1-api.chaoxing.com/mooc-ans/facephoto/clientfacecheckstatus"

# 接口-提交考试人脸识别
API_FACE_SUBMIT_EXAM = "https://mooc1-api.chaoxing.com/exam-ans/exam/phone/face-compare"


class FaceDetectionDto:
    """人脸识别Dto"""

    logger: Logger  # 日志记录器
    session: "SessionWraper"
    upload_token: str

    def __init__(self, session: "SessionWraper"):
        self.logger = Logger("FaceDetectionDto")
        self.session = session
        self.upload_token = None

    def get_upload_token(self) -> None:
        """获取云盘 token (用于上传人脸)
        Returns:
            str: 云盘 token
        """
        resp = self.session.get(API_GET_PAN_TOKEN)
        json_content = resp.json()
        if json_content.get("result") is not True:
            raise APIError
        self.upload_token = json_content["_token"]
        self.logger.debug(f"云盘token获取成功 {self.upload_token}")

    def upload_face_img(self, face_img: str | PathLike) -> str:
        """上传人脸照片
        Args:
            token: 云盘 token
            puid: 用户 puid
            face_img: 待上传的人脸图片路径
        Returns:
            str: 上传后的对象 objectId
        """
        # 随机 LSB 像素干扰，破坏 hash 风控
        face_img = cv2.imread(str(face_img))
        img_h, img_w, _ = face_img.shape
        rng = np.random.default_rng()
        for _ in range(rng.integers(0, 5)):
            face_img[
                rng.integers(0, img_h - 1),
                rng.integers(0, img_w - 1),
                rng.integers(0, 2),
            ] += rng.integers(-2, 2)
        _, face_img_data = cv2.imencode(".jpg", face_img)

        resp = self.session.post(
            API_UPLOAD_FACE,
            params={
                "uploadtype": "face",
                "_token": self.upload_token,
                "puid": self.session.acc.puid,
            },
            files={
                "file": (f"{get_ts()}.jpg", face_img_data, "image/jpeg"),
            },
        )
        json_content = resp.json()
        self.logger.debug(f"人脸上传 resp:{json_content}")
        if json_content.get("result") is not True:
            self.logger.error("人脸上传失败")
            raise APIError
        object_id = json_content["objectId"]
        url = json_content["data"]["previewUrl"]
        self.logger.info(f"人脸上传成功 I.{object_id}/U.{url}")
        return object_id

    def upload_face_by_puid(self, puid: int = None) -> tuple[str, Path]:
        """根据puid查找人脸图片并上传
        Args:
            puid: 查找目标 puid (默认为当前 Session 对应的 puid)
        """
        if puid is None:
            puid = self.session.acc.puid

        if face_image_path := get_face_path_by_puid(puid):
            self.logger.info(f'找到 puid={puid} 对应待上传人脸 "{face_image_path}"')
            object_id = self.upload_face_img(face_image_path)
        else:
            self.logger.error("未找到待上传人脸")
            raise FaceDetectionError

        return object_id, face_image_path

    def submit_face(
        self,
        class_id: str,
        course_id: str,
        knowledge_id: str,
        object_id: str,
    ) -> None:
        """提交人脸识别信息
        Args:
            class_id course_id knowledge_id: 课程信息 id
            object_id: 人脸上传 id
        """
        resp = self.session.post(
            API_FACE_SUBMIT,
            data={
                "clazzId": class_id,
                "courseId": course_id,
                "knowledgeId": knowledge_id,
                "uuid": "",
                "qrcEnc": "",
                "objectId": object_id,
            },
        )
        json_content = resp.json()
        self.logger.debug(f"人脸识别提交 resp:{json_content}")
        if json_content.get("status") is not True:
            message = json_content.get("msg")
            self.logger.error(f"人脸识别提交失败 {message}")
            raise APIError
        self.logger.info("人脸识别提交成功")

    def submit_face_new(
        self,
        class_id: str,
        course_id: str,
        knowledge_id: str,
        cpi: str,
        object_id: str,
    ) -> None:
        """提交人脸识别信息
        Args:
            class_id course_id knowledge_id: 课程信息 id
            object_id: 人脸上传 id
        """
        resp = self.session.get(
            API_FACE_SUBMIT_NEW,
            params={
                "courseId": course_id,
                "clazzId": class_id,
                "cpi": cpi,
                "chapterId": knowledge_id,
                "objectId": object_id,
                "type": 1,
            },
        )
        resp.raise_for_status()
        json_content = resp.json()
        self.logger.debug(f"人脸识别提交 new resp:{json_content}")
        if json_content.get("status") is not True:
            message = json_content.get("msg")
            self.logger.error(f"人脸识别 new 提交失败 {message}")
            raise APIError
        self.logger.info("人脸识别 new 提交成功")

    def submit_face_exam(
        self,
        exam_id: int,
        course_id: int,
        class_id: int,
        cpi: int,
        object_id: str,
    ):
        """提交考试人脸识别"""
        resp = self.session.get(
            API_FACE_SUBMIT_EXAM,
            params={
                "relationid": exam_id,
                "courseId": course_id,
                "classId": class_id,
                "currentFaceId": object_id,
                "liveDetectionStatus": 1,
                "cpi": cpi,
            },
        )
        resp.raise_for_status()
        json_content = resp.json()
        self.logger.debug(f"考试人脸识别提交 resp:{json_content}")
        if json_content.get("status") is not True:
            message = json_content.get("msg")
            self.logger.error(f"人脸识别 new 提交失败 {message}")
            raise APIError
        result = json_content["data"]
        score = result["origin"]["data"]["score"]
        hit_status = result["origin"]["data"]["hitStatus"]
        self.logger.info(f"人脸提交成功 score={score} status={hit_status} key={result['facekey']}")
        return result


__all__ = ["FaceDetectionDto"]
