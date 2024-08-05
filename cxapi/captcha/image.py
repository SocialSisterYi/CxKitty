import json
import re
import uuid
from enum import Enum

import cv2
import numpy as np
from hashlib import md5

from logger import Logger

from ..session import SessionWraper
from ..utils import get_ts

API_CAPTCHA_SERVER_TIME = "https://captcha.chaoxing.com/captcha/get/conf"

API_CAPTCHA_IMAGE = "https://captcha.chaoxing.com/captcha/get/verification/image"

API_CAPTCHA_CHECK = "https://captcha.chaoxing.com/captcha/check/verification/result"


def fuck_slide_image_captcha(shade_image, cutout_image):
    shade_image = cv2.imdecode(np.frombuffer(shade_image, np.uint8), cv2.IMREAD_COLOR)
    cutout_image = cv2.imdecode(np.frombuffer(cutout_image, np.uint8), cv2.IMREAD_COLOR)
    # TODO: 验证码识别


class ImageCaptchaType(Enum):
    SLIDE = "slide"
    TEXT_CLICK = "textclick"
    ROTATE = "rotate"
    ICON_CLICK = "iconclick"
    OBSTACLE = "obstacle"


class ImageCaptchaDto:
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

    def _get_image_url(self, referer: str = ""):
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
        shade_image, cutout_image = self._get_image_url(referer)
        shade_image_data = self.session.get(shade_image).content
        cutout_image_data = self.session.get(cutout_image).content
        return shade_image_data, cutout_image_data
