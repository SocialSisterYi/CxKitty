class APIError(Exception):
    "接口错误"

class HandleCaptchaError(Exception):
    "处理风控验证码时错误"