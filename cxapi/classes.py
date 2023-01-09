import re
from typing import Iterator, Optional

import requests

from logger import Logger

from . import APIError
from .chapters import ClassChapters
from .schema import AccountInfo, ClassModule

# 接口-课程章节列表
API_CHAPTER_LST = "https://mooc1-api.chaoxing.com/gas/clazz"


class Classes:
    logger: Logger
    session: requests.Session
    acc: AccountInfo
    classes: list[ClassModule]

    def __init__(
        self, session: requests.Session, acc: AccountInfo, classes_lst: list[dict]
    ) -> None:
        self.session = session
        self.acc = acc
        self.logger = Logger("Classes")
        self.logger.set_loginfo(self.acc.phone)
        self.classes = []
        for cla in classes_lst:
            # 未知 bug
            # 有些课程不存在`content`字段, 跳过处理
            content = cla["content"]
            if (course := content.get("course")) == None:
                continue
            # ORM
            self.classes.append(
                ClassModule(
                    cpi=cla["cpi"],
                    key=cla["key"],
                    clazzid=content["id"],
                    state=content["state"],
                    courseid=course["data"][0]["id"],
                    name=course["data"][0]["name"],
                    teacher_name=course["data"][0]["teacherfactor"],
                )
            )

    def __len__(self) -> int:
        "获取课程数"
        return len(self.classes)

    def __repr__(self) -> str:
        return f"<Classes count={len(self)}>"

    def fetch_chapters_by_index(self, index: int) -> ClassChapters:
        "拉取课程对应章节列表"
        resp = self.session.get(
            API_CHAPTER_LST,
            params={
                "id": self.classes[index].key,
                "personid": self.classes[index].cpi,
                "fields": "id,bbsid,classscore,isstart,allowdownload,chatid,name,state,isfiled,visiblescore,begindate,coursesetting.fields(id,courseid,hiddencoursecover,coursefacecheck),course.fields(id,name,infocontent,objectid,app,bulletformat,mappingcourseid,imageurl,teacherfactor,jobcount,knowledge.fields(id,name,indexOrder,parentnodeid,status,layer,label,jobcount,begintime,endtime,attachment.fields(id,type,objectid,extension).type(video)))",
                "view": "json",
            },
        )
        resp.raise_for_status()
        content_json = resp.json()
        if len(content_json["data"]) == 0:
            self.logger.info(
                f"获取课程 [{self.classes[index].name}(Cou.{self.classes[index].courseid}/Cla.{self.classes[index].clazzid})] "
                f"章节列表失败"
            )
            raise APIError
        class_cnt = len(content_json["data"][0]["course"]["data"][0]["knowledge"]["data"])
        self.logger.info(
            f"获取课程 章节列表成功 共 {class_cnt} 个 "
            f"[{self.classes[index].name}(Cou.{self.classes[index].courseid}/Cla.{self.classes[index].clazzid})]"
        )
        return ClassChapters(
            session=self.session,
            acc=self.acc,
            courseid=self.classes[index].courseid,
            clazzid=self.classes[index].clazzid,
            name=self.classes[index].name,
            cpi=self.classes[index].cpi,
            chapter_lst=content_json["data"][0]["course"]["data"][0]["knowledge"]["data"],
        )


class ClassSeqIter:
    "课程批量序列迭代器"
    __mached_index_nums: list[int]
    __mached_index_iterator: Iterator
    __classes: Classes

    def __init__(self, seq_str: str, classes: Classes) -> None:
        temp = set()
        self.__classes = classes
        for seg in seq_str.split(","):
            seg = seg.strip()
            # 课程名
            if r := re.match(r"^\"(?P<name>.*?)\"$", seg):
                if (index := self.__name2index(r.group("name"))) is not None:
                    temp.add(index)
            # 索引范围
            elif r := re.match(r"^(?P<start>\d+)-(?P<end>\d+)$", seg):
                start = int(r.group("start"))
                end = int(r.group("end"))
                if end >= start:
                    temp.update(range(start, end + 1))
                else:
                    temp.update(range(end, start + 1))
            # 课程 id
            elif r := re.match(r"^#(?P<id>\d+)$", seg):
                if (index := self.__id2index(int(r.group("id")))) is not None:
                    temp.add(index)
            # 索引
            elif r := re.match(r"^(?P<index>\d+)$", seg):
                index = int(r.group("index"))
                if index < len(self.__classes):
                    temp.add(index)
        self.__mached_index_nums = list(temp)
        self.__mached_index_nums.sort()

    def __len__(self) -> int:
        return len(self.__mached_index_nums)

    def __iter__(self) -> "ClassSeqIter":
        self.__mached_index_iterator = iter(self.__mached_index_nums)
        return self

    def __next__(self) -> ClassChapters:
        curr_index = next(self.__mached_index_iterator)
        return self.__classes.fetch_chapters_by_index(curr_index)

    def __id2index(self, cid: int) -> Optional[int]:
        for i, c in enumerate(self.__classes.classes):
            if c.courseid == cid:
                return i

    def __name2index(self, name: str) -> Optional[int]:
        for i, c in enumerate(self.__classes.classes):
            if c.name.startswith(name):
                return i


__all__ = ["Classes", "ClassSeqIter"]
