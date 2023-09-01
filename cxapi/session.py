import re
import time
from enum import Enum, auto
from os import PathLike
from typing import Callable

import cv2
import numpy as np
import requests
import requests.utils
from bs4 import BeautifulSoup
from ddddocr import DdddOcr
from requests.models import Response
from requests.sessions import Session
from yarl import URL

from logger import Logger

from . import get_ts, get_ua
from .exception import APIError, HandleCaptchaError

# 接口-获取验证码图片
API_CAPTCHA_IMG = "https://mooc1-api.chaoxing.com/processVerifyPng.ac"

# 接口-提交验证码并重定向至原请求
API_CAPTCHA_COMMIT = "https://mooc1-api.chaoxing.com/html/processVerify.ac"

# 接口-提交人脸识别结果
API_FACE_SUBMIT_INFO = "https://mooc1-api.chaoxing.com/mooc-ans/knowledge/uploadInfo"

# 接口-获取云盘 token
API_GET_PAN_TOKEN = "https://pan-yz.chaoxing.com/api/token/uservalid"

# 接口-上传人脸图片
API_UPLOAD_FACE = "https://pan-yz.chaoxing.com/upload"

ocr = DdddOcr(show_ad=False)


class SpecialPageType(Enum):
    """特殊页类型"""

    NORMAL = auto()  # 正常
    CAPTCHA = auto()  # 人机验证码
    FACE = auto()  # 人脸识别


def identify_captcha(captcha_img: bytes) -> str:
    """验证码识别实现
    Args:
        captcha_img: 验证码图片数据 png 格式
    Returns:
        str: 识别的验证码文本
    """
    img = np.frombuffer(captcha_img, np.uint8)
    img = cv2.imdecode(img, cv2.IMREAD_GRAYSCALE)

    # 二值化
    _, img = cv2.threshold(img, 190, 255, cv2.THRESH_BINARY)

    # 反色
    img = cv2.bitwise_not(img)

    # 膨胀
    kernal = np.ones([3, 2], np.uint8)
    img = cv2.dilate(img, kernal, iterations=1)

    # 交给 OCR 识别
    _, img_data = cv2.imencode(".png", img)
    code = ocr.classification(img_data.tostring())
    return code


def get_special_type(resp: Response) -> SpecialPageType:
    """识别特殊响应页面
    Args:
        resp: 响应对象
    Returns:
        SpecialPageType: 特殊页面类型
    """
    resp_url = URL(resp.url)
    if resp_url.path.endswith("/antispiderShowVerify.ac"):
        return SpecialPageType.CAPTCHA
    elif resp.headers["Content-Type"].startswith("text/html"):
        html = BeautifulSoup(resp.text, "lxml")
        if e := html.select_one("body.grayBg script"):
            if re.search(
                r"var url = ServerHost.moocDomain \+ _CP_ \+ \"/knowledge/startface",
                e.text,
            ):
                return SpecialPageType.FACE
    return SpecialPageType.NORMAL


class SessionWraper(Session):
    """requests.Session 的封装
    用于处理风控、序列化 ck 和自动重试
    """

    logger: Logger  # 日志记录器
    __cb_resolve_captcha_after: Callable[[int], None]  # 验证码识别前回调
    __cb_resolve_captcha_before: Callable[[bool, str], None]  # 验证码识别后回调
    __cb_resolve_face_after: Callable  # 人脸识别前回调
    __cb_resolve_face_before: Callable  # 人脸识别后回调
    __captcha_max_retry: int  # 验证码最大重试
    __request_max_retry: int  # 连接最大重试
    __request_retry_cnt: int  # 连接重试计数
    __retry_delay: float  # 连接重试间隔

    def __init__(
        self,
        captcha_max_retry: int = 6,
        request_max_retry: int = 5,
        retry_delay: float = 5.0,
        **kwargs,
    ) -> None:
        """Constructor
        Args:
            captcha_max_retry: 验证码最大重试次数
            request_max_retry: 连接重试计数
            retry_delay: 连接重试间隔
        """
        self.logger = Logger("Session")
        super().__init__(**kwargs)
        # 默认使用 APP 的 UA, 因为一些接口为 APP 独占
        self.headers.update(
            {
                "User-Agent": get_ua("mobile"),
                "X-Requested-With": "com.chaoxing.mobile",
            }
        )
        self.__captcha_max_retry = captcha_max_retry
        self.__request_max_retry = request_max_retry
        self.__request_retry_cnt = 0
        self.__retry_delay = retry_delay

    def __cb_resolve_captcha_after(self, times: int):
        """识别验证码前 默认回调
        Args:
            times: 识别循环次数
        """
        print(f"正在识别验证码，第 {times} 次...")

    def __cb_resolve_captcha_before(self, status: bool, code: str):
        """识别验证码后 默认回调
        Args:
            status: 识别状态
            code: 识别的验证码
        """
        if status is True:
            print(f"验证码识别成功：{code}，提交正确")
        else:
            print(f"验证码识别成功：{code}，提交错误，10S 后重试")

    def __cb_resolve_face_after(self):
        """识别人脸前 默认回调"""
        print("开始上传人脸")

    def __cb_resolve_face_before(self):
        """识别人脸后 默认回调"""
        print("人脸提交成功")

    def reg_captcha_after(self, cb: Callable[[int], None]):
        """注册验证码识别前回调
        Args:
            cb: 回调函数
        """
        self.__cb_resolve_captcha_after = cb

    def reg_captcha_before(self, cb: Callable[[bool, str], None]):
        """注册验证码识别后回调
        Args:
            cb: 回调函数
        """
        self.__cb_resolve_captcha_before = cb

    def request(self, *args, **kwargs) -> Response:
        """ "requests.Session.request 的 hook 函数
        Args:
            *args, **kwargs: request 的原始参数
        Returns:
            Response: 响应数据
        """
        try:
            resp = super().request(*args, **kwargs)
        except requests.ConnectionError as e:
            self.__request_retry_cnt += 1
            self.logger.warning(f"连接错误 {e.__str__()}")
            time.sleep(self.__retry_delay)
            if self.__request_retry_cnt < self.__request_max_retry:
                return self.request(*args, **kwargs)
            else:
                raise
        self.__request_retry_cnt = 0
        match get_special_type(resp):
            case SpecialPageType.CAPTCHA:
                # 验证码
                self.__handle_anti_spider()
                # 递归重发请求
                resp = self.request(*args, **kwargs)
                return resp

            case SpecialPageType.FACE:
                # 人脸识别
                self.__handle_face_detection(resp)
                # TODO: 处理成功后重发

            case SpecialPageType.NORMAL:
                # 正常响应
                return resp

    def __handle_anti_spider(self) -> None:
        """处理风控沿验证码"""
        self.logger.info("开始处理验证码")
        for retry_times in range(self.__captcha_max_retry):
            self.logger.info(f"验证码处理第 {retry_times + 1} 次")
            self.__cb_resolve_captcha_after(retry_times + 1)

            # 这里过快可能导致 capthca 拉取识别，故延时
            time.sleep(5.0)
            captcha_img = self.__get_captcha_image()
            if captcha_img is None:
                continue
            captcha_code = identify_captcha(captcha_img)
            self.logger.info(f"验证码已识别 {captcha_code}")
            status = self.__commit_captcha(captcha_code)

            self.__cb_resolve_captcha_before(status, captcha_code)
            if status is True:
                # 识别成功退出 retry
                break
            # 失败后进行 retry
            time.sleep(5.0)
        else:
            # retry 超限
            raise HandleCaptchaError

    def __get_captcha_image(self) -> bytes | None:
        """获取验证码图片
        Returns:
            bytes: 验证码图片数据 png 格式
        """
        resp = self.get(API_CAPTCHA_IMG, params={"t": round(time.time() * 1000)})
        if not resp.ok or resp.headers["Content-Type"] != "image/png":
            self.logger.warning(f"验证码图片获取失败 {resp.status_code}")
            return None
        self.logger.info(f"验证码图片已获取 (大小 {len(resp.content) / 1024:.2f}KB)")
        return resp.content

    def __commit_captcha(self, code: str) -> bool:
        """提交验证码
        Args:
            code: 验证码
        """
        resp = self.post(
            API_CAPTCHA_COMMIT,
            data={
                "app": 0,
                "ucode": code,
            },
            allow_redirects=False,  # 阻止重定向，以进一步操作
        )

        # HTTP 302 即验证正确，HTTP 202 即验证错误
        if resp.status_code == 302:
            self.logger.info(f"验证码验证成功 {code}")
            return True
        self.logger.warning(f"验证码验证失败 {code}")
        return False

    def __handle_face_detection(self, resp: Response):
        """处理风控人脸识别
        Args:
            resp: 响应对象
        """
        self.logger.info("开始处理人脸识别")
        html = BeautifulSoup(resp.text, "lxml")
        js_code = html.select_one("body.grayBg script").text
        face_url = URL(re.search(r"\"/knowledge/startface\?(\S+)\"", js_code).group(0))
        class_id = face_url.query.get("clazzid")
        course_id = face_url.query.get("courseid")
        knowledge_id = face_url.query.get("knowledgeid")

        time.sleep(5.0)
        self.__cb_resolve_face_after()
        # token = self.__get_face_upload_token()

        # TODO: 上传及提交实现
        ...

    def __get_face_upload_token(self) -> str:
        """获取云盘 token (用于上传人脸)
        Returns:
            str: 云盘 token
        """
        resp = self.get(API_GET_PAN_TOKEN)
        json_content = resp.json()
        if json_content.get("result") is not True:
            raise APIError
        token = json_content["_token"]
        self.logger.debug(f"云盘token获取成功 {token}")
        return token

    def __upload_face(self, token: str, face_img: str | PathLike) -> str:
        """上传人脸照片
        Args:
            token: 云盘 token
            face_img: 待上传的人脸图片路径
        Returns:
            str: 上传后的对象 objectId
        """
        resp = self.post(
            API_UPLOAD_FACE,
            params={
                "uploadtype": "face",
                "_token": token,
            },
            files={
                "file": (f"{get_ts()}.jpg", open(face_img, "rb"), "image/jpeg"),
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

    def __submit_faceinfo(
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
        resp = self.post(
            API_FACE_SUBMIT_INFO,
            json={
                "clazzId": class_id,
                "courseId": course_id,
                "knowledgeId": knowledge_id,
                "uuid": "",
                "qrcEnc": "",
                "objectId": object_id,
            },
        )
        json_content = resp.json()
        if json_content.get("status") is not True:
            message = json_content.get("msg")
            self.logger.error(f"人脸识别提交失败 {message}")
            raise APIError
        self.logger.info("人脸识别提交成功")

    def ck_load(self, ck: dict[str, str]) -> None:
        """加载 dict 格式的 ck
        Args:
            ck: 欲导入的 key-value 格式的 Cookie
        """
        requests.utils.add_dict_to_cookiejar(self.cookies, ck)

    def ck_dump(self) -> dict[str, str]:
        """导出 dict 格式的 ck
        Returns:
            dict[str, str]: 欲导入的 key-value 格式的 Cookie
        """
        return requests.utils.dict_from_cookiejar(self.cookies)


__all__ = ["SessionWraper"]
