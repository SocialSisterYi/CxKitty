import re
import sys
import time

from qrcode import QRCode
from rich.console import Console
from rich.table import Table

from cxapi.api import ChaoXingAPI
from cxapi.classes import Classes
from utils import (CONF_MASKACC, SessionModule, __version__, ck2dict,
                   mask_name, mask_phone, save_session)


def logo(tui_ctx: Console) -> None:
    '显示项目logo'
    tui_ctx.print(f"""\
[red]   █████████             [/][green] █████   ████  ███   █████     █████[/]
[red]  ███░░░░░███            [/][green]░░███   ███░  ░░░   ░░███     ░░███[/]
[red] ███     ░░░  █████ █████[/][green] ░███  ███    ████  ███████   ███████   █████ ████[/]
[red]░███         ░░███ ░░███ [/][green] ░███████    ░░███ ░░░███░   ░░░███░   ░░███ ░███[/]
[red]░███          ░░░█████░  [/][green] ░███░░███    ░███   ░███      ░███     ░███ ░███[/]
[red]░░███     ███  ███░░░███ [/][green] ░███ ░░███   ░███   ░███ ███  ░███ ███ ░███ ░███[/]
[red] ░░█████████  █████ █████[/][green] █████ ░░████ █████  ░░█████   ░░█████  ░░███████[/]
[red]  ░░░░░░░░░  ░░░░░ ░░░░░ [/][green]░░░░░   ░░░░ ░░░░░    ░░░░░     ░░░░░    ░░░░░███[/]
[red]                         [/][green]                                         ███ ░███[/]
[red]                         [/][green]                                        ░░██████[/]
[red]                         [/][green]                                         ░░░░░░[/]
[bold red]超星[/][red]学习通[/][green]答题姬 Ver{__version__}[/]
[green]SocialSisterYi[/]
─────────────────────────────────────""",
    highlight=False)

def accinfo(tui_ctx: Console, api: ChaoXingAPI) -> None:
    '显示账号信息到终端'
    tui_ctx.print(f"[green]账号已登录[/] {' '.join(f'{k}={v}' for k, v in api.acc.__dict__.items())}")

def login(tui_ctx: Console, api: ChaoXingAPI):
    '交互-登录账号'
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
                    accinfo(tui_ctx, api)
                    save_session(api.ck_dump(), api.acc)
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
            passwd = tui_ctx.input('[yellow]请输入密码 (隐藏)：', password=True)
            status, result = api.login_passwd(uname, passwd)
            if status:
                tui_ctx.print('[green]登录成功')
                tui_ctx.print(result)
                api.accinfo()
                save_session(api.ck_dump(), api.acc, passwd)
                return
            else:
                tui_ctx.print('[red]登录失败')

def select_session(tui_ctx: Console, sessions: list[SessionModule], api: ChaoXingAPI):
    '交互-选择会话'
    
    def relogin(index: int):
        phone = sessions[index].phone
        passwd = sessions[index].passwd
        if passwd is not None:
            status, result = api.login_passwd(phone, passwd)
            if status:
                tui_ctx.print('[green]重新登录成功')
                tui_ctx.print(result)
                api.accinfo()
                save_session(api.ck_dump(), api.acc, passwd)
                return True
            else:
                tui_ctx.print('[red]登录失败, 清手动登录')
        else:
            tui_ctx.print('[red]找不到密码, 无法重登')
    
    tb = Table('序号', '手机号', 'puid', '姓名', title='请选择欲读档的会话')
    for index, session in enumerate(sessions):
        tb.add_row(
            f'[green]{index}',
            mask_phone(session.phone) if CONF_MASKACC else session.phone,
            str(session.puid),
            mask_name(session.name) if CONF_MASKACC else session.name
        )
    tui_ctx.print(tb)
    while True:
        inp = tui_ctx.input('输入会话序号选择 (序号后加r重登), 留空登录新账号, 退出输入q：')
        if inp == '':
            login(tui_ctx, api)
            if api.accinfo():
                return
        elif inp == 'q':
            sys.exit()
        elif r := re.match(r'^(\d+)(r?)', inp):
            index = int(r.group(1))
            if r.group(2) == 'r':
                starts = relogin(index)
                if starts:
                    return
            else:
                ck = ck2dict(sessions[index].ck)
                api.ck_load(ck)
                # 自动重登逻辑
                if not api.accinfo():
                    tui_ctx.print('[red]会话失效, 尝试重新登录')
                    starts = relogin(index)
                    if not starts:
                        continue
                return

def select_class(tui_ctx: Console, classes: Classes):
    '交互-选择课程'
    tb = Table('序号', '课程名', '老师名', '课程id', '课程状态', title='所学的课程', border_style='blue')
    for index, cla in enumerate(classes.classes):
        tb.add_row(
            f'[green]{index}', cla.name, cla.teacher_name, str(cla.courseid),
            '[red]已结课' if cla.state else '[green]进行中'
        )
    while True:
        tui_ctx.print(tb)
        inp = tui_ctx.input('请输入欲完成的课程序号, 输入q退出：')
        if inp == 'q':
            sys.exit()
        elif inp.isdigit():
            return inp
