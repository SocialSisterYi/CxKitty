import re
import sys
import time

from qrcode import QRCode
from rich.console import Console
from rich.prompt import Prompt
from rich.styled import Styled
from rich.table import Table

import config
from cxapi.api import ChaoXingAPI
from cxapi.classes import ClassContainer
from cxapi.exam import ExamDto
from cxapi.schema import ClassExamModule, ClassStatus, ExamStatus
from utils import (
    SessionModule,
    __version__,
    ck2dict,
    mask_name,
    mask_phone,
    save_session
)


def logo(tui_ctx: Console) -> None:
    "显示项目logo"
    tui_ctx.print(
        f"""\
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
        highlight=False,
    )


def accinfo(tui_ctx: Console, api: ChaoXingAPI) -> None:
    "显示账号信息到终端"
    tui_ctx.print(
        f"[green]账号已登录[/] "
        f"puid={api.acc.puid} "
        f"姓名={api.acc.name} "
        f"性别={api.acc.sex.name} "
        f"电话={api.acc.phone} "
        f"学校={api.acc.school} "
        f"学号={api.acc.stu_id}"
    )


def login(tui_ctx: Console, api: ChaoXingAPI):
    "交互-登录账号"
    while True:
        uname = Prompt.ask("[yellow]请输入手机号, 留空为二维码登录[/]", console=tui_ctx)
        tui_ctx.print('')
        # 二维码登录
        if uname == "":
            api.qr_get()
            qr = QRCode()
            qr.add_data(api.qr_geturl())
            qr.print_ascii()  # 打印二维码到终端
            tui_ctx.print("[yellow]等待扫描")
            flag_scanned = False
            # 开始轮询二维码状态
            while True:
                qr_status = api.login_qr()
                if qr_status["status"] == True:
                    tui_ctx.print("[green]登录成功")
                    api.accinfo()
                    accinfo(tui_ctx, api)
                    save_session(api.session.ck_dump(), api.acc)
                    return
                match qr_status.get("type"):
                    case "1":
                        tui_ctx.print("[red]二维码验证错误")
                        break
                    case "2":
                        tui_ctx.print("[red]二维码已失效")
                        break
                    case "4":
                        if not flag_scanned:
                            tui_ctx.print(
                                f"[green]二维码已扫描 name={qr_status['nickname']} puid={qr_status['uid']}"
                            )
                        flag_scanned = True
                time.sleep(1.0)
        # 手机号+密码登录
        else:
            passwd = Prompt.ask("[yellow]请输入密码 (内容隐藏)", password=True, console=tui_ctx)
            tui_ctx.print('')
            status, result = api.login_passwd(uname, passwd)
            if status:
                tui_ctx.print("[green]登录成功")
                tui_ctx.print(result)
                api.accinfo()
                save_session(api.session.ck_dump(), api.acc, passwd)
                return
            else:
                tui_ctx.print("[red]登录失败")

def relogin(tui_ctx: Console, session: SessionModule, api: ChaoXingAPI):
    "重新登录账号"
    api.session.ck_clear()
    phone = session.phone
    passwd = session.passwd
    if passwd is not None:
        status, result = api.login_passwd(phone, passwd)
        if status:
            tui_ctx.print("[green]重新登录成功")
            tui_ctx.print(result)
            api.accinfo()
            save_session(api.session.ck_dump(), api.acc, passwd)
            return True
        else:
            tui_ctx.print("[red]登录失败, 请手动登录")
    else:
        tui_ctx.print("[red]找不到密码, 无法重登")

def select_session(tui_ctx: Console, sessions: list[SessionModule], api: ChaoXingAPI):
    "交互-选择会话"
    tb = Table("序号", "手机号", "puid", "姓名", title="请选择欲读档的会话")
    for index, session in enumerate(sessions):
        tb.add_row(
            f"[green]{index}",
            mask_phone(session.phone) if config.MASKACC else session.phone,
            str(session.puid),
            mask_name(session.name) if config.MASKACC else session.name,
        )
    tui_ctx.print(tb)
    while True:
        inp = Prompt.ask("输入会话序号选择 ([yellow]序号后加r重登[/]), 留空登录新账号, 退出输入 [yellow]q[/]", console=tui_ctx)
        tui_ctx.print('')
        if inp == "":
            login(tui_ctx, api)
            if api.accinfo():
                return
        elif inp == "q":
            sys.exit()
        elif r := re.match(r"^(\d+)(r?)", inp):
            index = int(r.group(1))
            if r.group(2) == "r":
                starts = relogin(tui_ctx, sessions[index], api)
                if starts:
                    return
            else:
                ck = ck2dict(sessions[index].ck)
                api.session.ck_load(ck)
                # 自动重登逻辑
                if not api.accinfo():
                    tui_ctx.print("[red]会话失效, 尝试重新登录")
                    starts = relogin(tui_ctx, sessions[index], api)
                    if not starts:
                        continue
                return

def select_class(tui_ctx: Console, classes: ClassContainer) -> str:
    "交互-选择课程"
    tb = Table("序号", "课程名", "老师名", "课程id", "课程状态", title="所学的课程", border_style="blue")
    for index, cla in enumerate(classes.classes):
        tb.add_row(
            f"[green]{index}",
            cla.name,
            cla.teacher_name,
            str(cla.course_id),
            Styled(cla.state.name, style="red" if cla.state == ClassStatus.已结课 else "green")
        )
    while True:
        tui_ctx.print(tb)
        command = Prompt.ask("请输入欲完成的课程 ([yellow]序号/名称/id[/]), 序号前加[yellow]\"EXAM|\"[/]进入考试模式, 输入 [yellow]q[/] 退出", console=tui_ctx)
        tui_ctx.print("")
        if command == "q":
            sys.exit()
        else:
            return command

def select_exam(tui_ctx: Console, exams: list[ClassExamModule], api: ChaoXingAPI) -> tuple[ExamDto, bool]:
    """交互-选择考试
    Args:
        tui_ctx: TUI ctx
        exams: 考试列表
        api: 根 API
    Return:
        ExamDto: 考试接口对象
        bool: 是否导出模式
    """
    tb = Table("序号", "考试名", "过期时间", "考试id", "考试状态", title="课程考试", border_style="blue")
    for index, exam in enumerate(exams):
        match exam.status:
            case ExamStatus.未开始:
                status_style = "red"
            case ExamStatus.未交:
                status_style = "yellow"
            case ExamStatus.已完成:
                status_style = "green"
        tb.add_row(
            f"[green]{index}",
            exam.name,
            exam.expire_time or "-",
            str(exam.exam_id),
            Styled(exam.status.name, style=status_style)
        )
    while True:
        tui_ctx.print(tb)
        command = Prompt.ask("请选择考试对应的序号（[yellow]序号前加e导出[/]）, 输入 [yellow]q[/] 退出", console=tui_ctx)
        tui_ctx.print("")
        if command == "q":
            sys.exit()
        else:
            if command[0] == "e":
                export = True
                exam_index = int(command[1:])
            else:
                export = False
                exam_index = int(command)
            exam = ExamDto(
                session=api.session,
                acc=api.acc,
                exam_id=exams[exam_index].exam_id,
                course_id=exams[exam_index].course_id,
                class_id=exams[exam_index].class_id,
                cpi=exams[exam_index].cpi,
                enc_task=exams[exam_index].enc_task
            )
            return exam, export
    