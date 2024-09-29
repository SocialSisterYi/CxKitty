import random
import secrets
import time
import urllib.parse
import hashlib
from math import floor
from typing import Literal

# API 环境参数
IMEI = secrets.token_hex(16)  # 设备uuid 生成随机即可
ANDROID_VERSION = f"Android {random.randint(9, 12)}"  # 安卓版本
MODEL = f"MI{random.randint(10, 12)}"  # 设备型号
LOCALE = "zh_CN"  # 语言标识
VERSION = "6.3.9"  # 版本名
BUILD = "10824_250"  # 构建id


def inf_enc_sign(params: dict) -> dict:
    """为请求表单添加 infenc 签名
    Args:
        params: 原始请求表单参数
    Returns:
        dict: 加入签名后的表单参数
    """
    query = urllib.parse.urlencode(params) + "&DESKey=Z(AfY@XS"
    inf_enc = hashlib.md5(query.encode()).hexdigest()
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


def mobile_ua_sign(model: str, locale: str, version: str, build: str, imei: str) -> str:
    """客户端 UA 签名
    Args:
        model: 设备型号
        locale: 语言标识
        version: 版本名
        build: 构建id
        imei: 设备uuid
    Returns:
        str: schild字段签名值
    """
    return hashlib.md5(
        " ".join(
            (
                f"(schild:ipL$TkeiEmfy1gTXb2XHrdLN0a@7c^vu)",
                f"(device:{model})",
                f"Language/{locale}",
                f"com.chaoxing.mobile/ChaoXingStudy_3_{version}_android_phone_{build}",
                f"(@Kalimdor)_{imei}",
            )
        ).encode()
    ).hexdigest()


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
                    f"Dalvik/2.1.0 (Linux; U; {ANDROID_VERSION}; {MODEL} Build/SKQ1.211006.001)",
                    f"(schild:{mobile_ua_sign(MODEL, LOCALE,VERSION,BUILD,IMEI)})",
                    f"(device:{MODEL})",
                    f"Language/{LOCALE}",
                    f"com.chaoxing.mobile/ChaoXingStudy_3_{VERSION}_android_phone_{BUILD}",
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
