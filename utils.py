import json
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Optional

import maskpass
from qrcode import QRCode
from rich.console import Console

from cxapi import ChaoXingAPI


def show_logo(tui_ctx: Console):
    '显示项目logo'
    tui_ctx.print("""\
[red]   ______[/][green]     __ __ _ __  __[/]
[red]  / ____/  __[/][green]/ //_/(_) /_/ /___  __[/]
[red] / /   | |/_[/][green]/ ,<  / / __/ __/ / / /[/]
[red]/ /____>  <[/][green]/ /| |/ / /_/ /_/ /_/ /[/]
[red]\\____/_/|_[/][green]/_/ |_/_/\\__/\\__/\\__, /[/]
                          [green]/____/[/]
[bold red]超星[/][red]学习通[/][green]答题姬[/]
─────────────────────────────────────""",
    highlight=False)
    

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

def save_session(session_path: Path, api: ChaoXingAPI, passwd: Optional[str]=None) -> None:
    '存档会话数据为json'
    if not session_path.is_dir():
        session_path.mkdir(parents=True)
    file_path = session_path / f'{api.phone}.json'
    with open(file_path, 'w', encoding='utf8') as fp:
        sessdata = {
            'phone': api.phone,
            'puid': api.puid,
            'passwd': passwd,
            'name': api.name,
            'ck': dict2ck(api.ck_dump())
        }
        json.dump(sessdata, fp, ensure_ascii=False)

def sessions_load(session_path: Path):
    '从路径批量读档会话'
    sessions = []
    if not session_path.is_dir():
        return []
    for file in session_path.iterdir():
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

def print_accinfo(tui_ctx: Console, api: ChaoXingAPI):
    '显示账号信息到终端'
    tui_ctx.print(f"[green]账号已登录[/] puid={api.puid} name={api.name} schools={api.schools}")

def dialog_login(tui_ctx: Console, session_path: Path, api: ChaoXingAPI):
    '密码和二维码“登录”交互'
    while True:
        uname = tui_ctx.input('[yellow]请输入手机号, 留空为二维码登录：')
        # 二维码登录
        if uname == '':
            api.qr_get()
            qr = QRCode()
            qr.add_data(api.qr_geturl())
            qr.print_ascii()  # 打印二维码到终端
            tui_ctx.print('[yellow]等待扫描')
            flag_scanned = False
            # 开始轮询二维码状态
            while True:
                qr_status = api.login_qr()
                if qr_status['status'] == True:
                    tui_ctx.print('[green]登录成功')
                    api.accinfo()
                    print_accinfo(tui_ctx, api)
                    save_session(session_path, api)
                    return
                match qr_status.get('type'):
                    case '1':
                        tui_ctx.print('[red]二维码验证错误')
                        break
                    case '2':
                        tui_ctx.print('[red]二维码已失效')
                        break
                    case '4':
                        if not flag_scanned:
                            tui_ctx.print(f"[green]二维码已扫描 name={qr_status['nickname']} puid={qr_status['uid']}")
                        flag_scanned = True
                time.sleep(1.0)
        # 手机号+密码登录
        else:
            tui_ctx.print('[yellow]请输入密码：', end='')
            passwd = maskpass.askpass('')
            status, acc = api.login_passwd(uname, passwd)
            if status:
                tui_ctx.print('[green]登录成功')
                tui_ctx.print(acc)
                api.accinfo()
                save_session(session_path, api, passwd)
                return
            else:
                tui_ctx.print('[red]登录失败')

def mask_name(name: str) -> str:
    '打码姓名'
    if len(name) <= 2:
        return name[0] + '*'
    else:
        return name[0] + '*' + name[-1]

def mask_phone(phone: str) -> str:
    '打码手机号'
    return phone[:3] + '****' + phone[-4:]

__all__ = ['save_session', 'dialog_login', 'SessionModule', 'ck2dict', 'sessions_load', 'print_accinfo', 'mask_name', 'mask_phone', 'show_logo']