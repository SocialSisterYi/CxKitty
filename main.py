#!/bin/python3
import json
import time

from rich.console import Console
from rich.layout import Layout
from rich.live import Live
from rich.panel import Panel
from rich.traceback import install

import dialog
from cxapi.api import ChaoXingAPI
from cxapi.chapters import ClassChapters
from cxapi.jobs.document import ChapterDocument
from cxapi.jobs.exam import ChapterExam
from cxapi.jobs.video import ChapterVideo
from searcher import JsonFileSearcher, RestAPISearcher, SqliteSearcher
from utils import (CONF_EN_DOCUMENT, CONF_EN_EXAM, CONF_EN_VIDEO,
                   CONF_MULTI_SESS, CONF_SEARCHER, CONF_TUI_MAX_HEIGHT,
                   CONF_VIDEO, CONF_WAIT_DOCUMENT, CONF_WAIT_EXAM,
                   CONF_WAIT_VIDEO, ck2dict, sessions_load)

try:
    import readline
except ImportError:
    ...

console = Console(height=CONF_TUI_MAX_HEIGHT)
install(console=console, show_locals=False)

# 自动判断类型, 并实例化搜索器
if CONF_EN_EXAM:
    match CONF_SEARCHER['use']:
        case 'restApiSearcher':
            searcher = RestAPISearcher(**CONF_SEARCHER['restApiSearcher'])
        case 'jsonFileSearcher':
            searcher = JsonFileSearcher(**CONF_SEARCHER['jsonFileSearcher'])
        case 'sqliteSearcher':
            searcher = SqliteSearcher(**CONF_SEARCHER['sqliteSearcher'])
        case _:
            raise TypeError('不合法的搜索器类型')

def wait_for_class(tui_ctx: Layout, wait_sec: int, text: str):
    '课间等待, 防止风控'
    tui_ctx.unsplit()
    for i in range(wait_sec):
        tui_ctx.update(Panel(f'[green]{text}, 课间等待{i}/{wait_sec}s'))
        time.sleep(0.1)

def fuck_task_worker(chap: ClassChapters):
    '完成任务点实现函数'
    lay = Layout()
    lay_main = Layout(Panel('等待执行任务'), name='main')
    lay_chapter = Layout(name='chapter', size=70)
    lay.split_row(lay_main, lay_chapter)
    chap.fetch_point_status()
    with Live(lay, console=console) as live:
        for index in range(len(chap.chapters)):
            chap.render_lst2tui(lay_chapter, index)
            if chap.is_finished(index):  # 如果该章节所有任务点做完, 那么就跳过
                chap.logger.info(
                    f'忽略完成任务点 '
                    f'[{chap.chapters[index].label}:{chap.chapters[index].name}(Id.{chap.chapters[index].chapter_id})]'
                )
                time.sleep(1)  # 解决强迫症, 故意添加延时, 为展示滚屏效果
                continue
            for task_point in chap.fetch_points_by_index(index):  # 获取当前章节的所有任务点, 并遍历
                # 预拉取任务点数据
                prefetch_status = task_point.pre_fetch()
                if not prefetch_status:
                    del task_point
                    continue
                # 拉取取任务点数据
                fetch_status = task_point.fetch()
                if not fetch_status:
                    del task_point
                    continue
                # 开始分类讨论任务点类型
                
                # 试题类型
                if isinstance(task_point, ChapterExam) and CONF_EN_EXAM:
                    task_point.mount_searcher(searcher)
                    task_point.fill_and_commit(lay_main)
                    # 开始等待
                    wait_for_class(lay_main, CONF_WAIT_EXAM, f'试题《{task_point.title}》已结束')
                
                # 视频类型
                elif isinstance(task_point, ChapterVideo) and CONF_EN_VIDEO:
                    task_point.playing(lay_main, CONF_VIDEO['speed'], CONF_VIDEO['report_rate'])
                    # 开始等待
                    wait_for_class(lay_main, CONF_WAIT_VIDEO, f'视频《{task_point.title}》已结束')
                
                # 文档类型
                elif isinstance(task_point, ChapterDocument) and CONF_EN_DOCUMENT:
                    task_point.reading(lay_main)
                    # 开始等待
                    wait_for_class(lay_main, CONF_WAIT_DOCUMENT, f'文档《{task_point.title}》已结束')
                
                # 析构任务点对象
                del task_point
                chap.fetch_point_status()  # 刷新章节任务点状态
                chap.render_lst2tui(lay_chapter, index)
        lay_main.unsplit()
        lay_main.update(Panel('[green]该课程已通过', border_style='green'))
        time.sleep(5.0)
            
if __name__ == '__main__':
    api = ChaoXingAPI()
    dialog.logo(console)
    sessions = sessions_load()
    # 存在至少一个会话存档
    if sessions:
        # 开启多会话, 允许进行选择
        if CONF_MULTI_SESS:
            dialog.select_session(console, sessions, api)
        # 关闭多会话, 默认加载第一个会话存档
        else:
            ck = ck2dict(sessions[0].ck)
            api.ck_load(ck)
    # 会话存档为空
    else:
        console.print('[yellow]会话存档为空, 请登录账号')
        dialog.login(console, api)
    api.logger.info('-----*任务开始执行*-----')
    dialog.accinfo(console, api)
    try:
        classes = api.fetch_classes()  # 拉取该账号下所学的课程
        course_seq = dialog.select_class(console, classes)  # 进行课程选择
        for chapter in course_seq:  # 迭代返回课程章节
            fuck_task_worker(chapter)
    except Exception as err:
        console.print_exception(show_locals=False)
        api.logger.error('-----*程序运行异常退出*-----', exc_info=True)
        if isinstance(err, json.JSONDecodeError):
            console.print('[red]JSON 解析失败, 可能为账号 ck 失效, 请重新登录该账号 (序号+r)')
        else:    
            console.print('[bold red]程序运行出现错误, 请截图保存并附上 log 文件在 issue 提交')
    except KeyboardInterrupt:
        api.logger.warning('-----*手动中断程序*-----')
        console.print('[yellow]手动中断程序运行')
    else:
        api.logger.info('-----*任务执行完毕, 程序退出*-----')
        console.print('[green]任务已完成, 程序退出')
