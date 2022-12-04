import json
import re
import time
import urllib.parse
from hashlib import md5

import requests
from bs4 import BeautifulSoup
from rich.json import JSON
from rich.layout import Layout
from rich.panel import Panel
from rich.progress import Progress

from logger import Logger

from .. import get_dc
from ..schema import AccountInfo

PAGE_MOBILE_CHAPTER_CARD = 'https://mooc1-api.chaoxing.com/knowledge/cards'      # SSR页面-客户端章节任务卡片
API_CHAPTER_CARD_RESOURCE = 'https://mooc1-api.chaoxing.com/ananas/status'       # 接口-课程章节卡片资源
API_VIDEO_PLAYREPORT = 'https://mooc1-api.chaoxing.com/multimedia/log/a'         # 接口-视频播放上报


class ChapterVideo:
    '章节视频'
    logger: Logger
    session: requests.Session
    acc: AccountInfo
    # 基本参数
    clazzid: int
    courseid: int
    knowledgeid: int
    card_index: int  # 卡片索引位置
    point_index: int  # 任务点索引位置
    cpi: int
    # 视频参数
    objectid: str
    fid: int
    dtoken: str
    duration: int
    jobid: str
    otherInfo: str
    title: str
    
    def __init__(self, session: requests.Session, acc: AccountInfo, clazzid: int, courseid: int, knowledgeid: int, card_index: int, objectid: str, cpi: int, point_index: int) -> None:
        self.session = session
        self.acc = acc
        self.clazzid = clazzid
        self.courseid = courseid
        self.knowledgeid = knowledgeid
        self.card_index = card_index
        self.objectid = objectid
        self.cpi = cpi
        self.point_index = point_index
        self.logger = Logger('PointVideo')
        self.logger.set_loginfo(self.acc.phone)
    
    def pre_fetch(self) -> bool:
        '预拉取视频  返回是否需要完成'
        resp = self.session.get(PAGE_MOBILE_CHAPTER_CARD, params={
            'clazzid': self.clazzid,
            'courseid': self.courseid,
            'knowledgeid': self.knowledgeid,
            'num': self.card_index,
            'isPhone': 1,
            'control': 'true',
            'cpi': self.cpi
        })
        resp.raise_for_status()
        html = BeautifulSoup(resp.text, 'lxml')
        try:
            if r := re.search(r'window\.AttachmentSetting *= *(.+?);', html.head.find('script', type='text/javascript').text):
                attachment = json.loads(r.group(1))
            else:
                raise ValueError
            self.fid = attachment['defaults']['fid']
            self.jobid = attachment['attachments'][self.point_index]['jobid']
            self.otherInfo = attachment['attachments'][self.point_index]['otherInfo']
            needtodo = attachment['attachments'][self.point_index].get('isPassed') in (False, None)
            self.logger.info('预拉取成功')
            self.logger.debug(f'attachment: {attachment}')
        except Exception:
            self.logger.error('预拉取失败')
            raise RuntimeError('视频预拉取出错')
        return needtodo
    
    def fetch(self) -> bool:
        '拉取视频'
        resp = self.session.get(
            f'{API_CHAPTER_CARD_RESOURCE}/{self.objectid}',
            params={
                'k': self.fid,
                'flag': 'normal',
                '_dc': get_dc()
            }
        )
        resp.raise_for_status()
        json_content = resp.json()
        self.dtoken = json_content['dtoken']
        self.duration = json_content['duration']
        self.title = json_content['filename']
        self.logger.info(f'拉取成功 [{self.title}/{self.duration}(O.{self.objectid}/T.{self.dtoken}/J.{self.jobid})]')
        self.logger.debug(f'视频 schema: {json_content}')
        return True
    
    def __play_report(self, playing_time: int) -> dict:
        '播放上报'
        resp = self.session.get(
            f'{API_VIDEO_PLAYREPORT}/{self.cpi}/{self.dtoken}',
            params=urllib.parse.urlencode({
                'otherInfo': self.otherInfo,
                'playingTime': playing_time,
                'duration': self.duration,
                # 'akid': None,
                'jobid': self.jobid,
                'clipTime': f'0_{self.duration}',
                'clazzId': self.clazzid,
                'objectId': self.objectid,
                'userid': self.acc.puid,
                'isdrag': '0',
                'enc': md5(f'[{self.clazzid}][{self.acc.puid}][{self.jobid}][{self.objectid}][{playing_time * 1000}][d_yHJ!$pdA~5][{self.duration * 1000}][0_{self.duration}]'.encode()).hexdigest(),
                'rt': '0.9',  # 'rt': '1.0',  ??
                'dtype': 'Video',
                'view': 'pc',
                '_t': int(time.time()*1000)
            }, safe='&=')  # 这里不需要编码`&`和`=`否则报403
        )
        resp.raise_for_status()
        json_content = resp.json()
        self.logger.info('播放上报成功')
        self.logger.debug(f'上报 resp: {json_content}')
        return json_content
    
    def playing(self, tui_ctx: Layout, speed: float=1.0, report_rate: int=58) -> None:
        '开始模拟播放视频'
        s_counter = report_rate
        playing_time = 0
        progress = Progress()
        info = Layout()
        tui_ctx.split_column(info, Panel(progress, title=f'模拟播放视频[green]《{self.title}》[/]', border_style='yellow'))
        bar = progress.add_task('playing...', total=self.duration)
        def _update_bar():
            '更新进度条'
            progress.update(
                bar,
                completed=playing_time,
                description=f"playing... [blue]{playing_time // 60:02d}:{playing_time % 60:02d}[/blue] [yellow]{report_rate - s_counter}s后汇报[/yellow](X{speed})"
            )
        self.logger.info(
            f'开始播放 倍速=x{speed} 汇报率={report_rate}s '
            f'[{self.title}/{self.duration}(O.{self.objectid}/T.{self.dtoken}/J.{self.jobid})]'
        )
        while True:
            if s_counter >= report_rate:
                s_counter = 0
                report_result = self.__play_report(playing_time)
                j = JSON.from_data(report_result, ensure_ascii=False)
                if report_result.get('error'):
                    self.logger.warning(f'播放上报失败 {playing_time}/{self.duration}')
                    info.update(Panel(j, title='上报失败', border_style='red'))
                else:
                    self.logger.info(f'播放上报成功 {playing_time}/{self.duration}')
                    info.update(Panel(j, title='上报成功', border_style='green'))
                if report_result.get('isPassed') == True:
                    playing_time = self.duration  # 强制100%, 解决强迫症
                    self.logger.info(f'播放完毕')
                    _update_bar()
                    info.update(Panel('OHHHHHHHH', title='播放完毕', border_style='green'))
                    time.sleep(5.0)
                    break
            playing_time += round(1 * speed)
            s_counter += round(1 * speed)
            _update_bar()
            time.sleep(1.0)

__all__ = ['ChapterVideo']