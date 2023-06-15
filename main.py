#!/bin/python3
import json
import sys
import time
from pathlib import Path

from rich.align import Align
from rich.console import Console
from rich.layout import Layout
from rich.live import Live
from rich.panel import Panel
from rich.traceback import install

import config
import dialog
import searcher
from cxapi.api import ChaoXingAPI
from cxapi.chapters import ClassChapters
from cxapi.jobs.document import ChapterDocument
from cxapi.jobs.exam import ChapterExam, add_searcher
from cxapi.jobs.video import ChapterVideo
from utils import ck2dict, sessions_load

api = ChaoXingAPI()
console = Console(height=config.TUI_MAX_HEIGHT)
install(console=console, show_locals=False)

layout = Layout()
lay_left = Layout(
    Panel(
        Align.center(
            "[yellow]正在扫描章节，请稍等...",
            vertical="middle"
        )
    ), 
    name="left"
)
lay_right = Layout(name="right", size=60)
lay_chapter = Layout(name="chapter")
lay_captcha = Layout(name="captcha", size=6)

# 自动判断类型, 并实例化搜索器
if config.EXAM_EN and config.SEARCHERS:
    for searcher_conf in config.SEARCHERS:
        typename = searcher_conf["type"]
        typename = typename[0].upper() + typename[1:]
        if typename not in searcher.__all__:
            raise AttributeError(f'Searcher "{typename}" not found')
        searcher_conf.__delitem__("type")
        # 动态加载搜索器类
        add_searcher(getattr(searcher, typename)(**searcher_conf))

def wait_for_class(tui_ctx: Layout, wait_sec: int, text: str):
    "课间等待, 防止风控"
    tui_ctx.unsplit()
    for i in range(wait_sec):
        tui_ctx.update(Panel(
            Align.center(
                f"[green]{text}, 课间等待{i}/{wait_sec}s",
                vertical="middle"
            )
        ))
        time.sleep(1.0)

def on_captcha_after(times: int):
    "识别验证码开始 回调"
    if layout.get("captcha") is None:
        lay_right.split_column(lay_chapter, lay_captcha)
    lay_captcha.update(Panel(f'[yellow]正在识别验证码，第 {times} 次...', title='[red]接口风控', border_style='yellow'))

def on_captcha_before(status: bool, code: str):
    "验证码识别成功 回调"
    if status is True:
        lay_captcha.update(Panel(f'[green]验证码识别成功：[yellow]{code}[green]，提交正确', title='[red]接口风控', border_style='green'))
        time.sleep(1.0)
        lay_right.unsplit()
    else:
        lay_captcha.update(Panel(f'[red]验证码识别成功：[yellow]{code}[red]，提交错误，10S 后重试', title='[red]接口风控', border_style='red'))
        time.sleep(1.0)
        
def fuck_task_worker(chap: ClassChapters):
    "任务点处理实现"
    def _show_chapter(index: int):
        chap.set_tui_index(index)
        lay_chapter.update(Panel(chap, title=f"《{chap.name}》章节列表", border_style="blue"))
    
    layout.split_row(lay_left, lay_right)
    lay_right.update(lay_chapter)
    
    chap.fetch_point_status()
    with Live(layout, console=console) as live:
        api.session.reg_captcha_after(on_captcha_after)
        api.session.reg_captcha_before(on_captcha_before)
        
        for index in range(len(chap)):
            _show_chapter(index)
            if chap.is_finished(index):  # 如果该章节所有任务点做完, 那么就跳过
                chap.logger.info(
                    f"忽略完成任务点 "
                    f"[{chap.chapters[index].label}:{chap.chapters[index].name}(Id.{chap.chapters[index].chapter_id})]"
                )
                time.sleep(0.1)  # 解决强迫症, 故意添加延时, 为展示滚屏效果
                continue
            for task_point in chap[index]:  # 获取当前章节的所有任务点, 并遍历
                # 开始分类讨论任务点类型

                # 试题类型
                if isinstance(task_point, ChapterExam) and (config.EXAM_EN or config.EXAM['export'] is True):
                    # 预拉取任务点数据
                    if not task_point.pre_fetch():
                        continue
                    # 拉取取任务点数据
                    if not task_point.fetch():
                        continue
                    # 导出试题
                    if config.EXAM['export'] is True:
                        json_data = task_point.export('json')
                        with Path(config.EXAM['export_path']).open('a', encoding='utf8') as fp:
                            fp.write(json_data + "\n")
                    # 完成试题
                    if config.EXAM_EN:
                        task_point.fill_and_commit(lay_left, config.EXAM["fail_save"])
                        # 开始等待
                        wait_for_class(lay_left, config.EXAM_WAIT, f"试题《{task_point.title}》已结束")

                # 视频类型
                elif isinstance(task_point, ChapterVideo) and config.VIDEO_EN:
                    # 预拉取任务点数据
                    if not task_point.pre_fetch():
                        continue
                    # 拉取取任务点数据
                    if not task_point.fetch():
                        continue
                    task_point.play(lay_left, config.VIDEO["speed"], config.VIDEO["report_rate"])
                    # 开始等待
                    wait_for_class(lay_left, config.VIDEO_WAIT, f"视频《{task_point.title}》已结束")

                # 文档类型
                elif isinstance(task_point, ChapterDocument) and config.DOCUMENT_EN:
                    # 预拉取任务点数据
                    if not task_point.pre_fetch():
                        continue
                    # 拉取取任务点数据
                    if not task_point.fetch():
                        continue
                    task_point.watch(lay_left)
                    # 开始等待
                    wait_for_class(lay_left, config.DOCUMENT_WAIT, f"文档《{task_point.title}》已结束")

                chap.fetch_point_status()  # 刷新章节任务点状态
                _show_chapter(index)
        lay_left.unsplit()
        lay_left.update(
            Panel(
                Align.center(
                    "[green]该课程已通过",
                    vertical="middle"
                ),
                border_style="green"
            )
        )
        time.sleep(5.0)

if __name__ == "__main__":
    dialog.logo(console)
    acc_sessions = sessions_load()
    # 存在至少一个会话存档
    if acc_sessions:
        # 多用户, 允许进行选择
        if config.MULTI_SESS:
            dialog.select_session(console, acc_sessions, api)
        # 单用户, 默认加载第一个会话档
        else:
            ck = ck2dict(acc_sessions[0].ck)
            api.ck_load(ck)
            if not api.accinfo():
                console.print("[red]会话失效, 尝试重新登录")
                if not dialog.relogin(console, acc_sessions[0], api):
                    console.print("[red]重登失败，账号或密码错误")
                    sys.exit()
    # 会话存档为空
    else:
        console.print("[yellow]会话存档为空, 请登录账号")
        dialog.login(console, api)
    api.logger.info("-----*任务开始执行*-----")
    dialog.accinfo(console, api)
    try:
        classes = api.fetch_classes()  # 拉取该账号下所学的课程
        course_seq = dialog.select_class(console, classes)  # 进行课程选择
        for chapter in course_seq:  # 迭代返回课程章节
            fuck_task_worker(chapter)
    except Exception as err:
        console.print_exception(show_locals=False)
        api.logger.error("-----*程序运行异常退出*-----", exc_info=True)
        if isinstance(err, json.JSONDecodeError):
            console.print("[red]JSON 解析失败, 可能为账号 ck 失效, 请重新登录该账号 (序号+r)")
        else:
            console.print("[bold red]程序运行出现错误, 请截图保存并附上 log 文件在 issue 提交")
    except KeyboardInterrupt:
        api.logger.warning("-----*手动中断程序*-----")
        console.print("[yellow]手动中断程序运行")
    else:
        api.logger.info("-----*任务执行完毕, 程序退出*-----")
        console.print("[green]任务已完成, 程序退出")
