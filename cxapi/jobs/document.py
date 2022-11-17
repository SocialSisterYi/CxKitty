import json
import re
import time

import requests
from rich.json import JSON
from rich.layout import Layout
from rich.panel import Panel

from ..utils import get_dc

PAGE_MOBILE_CHAPTER_CARD = 'https://mooc1-api.chaoxing.com/knowledge/cards'      # SSR页面-客户端章节任务卡片
API_DOCUMENT_READINGREPORT = 'https://mooc1.chaoxing.com/ananas/job/document'    # 接口-课程文档阅读上报

class ChapterDocument:
    '章节文档'
    session: requests.Session
    # 基本参数
    clazzid: int
    courseid: int
    knowledgeid: int
    card_index: int  # 卡片索引位置
    point_index: int  # 任务点索引位置
    cpi: int
    puid: int
    # 文档参数
    objectid: str
    jobid: str
    title: str
    jtoken: str
    
    def __init__(self, session: requests.Session, clazzid: int, courseid: int, knowledgeid: int, card_index: int, objectid: str, cpi: int, puid: int, point_index: int) -> None:
        self.session = session
        self.clazzid = clazzid
        self.courseid = courseid
        self.knowledgeid = knowledgeid
        self.card_index = card_index
        self.objectid = objectid
        self.cpi = cpi
        self.puid = puid
        self.point_index = point_index
    
    def pre_fetch(self) -> bool:
        '预拉取文档  返回是否需要完成'
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
        try:
            if r := re.search(r'window\.AttachmentSetting *= *(.+?);', resp.text):
                j = json.loads(r.group(1))
            else:
                raise ValueError
            if j['attachments'][self.point_index].get('job') == True:  # 这里需要忽略非任务点文档
                self.title = j['attachments'][self.point_index]['property']['name']
                self.jobid = j['attachments'][self.point_index]['jobid']
                self.jtoken = j['attachments'][self.point_index]['jtoken']
                return True
            return False  # 非任务点文档不需要完成
        except Exception:
            raise RuntimeError('文档预拉取出错')
    
    def fetch(self) -> bool:
        '拉取文档'
        return True  # 文档类型无需二次拉取
    
    def __report_reading(self):
        '上报文档阅读记录'
        resp = self.session.get(API_DOCUMENT_READINGREPORT, params={
            'jobid': self.jobid,
            'knowledgeid': self.knowledgeid,
            'courseid': self.courseid,
            'clazzid': self.clazzid,
            'jtoken': self.jtoken,
            '_dc': get_dc()
        })
        resp.raise_for_status()
        return resp.json()
        
    def reading(self, tui_ctx: Layout) -> None:
        '开始模拟阅读文档'
        inspect = Layout()
        tui_ctx.split_column(Panel(f'模拟浏览：{self.title}', title='正在模拟浏览'), inspect)
        report_result = self.__report_reading()
        j = JSON.from_data(report_result, ensure_ascii=False)
        if report_result['status']:
            inspect.update(Panel(j, title='上报成功', border_style='green'))
        else:
            inspect.update(Panel(j, title='上报失败', border_style='red'))
        time.sleep(1.0)
            

__all__ = ['ChapterDocument']