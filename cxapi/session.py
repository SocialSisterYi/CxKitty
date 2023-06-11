import time
from typing import Callable

import cv2
import numpy as np
from ddddocr import DdddOcr
from requests.models import Response
from requests.sessions import Session

from . import get_ua
from .exception import HandleCaptchaError

# 接口-获取验证码图片
API_CAPTCHA_IMG = "https://mooc1-api.chaoxing.com/processVerifyPng.ac"

# 接口-提交验证码并重定向至原请求
API_CAPTCHA_COMMIT = "https://mooc1-api.chaoxing.com/html/processVerify.ac"

ocr = DdddOcr(show_ad=False)

def identify_captcha(captcha_img: bytes) -> str:
    "识别验证码"
    img = np.frombuffer(captcha_img, np.uint8)
    img = cv2.imdecode(img, cv2.IMREAD_GRAYSCALE)
    _, img = cv2.threshold(img, 190, 255, cv2.THRESH_BINARY)    # 二值化
    img = cv2.bitwise_not(img)                                  # 反色
    kernal = np.ones([3, 2], np.uint8)
    img = cv2.dilate(img, kernal, iterations=1)                 # 膨胀处理
    _, img_data = cv2.imencode('.png', img)
    code = ocr.classification(img_data.tostring())              # 交给 OCR 识别
    return code

class SessionWraper(Session):
    "Session 的封装，用于处理请求风控"
    __cb_resolve_captcha_after: Callable[[int], None] = None            # 验证码识别前回调
    __cb_resolve_captcha_before: Callable[[bool, str], None] = None     # 验证码识别后回调
    __captcha_max_retry: int                                            # 验证码最大重试
    
    def __init__(self, captcha_max_retry: int=6) -> None:
        super().__init__()
        # 默认使用 APP 的 UA, 因为一些接口为 APP 独占
        self.headers.update(
            {"User-Agent": get_ua("mobile"), "X-Requested-With": "com.chaoxing.mobile"}
        )
        self.__captcha_max_retry = captcha_max_retry
    
    def __cb_resolve_captcha_after(self, times: int):
        "识别验证码前 默认回调"
        print(f'正在识别验证码，第 {times} 次...')

    def __cb_resolve_captcha_before(self, status: bool, code: str):
        "识别验证码后 默认回调"
        if status is True:
            print(f'验证码识别成功：{code}，提交正确')
        else:
            print(f'验证码识别成功：{code}，提交错误，10S 后重试')
    
    def reg_captcha_after(self, cb: Callable[[int], None]):
        "注册验证码识别前回调"
        self.__cb_resolve_captcha_after = cb
    
    def reg_captcha_before(self, cb: Callable[[bool, str], None]):
        "注册验证码识别后回调"
        self.__cb_resolve_captcha_before = cb
    
    def request(self, *args, **kwargs) -> Response:
        "hook request 方法处理风控验证码"
        resp = super().request(*args, **kwargs)
        if resp.url.endswith("/antispiderShowVerify.ac"):
            self.__handle_anti_spider()
            resp = self.request(*args, **kwargs)  # 递归重发请求
        return resp
    
    def __handle_anti_spider(self):
        "处理风控沿验证码"
        for retry_times in range(self.__captcha_max_retry):
            self.__cb_resolve_captcha_after(retry_times + 1)
            
            # 这里过快可能导致 capthca 拉取识别，故延时
            time.sleep(5.0)
            captcha_img = self.__get_captcha_image()
            if captcha_img is None:
                continue
            captcha_code = identify_captcha(captcha_img)
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
        "获取验证码图片"
        resp = self.get(
            API_CAPTCHA_IMG, 
            params={'t': round(time.time() * 1000)}
        )
        if not resp.ok or resp.headers['Content-Type'] != 'image/png':
            return None
        return resp.content
    
    def __commit_captcha(self, code: str) -> bool:
        "提交验证码"
        resp = self.post(
            API_CAPTCHA_COMMIT,
            data={
                'app': 0,
                'ucode': code
            },
            allow_redirects=False   # 阻止重定向，以进一步操作
        )
        # HTTP 302 即验证正确，HTTP 202 即验证错误
        if resp.status_code == 302:
            return True
        return False
