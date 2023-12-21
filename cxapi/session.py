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

from .exception import HandleCaptchaError
from .schema import AccountInfo
from .utils import get_ua
from .face_detection import FaceDetectionDto

# 接口-获取验证码图片
API_CAPTCHA_IMG = "https://mooc1-api.chaoxing.com/processVerifyPng.ac"

# 接口-提交验证码并重定向至原请求
API_CAPTCHA_SUBMIT = "https://mooc1-api.chaoxing.com/html/processVerify.ac"

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
    if "Location" in resp.headers:
        return SpecialPageType.NORMAL
    if resp_url.path.endswith("/antispiderShowVerify.ac"):
        return SpecialPageType.CAPTCHA
    elif resp.headers.get("Content-Type", "").startswith("text/html"):
        html = BeautifulSoup(resp.text, "lxml")
        if e := html.select_one("body.grayBg script"):
            if re.search(
                r"var url = \S+ \+ _CP_ \+ \"/knowledge/startface",
                e.text,
            ):
                return SpecialPageType.FACE
    return SpecialPageType.NORMAL


class SessionWraper(Session):
    """requests.Session 的封装
    用于处理风控、序列化 ck 和自动重试
    """

    logger: Logger  # 日志记录器
    acc: AccountInfo  # 用户账号信息
    face_detection: FaceDetectionDto  # 人脸识别 Dto
    __cb_resolve_captcha_after: Callable[[int], None]  # 验证码识别前回调
    __cb_resolve_captcha_before: Callable[[bool, str], None]  # 验证码识别后回调
    __cb_resolve_face_after: Callable[[str], None]  # 人脸识别前回调
    __cb_resolve_face_before: Callable[[str, PathLike], None]  # 人脸识别后回调
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
        self.face_detection = FaceDetectionDto(self)

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

    def __cb_resolve_face_after(self, orig_url: str):
        """识别人脸前 默认回调
        Args:
            orig_url: 原始重定向 url
        """
        print(f"开始上传人脸 URL:{orig_url}")

    def __cb_resolve_face_before(self, object_id: str, image_path: PathLike):
        """识别人脸后 默认回调"""
        print(f"人脸提交成功：path={image_path}，objectId={object_id}")

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

    def reg_face_after(self, cb: Callable[[str], None]):
        """注册人脸识别前回调
        Args:
            cb: 回调函数
        """
        self.__cb_resolve_face_after = cb

    def reg_face_before(self, cb: Callable[[str, PathLike], None]):
        """注册人脸识别后回调
        Args:
            cb: 回调函数
        """
        self.__cb_resolve_face_before = cb

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

                # 递归重发请求
                resp = self.request(*args, **kwargs)
                return resp

            case SpecialPageType.NORMAL:
                # 正常响应
                return resp

    def __handle_anti_spider(self) -> None:
        """处理风控验证码"""
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
            status = self.__submit_captcha(captcha_code)

            self.__cb_resolve_captcha_before(status, captcha_code)
            if status is True:
                # 识别成功退出 retry
                break
            # 失败后进行 retry
            time.sleep(5.0)
        else:
            # retry 超限
            raise HandleCaptchaError

    def __handle_face_detection(self, resp: Response):
        """处理风控人脸识别
        Args:
            resp: 响应对象
        """
        orig_url = URL(resp.url)
        self.logger.info(f'开始处理人脸识别 响应url:"{orig_url}"')
        html = BeautifulSoup(resp.text, "lxml")
        js_code = html.select_one("body.grayBg script").text
        face_url = URL(re.search(r"\"/knowledge/startface\?(\S+)\"", js_code).group(0))
        class_id = face_url.query.get("clazzid")
        # 尝试从原始url中提取courseId，防止人脸识别重定向页面中不包含该courseId
        course_id = (
            face_url.query.get("courseid")
            or orig_url.query.get("courseid")
            or orig_url.query.get("courseId")
        )
        knowledge_id = face_url.query.get("knowledgeid")
        cpi = face_url.query.get("cpi")

        self.__cb_resolve_face_after(orig_url)
        time.sleep(5.0)

        # 上传并提交人脸
        self.face_detection.get_upload_token()
        object_id, face_image_path = self.face_detection.upload_face_by_puid()
        self.face_detection.submit_face_new(class_id, course_id, knowledge_id, cpi, object_id)

        self.__cb_resolve_face_before(object_id, face_image_path)
        time.sleep(5.0)

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

    def __submit_captcha(self, code: str) -> bool:
        """提交验证码
        Args:
            code: 验证码
        """
        resp = self.post(
            API_CAPTCHA_SUBMIT,
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

    def ck_clear(self) -> None:
        """清除当前会话的 ck"""
        self.cookies.clear()


__all__ = ["SessionWraper"]
