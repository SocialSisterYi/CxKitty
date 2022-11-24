#!/bin/python3
import json
import re
import sys
import time
from pathlib import Path

import yaml
from rich.console import Console
from rich.layout import Layout
from rich.live import Live
from rich.panel import Panel
from rich.table import Table

from cxapi import ChaoXingAPI
from cxapi.chapters import ClassChapters
from cxapi.jobs.document import ChapterDocument
from cxapi.jobs.exam import ChapterExam
from cxapi.jobs.video import ChapterVideo
from searcher import JsonFileSearcher, RestAPISearcher, SqliteSearcher
from utils import (SessionModule, ck2dict, dialog_login, mask_name, mask_phone,
                   print_accinfo, save_session, sessions_load, show_logo)

try:
    import readline
except ImportError:
    ...

CONFIG = yaml.load(open('config.yml', 'r', encoding='utf8') , yaml.FullLoader)
SESSION_PATH = Path(CONFIG['sessionPath'])
console = Console(height=CONFIG['tUIMaxHeight'])

# 自动判断类型, 并实例化搜索器
if CONFIG['exam']['enable']:
    match CONFIG['searcher']['use']:
        case 'restApiSearcher':
            searcher = RestAPISearcher(
                url=CONFIG['searcher']['restApiSearcher']['url'],
                method=CONFIG['searcher']['restApiSearcher']['method'],
                req_field=CONFIG['searcher']['restApiSearcher']['req'],
                rsp_field=CONFIG['searcher']['restApiSearcher']['rsp']
            )
        case 'jsonFileSearcher':
            searcher = JsonFileSearcher(
                file_path=Path(CONFIG['searcher']['jsonFileSearcher']['path'])
            )
        case 'sqliteSearcher':
            searcher = SqliteSearcher(
                file_path=Path(CONFIG['searcher']['sqliteSearcher']['path']),
                table=CONFIG['searcher']['sqliteSearcher']['table'],
                req_field=CONFIG['searcher']['sqliteSearcher']['req'],
                rsp_field=CONFIG['searcher']['sqliteSearcher']['rsp']
            )
        case _:
            raise TypeError('不合法的搜索器类型')

def wait_for_class(tui_ctx: Layout, wait_sec: int, text: str):
    '课间等待, 防止风控'
    tui_ctx.unsplit()
    for i in range(wait_sec):
        tui_ctx.update(Panel(f'[green]{text}, 课间等待{i}/{wait_sec}s'))
        time.sleep(1.0)

def fuck_video_and_exam_mainloop(chap: ClassChapters):
    '章节课程及答题主循环'
    lay = Layout()
    lay_main = Layout(Panel('等待执行任务'), name='main')
    lay_chapter = Layout(name='chapter', size=70)
    lay.split_row(lay_main, lay_chapter)
    chap.fetch_point_status()
    with Live(lay, console=console) as live:
        for index in range(len(chap.chapters)):
            chap.render_lst2tui(lay_chapter, index)
            if chap.is_finished(index):  # 如果该章节所有任务点做完, 那么就跳过
                time.sleep(0.1)  # 解决强迫症, 故意添加延时, 为展示滚屏效果
                continue
            points = chap.fetch_points_by_index(index)  # 获取当前章节的所有任务点
            for task_point in points:
                prefetch_status = task_point.pre_fetch()  # 预拉取 视频或试题
                if not prefetch_status:
                    continue
                fetch_status = task_point.fetch()  # 拉取  视频或试题
                if not fetch_status:
                    continue
                # 开始分类讨论任务点类型
                
                # 试题类型
                if isinstance(task_point, ChapterExam):
                    if not CONFIG['exam']['enable']:  # 是否配置跳过试题
                        continue
                    task_point.mount_searcher(searcher)
                    task_point.fill_and_commit(lay_main)
                    # 开始等待
                    wait_for_class(lay_main, CONFIG['exam']['wait'], f'试题《{task_point.title}》已结束')
                
                # 视频类型
                elif isinstance(task_point, ChapterVideo):
                    if not CONFIG['video']['enable']:  # 是否配置跳过视频
                        continue
                    task_point.playing(lay_main, CONFIG['video']['speed'], CONFIG['video']['report_rate'])
                    # 开始等待
                    wait_for_class(lay_main, CONFIG['video']['wait'], f'视频《{task_point.title}》已结束')
                
                # 文档类型
                elif isinstance(task_point, ChapterDocument):
                    if not CONFIG['document']['enable']:  # 是否配置跳过文档
                        continue
                    task_point.reading(lay_main)
                    # 开始等待
                    wait_for_class(lay_main, CONFIG['document']['wait'], f'文档《{task_point.title}》已结束')
                
                # 析构任务点对象
                del task_point
                chap.fetch_point_status()  # 刷新章节任务点状态
                chap.render_lst2tui(lay_chapter, index)
        lay_main.unsplit()
        lay_main.update(Panel('[green]该课程已通过', border_style='green'))
        time.sleep(5.0)
            
def dialog_class(cx: ChaoXingAPI):
    '选择“课程”交互'
    classes = cx.fetch_classes()
    while True:
        classes.print_tb(console)
        inp = console.input('输入课程序号, 退出输入q：')
        if inp == 'q':
            sys.exit()
        elif inp.isdigit():
            # 章节
            chap = classes.fetch_chapters_by_index(int(inp))
            fuck_video_and_exam_mainloop(chap)
            sys.exit()

def dialog_select_session(sessions: list[SessionModule], api: ChaoXingAPI):
    '选择“会话”交互'
    
    def relogin(index: int):
        phone = sessions[index].phone
        passwd = sessions[index].passwd
        if passwd is not None:
            status, acc = api.login_passwd(phone, passwd)
            if status:
                console.print('[green]重新登录成功')
                console.print(acc)
                api.accinfo()
                save_session(SESSION_PATH, api, passwd)
                return True
            else:
                console.print('[red]登录失败, 清手动登录')
        else:
            console.print('[red]找不到密码, 无法重登')
    
    tb = Table('序号', '手机号', 'puid', '姓名', title='请选择欲读档的会话')
    for index, session in enumerate(sessions):
        tb.add_row(
            f'[green]{index}',
            mask_phone(session.phone) if CONFIG['maskAcc'] else session.phone,
            str(session.puid),
            mask_name(session.name) if CONFIG['maskAcc'] else session.name
        )
    console.print(tb)
    while True:
        inp = console.input('输入会话序号选择 (序号后加r重登), 留空登录新账号, 退出输入q：')
        if inp == '':
            dialog_login(console, SESSION_PATH, api)
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
                    console.print('[red]会话失效, 尝试重新登录')
                    starts = relogin(index)
                    if not starts:
                        continue
                return
            

if __name__ == '__main__':
    api = ChaoXingAPI()
    show_logo(console)
    sessions = sessions_load(SESSION_PATH)
    # 存在至少一个会话存档
    if sessions:
        # 开启多会话, 允许进行选择
        if CONFIG['multiSession']:
            dialog_select_session(sessions, api)
        # 关闭多会话, 默认加载第一个会话存档
        else:
            ck = ck2dict(sessions[0].ck)
            api.ck_load(ck)
    # 会话存档为空
    else:
        console.print('[yellow]会话存档为空, 请登录账号')
        dialog_login(console, SESSION_PATH, api)
    print_accinfo(console, api)
    try:
        dialog_class(api)
    except json.JSONDecodeError:
        console.print('[red]JSON 解析失败, 可能为账号 ck 失效, 请重新登录该账号 (序号+r)')
    except Exception as err:
        console.print_exception(show_locals=False)
        console.print('[bold red]程序运行出现错误, 请截图保存并在issiue中提交')
    except KeyboardInterrupt:
        console.print('[yellow]手动中断程序运行')
    else:
        console.print('[green]任务已完成, 程序退出')
