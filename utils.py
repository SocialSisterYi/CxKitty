import json
from dataclasses import dataclass
from pathlib import Path
from typing import Optional

import config
from cxapi.schema import AccountInfo

__version__ = (
    Path("pyproject.toml")
    .read_text(encoding="utf8")
    .split("version = ")[1]
    .split("\n")[0]
    .strip('"')
)

@dataclass
class SessionModule:
    "会话数据模型"
    phone: str
    puid: int
    passwd: Optional[str]
    name: str
    ck: str

def dict2ck(dict_ck: dict[str, str]) -> str:
    "序列化dict形式的ck"
    return "".join(f"{k}={v};" for k, v in dict_ck.items())

def ck2dict(ck: str) -> dict[str, str]:
    "解析ck到dict"
    result = {}
    for field in ck.strip().split(";"):
        if not field:
            continue
        k, v = field.split("=")
        result[k] = v
    return result

def save_session(ck: dict, acc: AccountInfo, passwd: Optional[str] = None) -> None:
    "存档会话数据为json"
    if not config.SESSIONPATH.is_dir():
        config.SESSIONPATH.mkdir(parents=True)
    file_path = config.SESSIONPATH / f"{acc.phone}.json"
    with open(file_path, "w", encoding="utf8") as fp:
        sessdata = {
            "phone": acc.phone,
            "puid": acc.puid,
            "passwd": passwd,
            "name": acc.name,
            "ck": dict2ck(ck),
        }
        json.dump(sessdata, fp, ensure_ascii=False)

def sessions_load():
    "从路径批量读档会话"
    sessions = []
    if not config.SESSIONPATH.is_dir():
        return []
    for file in config.SESSIONPATH.iterdir():
        if file.suffix != ".json":
            continue
        with open(file, "r", encoding="utf8") as fp:
            sessdata = json.load(fp)
        sessions.append(
            SessionModule(
                phone=sessdata["phone"],
                puid=sessdata["puid"],
                passwd=sessdata.get("passwd"),
                name=sessdata["name"],
                ck=sessdata["ck"],
            )
        )
    return sessions

def mask_name(name: str) -> str:
    "打码姓名"
    return name[0] + ("*" * (len(name) - 2) + name[-1] if len(name) > 2 else "*")

def mask_phone(phone: str) -> str:
    "打码手机号"
    return phone[:3] + "****" + phone[-4:]

__all__ = [
    "save_session",
    "SessionModule",
    "ck2dict",
    "sessions_load",
    "mask_name",
    "mask_phone",
]
