import json
from dataclasses import dataclass
from pathlib import Path
from typing import Optional

import yaml
from cxapi.schema import AccountInfo

__version__ = '0.2.4'

CONF: dict = yaml.load(open('config.yml', 'r', encoding='utf8') , yaml.FullLoader)
CONF_SESSPATH = Path(CONF['sessionPath'])  # 会话存档路径
CONF_LOGPATH = Path(CONF['logPath'])  # 日志文件路径
CONF_MULTI_SESS: bool = CONF['multiSession']
CONF_TUI_MAX_HEIGHT: int = CONF['tUIMaxHeight']
CONF_MASKACC: bool = CONF['maskAcc']
CONF_EXAM: dict = CONF['exam']
CONF_VIDEO: dict = CONF['video']
CONF_DOCUMENT: dict = CONF['document']
CONF_SEARCHER: dict = CONF['searcher']

CONF_EN_EXAM: bool = CONF_EXAM['enable']
CONF_EN_VIDEO: bool = CONF_VIDEO['enable']
CONF_EN_DOCUMENT: bool = CONF_DOCUMENT['enable']

CONF_WAIT_EXAM: int = CONF_EXAM['wait']
CONF_WAIT_VIDEO: int = CONF_VIDEO['wait']
CONF_WAIT_DOCUMENT: int = CONF_DOCUMENT['wait']

@dataclass
class SessionModule:
    '会话数据模型'
    phone: str
    puid: int
    passwd: Optional[str]
    name: str
    ck: str

def dict2ck(dict_ck: dict[str, str]) -> str:
    '序列化dict形式的ck'
    return ''.join(f'{k}={v};' for k, v in dict_ck.items())

def ck2dict(ck: str) -> dict[str, str]:
    '解析ck到dict'
    result = {}
    for field in ck.strip().split(';'):
        if not field:
            continue
        k, v = field.split('=')
        result[k] = v
    return result

def save_session(ck: dict, acc: AccountInfo, passwd: Optional[str]=None) -> None:
    '存档会话数据为json'
    if not CONF_SESSPATH.is_dir():
        CONF_SESSPATH.mkdir(parents=True)
    file_path = CONF_SESSPATH / f'{acc.phone}.json'
    with open(file_path, 'w', encoding='utf8') as fp:
        sessdata = {
            'phone': acc.phone,
            'puid': acc.puid,
            'passwd': passwd,
            'name': acc.name,
            'ck': dict2ck(ck)
        }
        json.dump(sessdata, fp, ensure_ascii=False)

def sessions_load():
    '从路径批量读档会话'
    sessions = []
    if not CONF_SESSPATH.is_dir():
        return []
    for file in CONF_SESSPATH.iterdir():
        if file.suffix != '.json':
            continue
        with open(file, 'r', encoding='utf8') as fp:
            sessdata = json.load(fp)
        sessions.append(SessionModule(
            phone=sessdata['phone'],
            puid=sessdata['puid'],
            passwd=sessdata.get('passwd'),
            name=sessdata['name'],
            ck=sessdata['ck']
        ))
    return sessions

def mask_name(name: str) -> str:
    '打码姓名'
    return name[0] + '*' + (name[-1] if len(name) > 2 else '')

def mask_phone(phone: str) -> str:
    '打码手机号'
    return phone[:3] + '****' + phone[-4:]

__all__ = ['save_session', 'SessionModule', 'ck2dict', 'sessions_load', 'mask_name', 'mask_phone']