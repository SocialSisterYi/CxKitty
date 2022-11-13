from dataclasses import dataclass
import requests
from rich.table import Table
from .chapters import ClassChapters
from .exceptions import APIError

API_CHAPTER_LST = 'https://mooc1-api.chaoxing.com/gas/clazz'                     # 接口-课程章节列表

@dataclass
class ClassModule:
    '课程数据模型'
    courseid: int
    clazzid: int
    cpi: int
    key: int
    name: str
    teacher_name: str
    state: int
    

class Classes:
    session: requests.Session
    classes: list[ClassModule]
    puid: int
    
    def __init__(self, session: requests.Session, puid: int, classes_lst: list[dict]) -> None:
        self.session = session
        self.puid = puid
        self.classes = []
        for c in classes_lst:
            # ORM
            self.classes.append(ClassModule(
                cpi          = c['cpi'],
                key          = c['key'],
                clazzid      = c['content']['id'],
                state        = c['content']['state'],
                courseid     = c['content']['course']['data'][0]['id'],
                name         = c['content']['course']['data'][0]['name'],
                teacher_name = c['content']['course']['data'][0]['teacherfactor']
            ))
    
    def print_tb(self, tui_ctx) -> None:
        '输出课程列表表格'
        tb = Table('序号', '课程名', '老师名', '课程id', '课程状态', title='所学的课程', border_style='blue')
        for num, cla in enumerate(self.classes):
            tb.add_row(
                f'[green]{num}', cla.name, cla.teacher_name, str(cla.courseid),
                '[red]已结课' if cla.state else '[green]进行中'
            )
        tui_ctx.print(tb)
    
    def fetch_chapters_by_index(self, index: int) -> ClassChapters:
        '拉取课程对应“章节”列表'
        resp = self.session.get(API_CHAPTER_LST, params={
            'id': self.classes[index].key,
            'personid': self.classes[index].cpi,
            'fields': 'id,bbsid,classscore,isstart,allowdownload,chatid,name,state,isfiled,visiblescore,begindate,coursesetting.fields(id,courseid,hiddencoursecover,coursefacecheck),course.fields(id,name,infocontent,objectid,app,bulletformat,mappingcourseid,imageurl,teacherfactor,jobcount,knowledge.fields(id,name,indexOrder,parentnodeid,status,layer,label,jobcount,begintime,endtime,attachment.fields(id,type,objectid,extension).type(video)))',
            'view': 'json'
        })
        resp.raise_for_status()
        content_json = resp.json()
        if len(content_json['data']) == 0:
            raise APIError
        return ClassChapters(
            session=self.session,
            courseid=self.classes[index].courseid,
            clazzid=self.classes[index].clazzid,
            cpi=self.classes[index].cpi,
            puid=self.puid,
            chapter_lst=content_json['data'][0]['course']['data'][0]['knowledge']['data']
        )