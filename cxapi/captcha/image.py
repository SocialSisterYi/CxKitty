import json
import re
import uuid
from enum import Enum
from hashlib import md5

import cv2
import numpy as np

from logger import Logger

from ..exception import HandleCaptchaError
from ..session import SessionWraper
from ..utils import get_ts

# 获取验证码时间戳
API_CAPTCHA_SERVER_TIME = "https://captcha.chaoxing.com/captcha/get/conf"

# 获取验证码url
API_CAPTCHA_IMAGE = "https://captcha.chaoxing.com/captcha/get/verification/image"

# 提交检查验证码
API_CAPTCHA_CHECK = "https://captcha.chaoxing.com/captcha/check/verification/result"

PATT_CALLBACK_ARGS = re.compile(r"cx_captcha_function\((\{.*\})\)")


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

    # 识别滑块y坐标高度
    cutout_image_gray = cv2.cvtColor(cutout_image, cv2.COLOR_BGR2GRAY)
    contours, _ = cv2.findContours(cutout_image_gray, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
    box = cv2.boundingRect(contours[0])
    cutout_y = box[1]

    # 裁剪部分图片 减少干扰
    cutout_image_teil = cutout_image[cutout_y + 2 : cutout_y + 44, 8:48]
    shade_image_teil = shade_image[cutout_y - 2 : cutout_y + 50]

    # 匹配滑块在底图中的位置
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


class ImageCaptchaRunEnv(Enum):
    WEB = 10
    ANDROID = 20
    IOS = 30
    MINIPROGRAM = 40


class ImageCaptchaDto:
    """图形验证码Dto"""

    logger: Logger  # 日志记录器
    session: SessionWraper

    captcha_id: str
    type: ImageCaptchaType
    version: str
    run_env: ImageCaptchaRunEnv
    referer: str

    server_time: int
    iv: str
    token: str

    def __init__(
        self,
        session: SessionWraper,
        captcha_id: str,
        type: ImageCaptchaType,
        referer: str,
        version: str = "1.1.20",
        run_env: ImageCaptchaRunEnv = ImageCaptchaRunEnv.WEB,
    ):
        """_summary_

        Args:
            session (SessionWraper): 会话对象
            captcha_id (str): 验证码captchaId
            type (ImageCaptchaType): 验证码类型
            referer (str): 验证码页面来源 url
            version (str, optional): 验证码版本. Defaults to "1.1.20".
            run_env (ImageCaptchaRunEnv, optional): 验证码设备类型. Defaults to ImageCaptchaRunEnv.WEB.
        """
        self.logger = Logger("ImageCaptchaDto")
        self.session = session
        self.captcha_id = ""
        self.captcha_id = captcha_id
        self.captcha_type = type
        self.captcha_ver = version
        self.run_env = run_env
        self.referer = referer

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
            headers={
                "Referer": self.referer,
            },
        )
        json_content = json.loads(PATT_CALLBACK_ARGS.match(resp.text).group(1))
        self.server_time = json_content["t"]
        self.logger.debug(f"获取服务器时间戳成功[I.{self.captcha_id}] t={self.server_time}")

    def _get_image_url(self) -> tuple[str, str]:
        """获取图片验证码url
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
                "referer": self.referer,
                "iv": self.iv,
                "_": get_ts(),
            },
            headers={
                "Referer": self.referer,
            },
        )
        json_content = json.loads(PATT_CALLBACK_ARGS.match(resp.text).group(1))
        self.token = json_content["token"]
        images = json_content["imageVerificationVo"]
        shade_image = images["shadeImage"]
        cutout_image = images["cutoutImage"]
        self.logger.debug(
            f"获取图像验证码url[I.{self.captcha_id}] shade={shade_image} cutout={cutout_image}"
        )
        return shade_image, cutout_image

    def get_image(self) -> tuple[bytes, bytes]:
        """获取图片验证码资源
        Returns:
            bytes: 背景图片数据
            bytes: 滑块图片数据
        """
        shade_image, cutout_image = self._get_image_url()
        shade_image_data = self.session.get(shade_image).content
        cutout_image_data = self.session.get(cutout_image).content
        return shade_image_data, cutout_image_data

    def check_image(self, coords: list) -> str:
        """提交检查验证码结果
        Args:
            coords(list): 验证码输入坐标列表
        Returns:
            str: 正确时返回验证码validate
        """
        resp = self.session.get(
            API_CAPTCHA_CHECK,
            params={
                "callback": "cx_captcha_function",
                "captchaId": self.captcha_id,
                "type": self.captcha_type.value,
                "token": self.token,
                "textClickArr": json.dumps(coords, separators=(",", ":")),
                "coordinate": "[]",
                "runEnv": self.run_env.value,
                "version": self.captcha_ver,
                "t": "a",  # isTrusted
                "iv": self.iv,
                "_": get_ts(),
            },
            headers={
                "Referer": self.referer,
            },
        )
        json_content = json.loads(PATT_CALLBACK_ARGS.match(resp.text).group(1))
        self.logger.debug(f"提交验证码结果[I.{self.captcha_id}] result:{json_content}")
        if json_content.get("result") is True:
            self.logger.info(f"图像验证码通过[I.{self.captcha_id}]")
            extra_data = json.loads(json_content["extraData"])
            return extra_data["validate"]
        else:
            self.logger.info(f"图像验证码失败[I.{self.captcha_id}]")
            raise HandleCaptchaError
