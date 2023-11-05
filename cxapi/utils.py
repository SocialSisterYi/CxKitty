import random
import secrets
import time
import urllib.parse
from hashlib import md5
from math import floor
from typing import Literal

# 生成随机 IMEI 以及设备参数
IMEI = secrets.token_hex(16)
ANDROID_VERSION = f"Android {random.randint(9, 12)}"
DEVICE_VENDOR = f"MI{random.randint(10, 12)}"
APP_VERSION = "com.chaoxing.mobile/ChaoXingStudy_3_5.1.4_android_phone_614_74"


def inf_enc_sign(params: dict) -> dict:
    """为请求表单添加 infenc 校验
    Args:
        params: 原始请求表单参数
    Returns:
        dict: 加入签名后的表单参数
    """
    query = urllib.parse.urlencode(params) + "&DESKey=Z(AfY@XS"
    inf_enc = md5(query.encode()).hexdigest()
    return {
        **params,
        "inf_enc": inf_enc,
    }


def get_ts() -> str:
    """获取字符串形式当前时间戳
    Returns:
        str: 时间戳
    """
    return f"{round(time.time() * 1000)}"


def get_imei() -> str:
    """获取 IMEI
    Returns:
        str: 虚拟IMEI
    """
    return IMEI


def get_ua(ua_type: Literal["mobile", "web"]) -> str:
    """获取 UA
    Args:
        ua_type: UA类型
    Returns:
        str: UA字串
    """
    match ua_type:
        case "mobile":
            return " ".join(
                (
                    f"Dalvik/2.1.0 (Linux; U; {ANDROID_VERSION}; {DEVICE_VENDOR} Build/SKQ1.210216.001)",
                    f"(device:{DEVICE_VENDOR})",
                    f"Language/zh_CN",
                    f"{APP_VERSION}",
                    f"(@Kalimdor)_{IMEI}",
                )
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
        "_edt": f"{ts}{salt}",
    }


def remove_escape_chars(text: str) -> str:
    """移除空白字符
    Args:
        text: 输入字符串
    Returns:
        str: 输出字符串
    """
    return (
        text.replace("\xa0", " ")
        .strip()
        .replace("\u2002", "")
        .replace("\u200b", "")
        .replace("\u3000", "")
    )
