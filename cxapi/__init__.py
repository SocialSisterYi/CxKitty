import random
import secrets
import time
import urllib.parse
from hashlib import md5


def calc_infenc(params: dict) -> str:
    "计算infenc hash参数"
    query = urllib.parse.urlencode(params) + "&DESKey=Z(AfY@XS"
    return md5(query.encode()).hexdigest()


def get_dc() -> str:
    "获取时间戳"
    return str(int(time.time() * 1000))


def get_ua(ua_type: str) -> str:
    "获取UA"
    match ua_type:
        case "mobile":
            return f"Dalvik/2.1.0 (Linux; U; Android {random.randint(9, 12)}; MI{random.randint(10, 12)} Build/SKQ1.210216.001) (device:MI{random.randint(10, 12)}) Language/zh_CN com.chaoxing.mobile/ChaoXingStudy_3_5.1.4_android_phone_614_74 (@Kalimdor)_{secrets.token_hex(16)}"
        case "web":
            return "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/107.0.0.0 Safari/537.36 Edg/107.0.1418.35"
        case _:
            raise NotImplementedError
