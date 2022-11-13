import json
import time
from dataclasses import dataclass
from typing import Union

import lxml.html
import requests
from rich.layout import Layout
from rich.panel import Panel

from .exceptions import APIError
from .task_card.exam import ChapterExam
from .task_card.video import ChapterVideo
from .utils import calc_infenc

API_CHAPTER_POINT = 'https://mooc1-api.chaoxing.com/job/myjobsnodesmap'          # 接口-课程章节任务点状态
API_CHAPTER_CARDS = 'https://mooc1-api.chaoxing.com/gas/knowledge'               # 接口-课程章节卡片


@dataclass
class ChapterModel:
    '章节数据模型'
    chapter_id: int
    jobs: int
    index: int
    name: str
    label: str
    layer: int
    status: str
    point_total: int
    point_finish: int

class ClassChapters:
    '课程章节'
    session: requests.Session
    chapters: list[ChapterModel]
    # 课程参数
    courseid: int
    clazzid: int
    cpi: int
    puid: int
    
    def __init__(self, session: requests.Session, courseid: int, clazzid: int, cpi: int, puid: int, chapter_lst: list[dict]) -> None:
        self.session = session
        self.courseid = courseid
        self.clazzid = clazzid
        self.cpi = cpi
        self.puid = puid
        
        self.chapters = []
        for c in chapter_lst:
            if c['layer'] != 2:
                continue
            self.chapters.append(ChapterModel(
                chapter_id=c['id'],
                jobs=c['jobcount'],
                index=c['indexorder'],
                name=c['name'].strip(),
                label=c['label'],
                layer=c['layer'],
                status=c['status'],
                point_total=0, point_finish=0
            ))
        self.chapters.sort(key=lambda x: tuple(int(v) for v in x.label.split('.')))
    
    def is_finished(self, index: int) -> bool:
        '判断当前章节的任务点是否全部完成'
        return (self.chapters[index].point_total > 0) and (self.chapters[index].point_total == self.chapters[index].point_finish)
    
    def render_lst2tui(self, tui_ctx: Layout, index: int, lst_length: int=16):
        '渲染章节列表到TUI'
        lines = []
        total = len(self.chapters)
        half_length = lst_length // 2
        if index - half_length < 0:
            _min = 0
            _max = min(total, lst_length)
        elif index + half_length > total:
            _min = total - lst_length
            _max = total
        else:
            _min = index - half_length
            _max = index + half_length
        for ptr in range(_min, _max):
            chapter = self.chapters[ptr]
            # 判断是否已完成章节任务
            is_finished = self.is_finished(ptr)
            lines.append(
                ('[bold red]❱[/]' if ptr == index else ' ') + 
                f'[bold green]{chapter.label}[/]:' +
                '[' + ('bold ' if ptr == index else '')  + ('green' if is_finished else 'white') + ']' + chapter.name + '[/]' +
                f'\t...任务点{chapter.point_finish}/{chapter.point_total}'
            )
        tui_ctx.update(Panel('\n'.join(lines), title='课程列表', border_style='blue'))
    
    def fetch_point_status(self):
        '拉取章节任务点状态'
        resp = self.session.post(API_CHAPTER_POINT, data={
            'view': 'json',
            'nodes': ','.join(str(c.chapter_id) for c in self.chapters),
            'clazzid': self.clazzid,
            'time': int(time.time()*1000),
            'userid': self.puid,
            'cpi': self.cpi,
            'courseid': self.courseid
        })
        resp.raise_for_status()
        json_content = resp.json()
        for c in self.chapters:
            point_data = json_content[str(c.chapter_id)]
            c.point_total = point_data['totalcount']
            c.point_finish = point_data['finishcount']
    
    def fetch_points_by_index(self, num: int) -> list[Union[ChapterExam, ChapterVideo]]:
        '以课程序号拉取对应“章节”的任务节点卡片资源'
        params = {
            'id': self.chapters[num].chapter_id,
            'courseid': self.courseid,
            'fields': 'id,parentnodeid,indexorder,label,layer,name,begintime,createtime,lastmodifytime,status,jobUnfinishedCount,clickcount,openlock,card.fields(id,knowledgeid,title,knowledgeTitile,description,cardorder).contentcard(all)',
            'view': 'json',
            'token': '4faa8662c59590c6f43ae9fe5b002b42',
            '_time': int(time.time()*1000)
        }
        resp = self.session.get(API_CHAPTER_CARDS, params={**params, 'inf_enc': calc_infenc(params)})
        resp.raise_for_status()
        content_json = resp.json()
        if len(content_json['data']) == 0:
            raise APIError
        cards = content_json['data'][0]['card']['data']
        point_objs = []  # 任务点实例化列表
        for card_index, card in enumerate(cards):  # 遍历章节卡片
            inline_html = lxml.html.fromstring(card['description'])
            points = inline_html.xpath("//iframe")
            for point in points:  # 遍历任务点列表
                # 获取任务点类型 非视频和试题跳过
                if point_type := point.xpath("@module"):
                    point_type = point_type[0]
                else:
                    continue
                json_data = json.loads(point.xpath("@data")[0])
                match point_type:
                    case 'insertvideo':
                        # 视频任务点
                        point_objs.append(ChapterVideo(
                            session=self.session,
                            card_index=card_index,
                            courseid=self.courseid,
                            knowledgeid=self.chapters[num].chapter_id,
                            objectid=json_data['objectid'],
                            puid=self.puid,
                            clazzid=self.clazzid,
                            cpi=self.cpi
                        ))
                    case 'work':
                        # 测验任务点
                        point_objs.append(ChapterExam(
                            session=self.session,
                            card_index=card_index,
                            courseid=self.courseid,
                            workid=json_data['workid'],
                            jobid=json_data['_jobid'],
                            knowledgeid=self.chapters[num].chapter_id,
                            puid=self.puid,
                            clazzid=self.clazzid,
                            cpi=self.cpi
                        ))
        return point_objs