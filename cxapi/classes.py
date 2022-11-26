
import requests

from . import APIError
from .chapters import ClassChapters
from .schema import AccountInfo, ClassModule

API_CHAPTER_LST = 'https://mooc1-api.chaoxing.com/gas/clazz'                     # 接口-课程章节列表


class Classes:
    session: requests.Session
    classes: list[ClassModule]
    acc: AccountInfo
    
    def __init__(self, session: requests.Session, acc: AccountInfo, classes_lst: list[dict]) -> None:
        self.session = session
        self.acc = acc
        self.classes = []
        for c in classes_lst:
            # 未知 bug
            # 有些课程不存在`content`字段, 跳过处理
            if 'course' not in c['content']:
                continue
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
            acc=self.acc,
            courseid=self.classes[index].courseid,
            clazzid=self.classes[index].clazzid,
            cpi=self.classes[index].cpi,
            chapter_lst=content_json['data'][0]['course']['data'][0]['knowledge']['data']
        )