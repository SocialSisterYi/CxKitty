import random
import secrets
import time
import urllib.parse
from hashlib import md5
from math import floor

# 生成随机 IMEI
IMEI = secrets.token_hex(16)

def calc_infenc(params: dict) -> str:
    "计算 infenc hash 参数"
    query = urllib.parse.urlencode(params) + "&DESKey=Z(AfY@XS"
    return md5(query.encode()).hexdigest()

def get_ts() -> str:
    """获取字符串形式当前时间戳
    Returns:
        str: 时间戳
    """
    return str(round(time.time() * 1000))

def get_imei() -> str:
    "获取 IMEI"
    return IMEI

def get_ua(ua_type: str) -> str:
    "获取 UA"
    match ua_type:
        case "mobile":
            return (
                f"Dalvik/2.1.0 (Linux; U; Android {random.randint(9, 12)}; MI{random.randint(10, 12)} Build/SKQ1.210216.001) "
                f"(device:MI{random.randint(10, 12)}) "
                f"Language/zh_CN "
                f"com.chaoxing.mobile/ChaoXingStudy_3_5.1.4_android_phone_614_74 "
                f"(@Kalimdor)_{IMEI}"
            )
        case "web":
            return "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/107.0.0.0 Safari/537.36 Edg/107.0.1418.35"
        case _:
            raise NotImplementedError

def get_exam_signature(uid: int, qid: int, x: int, y: int):
    """计算考试提交接口签名参数组
    Args:
        uid: 用户 puid
        qid: 题目 id (可为 0)
        x: 屏幕点击坐标 X
        y: 屏幕点击坐标 Y
    Returns:
        dict: 签名参数组 pos rd value _edt
    """
    ts = get_ts()
    r1 = random.randrange(0, 9)
    r2 = random.randrange(0, 9)
    a = f"{secrets.token_hex(16)}{ts[4:]}{r1}{r2}{qid or ''}"
    temp = 0
    for ch in a:
        temp = (temp << 5) - temp + ord(ch)
    salt = f"{r1}{r2}{(0x7fffffff & temp) % 10}"
    encVal = f"{uid}"
    if qid:
        encVal += f"_{qid}"
    encVal += f"|{salt}"
    encVal2 = "".join(str(ord(c)) for c in encVal)
    b = len(encVal2) // 5
    c = int(encVal2[b] + encVal2[2 * b] + encVal2[3 * b] + encVal2[4 * b])
    d = len(encVal) // 2 + 1
    e = (c * int(encVal2[:10]) + d) % 0x7FFFFFFF
    pos = f"({x}|{y})"
    result = ""
    for ch in pos:
        temp = ord(ch) ^ floor(e / 0x7FFFFFFF * 0xFF)
        result += f"{temp:02x}"
        e = (c * e + d) % 0x7FFFFFFF

    return {
        "pos": f"{result}{secrets.token_hex(4)}",
        "rd": random.random(),
        "value": pos,
        "_edt": f"{ts}{salt}"
    }
