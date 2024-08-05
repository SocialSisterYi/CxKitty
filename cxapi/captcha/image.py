import json
import re
import uuid
from enum import Enum
from hashlib import md5

import cv2
import numpy as np

from logger import Logger

from ..session import SessionWraper
from ..utils import get_ts

# 获取验证码时间戳
API_CAPTCHA_SERVER_TIME = "https://captcha.chaoxing.com/captcha/get/conf"

# 获取验证码url
API_CAPTCHA_IMAGE = "https://captcha.chaoxing.com/captcha/get/verification/image"

# 提交检查验证码
API_CAPTCHA_CHECK = "https://captcha.chaoxing.com/captcha/check/verification/result"


def fuck_slide_image_captcha(shade_image: bytes, cutout_image: bytes) -> int:
    """识别滑动验证码滑块位置
    Args:
        shade_image: 背景图片
        cutout_image: 滑块图片
    Returns:
        int: 滑块拼合的x坐标
    """
    shade_image = cv2.imdecode(np.frombuffer(shade_image, np.uint8), cv2.IMREAD_COLOR)
    cutout_image = cv2.imdecode(np.frombuffer(cutout_image, np.uint8), cv2.IMREAD_COLOR)

    cutout_image_gray = cv2.cvtColor(cutout_image, cv2.COLOR_BGR2GRAY)
    contours, _ = cv2.findContours(cutout_image_gray, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
    box = cv2.boundingRect(contours[0])
    cutout_y = box[1]

    cutout_image_teil = cutout_image[cutout_y + 2 : cutout_y + 44, 8:48]
    shade_image_teil = shade_image[cutout_y - 2 : cutout_y + 50]

    result = cv2.matchTemplate(shade_image_teil, cutout_image_teil, cv2.TM_CCOEFF_NORMED)
    _, _, min_loc, max_loc = cv2.minMaxLoc(result)
    loc_x, loc_y = max_loc

    return loc_x - 5


class ImageCaptchaType(Enum):
    SLIDE = "slide"
    TEXT_CLICK = "textclick"
    ROTATE = "rotate"
    ICON_CLICK = "iconclick"
    OBSTACLE = "obstacle"


class ImageCaptchaDto:
    """图形验证码Dto"""

    logger: Logger  # 日志记录器
    session: SessionWraper

    captcha_id: str
    captcha_type: ImageCaptchaType
    captcha_ver: str

    server_time: int
    iv: str
    token: str

    def __init__(
        self,
        session: SessionWraper,
        captcha_id: str,
        captcha_type: ImageCaptchaType,
        captcha_ver: str = "1.1.20",
    ):
        self.logger = Logger("ImageCaptchaDto")
        self.session = session
        self.captcha_id = ""
        self.captcha_id = captcha_id
        self.captcha_type = captcha_type
        self.captcha_ver = captcha_ver

        self.server_time = 0
        self.iv = ""
        self.token = ""

    def get_server_time(self):
        """获取验证码时间戳"""
        resp = self.session.get(
            API_CAPTCHA_SERVER_TIME,
            params={
                "callback": "cx_captcha_function",
                "captchaId": self.captcha_id,
                "_": get_ts(),
            },
        )
        json_content = json.loads(re.match(r"cx_captcha_function\((\{.*\})\)", resp.text).group(1))
        self.server_time = json_content["t"]

    def _get_image_url(self, referer: str = "") -> tuple[str, str]:
        """获取图片验证码url
        Args:
            referer: 验证码页面来源 url
        Returns:
            str: 背景图片 url
            str: 滑块图片 url
        """
        captcha_key = md5(f"{self.server_time}{uuid.uuid4()}".encode()).hexdigest()
        self.iv = md5(
            f"{self.captcha_id}{self.captcha_type.value}{get_ts()}{uuid.uuid4()}".encode()
        ).hexdigest()
        resp = self.session.get(
            API_CAPTCHA_IMAGE,
            params={
                "callback": "cx_captcha_function",
                "captchaId": self.captcha_id,
                "type": self.captcha_type.value,
                "version": self.captcha_ver,
                "captchaKey": captcha_key,
                "token": (
                    md5(
                        f"{self.server_time}{self.captcha_id}{self.captcha_type.value}{captcha_key}".encode()
                    ).hexdigest()
                    + f":{self.server_time+300000}"
                ),
                "referer": referer,
                "iv": self.iv,
                "_": get_ts(),
            },
        )
        json_content = json.loads(re.match(r"cx_captcha_function\((\{.*\})\)", resp.text).group(1))
        self.token = json_content["token"]
        images = json_content["imageVerificationVo"]
        return images["shadeImage"], images["cutoutImage"]

    def get_image(self, referer: str = "") -> tuple[bytes, bytes]:
        """获取图片验证码资源
        Args:
            referer: 验证码页面来源 url
        Returns:
            bytes: 背景图片数据
            bytes: 滑块图片数据
        """
        shade_image, cutout_image = self._get_image_url(referer)
        shade_image_data = self.session.get(shade_image).content
        cutout_image_data = self.session.get(cutout_image).content
        return shade_image_data, cutout_image_data

    def check_image(self, coords: list):
        ...
        # TODO: 验证码提交实现
