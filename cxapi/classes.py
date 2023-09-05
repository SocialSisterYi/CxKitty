import re
from typing import Iterator, Optional

from bs4 import BeautifulSoup
from yarl import URL

from logger import Logger

from .chapters import ChapterContainer
from .exam import ExamDto
from .exception import APIError
from .schema import AccountInfo, ChapterModel, ClassExamModule, ClassModule, ClassStatus, ExamStatus
from .session import SessionWraper

# 接口-课程章节列表
API_CHAPTER_LST = "https://mooc1-api.chaoxing.com/gas/clazz"

# SSR页面-课程考试列表
PAGE_EXAM_LIST = "https://mooc1-api.chaoxing.com/exam/phone/task-list"


class ClassContainer:
    "课程接口"
    logger: Logger  # 日志记录器
    session: SessionWraper  # HTTP 会话封装
    acc: AccountInfo  # 用户账号信息
    classes: list[ClassModule]  # 课程信息

    def __init__(
        self,
        session: SessionWraper,
        acc: AccountInfo,
        classes_lst: list[dict],
    ) -> None:
        """constructor
        Args:
            session: HTTP 会话封装对象
            acc: 用户账号信息
            classes_lst: 课程序列信息
        """
        self.logger = Logger("Classes")
        self.session = session
        self.acc = acc
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
                    class_id=content["id"],
                    state=ClassStatus(content["state"]),
                    course_id=course["data"][0]["id"],
                    name=course["data"][0]["name"],
                    teacher_name=course["data"][0].get("teacherfactor", "未知"),
                )
            )

    def __len__(self) -> int:
        "获取课程数"
        return len(self.classes)

    def __repr__(self) -> str:
        return f"<Classes count={len(self)}>"

    def get_chapters_by_index(self, index: int) -> list[ChapterModel]:
        """拉取课程对应章节列表
        Args:
            index: 课程索引
        Returns:
            list[ChapterModel]: 课程章节列表
        """
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
            self.logger.error("拉取失败")
            raise APIError

        chapter_lst = content_json["data"][0]["course"]["data"][0]["knowledge"]["data"]
        self.logger.debug(f"章节 Resp: {chapter_lst}")

        chapters = [
            ChapterModel(
                chapter_id=cha["id"],
                jobs=cha["jobcount"],
                index=cha["indexorder"],
                name=cha["name"].strip(),
                label=cha["label"],
                layer=cha["layer"],
                status=cha["status"],
                point_total=0,
                point_finished=0,
            )
            for cha in chapter_lst
        ]
        # 按照任务点节点重排顺序
        chapters.sort(key=lambda x: tuple(int(v) for v in x.label.split(".")))

        self.logger.info(
            f"获取课程章节成功 (共 {len(chapters)} 个) "
            f"[{self.classes[index].name}(Cou.{self.classes[index].course_id}/Cla.{self.classes[index].class_id})]"
        )

        return chapters

    def get_exam_by_index(self, index: int) -> list[ClassExamModule]:
        """获取指定课程的考试列表
        Args:
            index: 课程索引
        Returns:
            list[ClassExamModule]: 考试数据模型列表
        """

        resp = self.session.get(
            PAGE_EXAM_LIST,
            params={
                "courseId": self.classes[index].course_id,
                "classId": self.classes[index].class_id,
                "cpi": self.classes[index].cpi,
            },
        )
        resp.raise_for_status()
        html = BeautifulSoup(resp.text, "lxml")
        exams = []
        if node_exam_lst := html.find("ul", {"class": "nav"}):
            for exam in node_exam_lst.find_all("li"):
                query_params = URL(exam["data"]).query
                exams.append(
                    ClassExamModule(
                        exam_id=int(query_params["taskrefId"]),
                        course_id=self.classes[index].course_id,
                        class_id=self.classes[index].class_id,
                        cpi=self.classes[index].cpi,
                        enc_task=query_params["enc_task"],
                        name=exam.p.text,
                        status=ExamStatus(exam.span.text),
                        expire_time=t.text if (t := exam.find("span", {"class": "fr"})) else None,
                    )
                )
        self.logger.info(
            f"拉取课程考试成功 (共 {len(exams)} 个) "
            f"[{self.classes[index].name}(Cou.{self.classes[index].course_id}/Cla.{self.classes[index].class_id})]"
        )
        return exams


# 选择器分段匹配表达式
RE_SELECTOR_SEG = re.compile(
    r"^(?P<exam_flag>EXAM *(\((?P<exam_index>\d+)\)|\(#(?P<exam_id>\d+)\))?\|)?((?P<index>\d+)$|(?P<start>\d+)-(?P<end>\d+)$|#(?P<id>\d+)$|\"(?P<name>.*?)\"$)"
)


class ClassSelector:
    "课程选择器"
    __mached_indexes: dict[int, dict]  # 匹配的课程索引
    __mached_index_iterator: Iterator[tuple[int, dict]]
    __classes: ClassContainer

    def __init__(self, seq_str: str, classes: ClassContainer) -> None:
        self.__classes = classes
        self.__mached_indexes = {}
        for seg in seq_str.split(","):
            if res := RE_SELECTOR_SEG.match(seg.strip()):
                params = {}
                # 解析考试模式参数
                if res.group("exam_flag"):
                    params["exam_flag"] = True
                    if exam_index := res.group("exam_index"):
                        params["exam_index"] = int(exam_index)
                    elif exam_id := res.group("exam_id"):
                        params["exam_id"] = int(exam_id)
                # 解析课程选择器语句
                # 索引
                if index := res.group("index"):
                    index = int(index)
                    if index < len(self.__classes):
                        self.__mached_indexes[index] = params.copy()
                # 索引范围
                elif (start := res.group("start")) and (end := res.group("end")):
                    start = int(start)
                    end = int(end)
                    if end >= start:
                        index_range = range(start, end + 1)
                    else:
                        index_range = range(end, start + 1)
                    self.__mached_indexes.update({index: params.copy() for index in index_range})
                # 课程 id
                elif class_id := res.group("id"):
                    if (index := self.__id2index(int(class_id))) is not None:
                        self.__mached_indexes[index] = params.copy()
                # 课程名
                elif class_name := res.group("name"):
                    if (index := self.__name2index(class_name)) is not None:
                        self.__mached_indexes[index] = params.copy()
        # 重排序课程索引
        self.__mached_indexes = dict(sorted(self.__mached_indexes.items()))

    def __len__(self) -> int:
        return len(self.__mached_indexes)

    def __iter__(self) -> "ClassSelector":
        self.__mached_index_iterator = iter(self.__mached_indexes.items())
        return self

    def __next__(self) -> ChapterContainer | ExamDto | list[ClassExamModule]:
        curr_index, curr_params = next(self.__mached_index_iterator)
        if curr_params.get("exam_flag") is True:
            # 选择语句为考试
            exams_lst = self.__classes.get_exam_by_index(curr_index)
            exam_index = curr_params.get("exam_index")

            # 按照 id 搜索考试数据模型
            if exam_index is None and (exam_id := curr_params.get("exam_id")):
                for exam_index, exam in enumerate(exams_lst):
                    if exam.exam_id == exam_id:
                        break

            if exam_index is not None:
                # 实例考试对象
                return ExamDto(
                    session=self.__classes.session,
                    acc=self.__classes.acc,
                    exam_id=exams_lst[exam_index].exam_id,
                    course_id=exams_lst[exam_index].course_id,
                    class_id=exams_lst[exam_index].class_id,
                    cpi=exams_lst[exam_index].cpi,
                    enc_task=exams_lst[exam_index].enc_task,
                )
            return exams_lst
        else:
            # 选择语句为章节
            chapters = self.__classes.get_chapters_by_index(curr_index)
            class_meta = self.__classes.classes[curr_index]
            # 实例化章节容器
            return ChapterContainer(
                session=self.__classes.session,
                acc=self.__classes.acc,
                courseid=class_meta.course_id,
                classid=class_meta.class_id,
                name=class_meta.name,
                cpi=class_meta.cpi,
                chapters=chapters,
            )

    def __id2index(self, cid: int) -> Optional[int]:
        for i, c in enumerate(self.__classes.classes):
            if c.course_id == cid:
                return i

    def __name2index(self, name: str) -> Optional[int]:
        for i, c in enumerate(self.__classes.classes):
            if c.name.startswith(name):
                return i


__all__ = ["ClassContainer", "ClassSelector"]
