from dataclasses import dataclass, field
from enum import Enum

from dataclasses_json import config, dataclass_json


class AccountSex(Enum):
    "账号性别"
    未知 = -1
    男 = 1
    女 = 0


@dataclass
class AccountInfo:
    "账号个人信息"
    puid: int  # 用户 puid
    name: str  # 真实姓名
    sex: AccountSex  # 性别
    phone: str  # 手机号
    school: str  # 学校
    stu_id: str | None  # 学号

    def __str__(self) -> str:
        return f"AccInfo(puid={self.puid} name='{self.name}' sex={self.sex} phone={self.phone} school='{self.school}' stu_id={self.stu_id})"


class ClassStatus(Enum):
    "课程状态"
    进行中 = 0
    已结课 = 1


@dataclass
class ClassModule:
    "课程数据模型"
    course_id: int  # 课程 id
    class_id: int  # 班级 id
    cpi: int
    key: int
    name: str  # 课程名
    teacher_name: str  # 老师名
    state: ClassStatus  # 课程状态


@dataclass
class ChapterModel:
    "章节数据模型"
    chapter_id: int  # 章节 id
    jobs: int
    index: int
    name: str
    label: str  # 章节标签
    layer: int  # 章节层级
    status: str
    point_total: int  # 总计任务点
    point_finished: int  # 已完成任务点


class QuestionType(Enum):
    "题目类型枚举"
    单选题 = 0
    多选题 = 1
    填空题 = 2
    判断题 = 3
    简答题 = 4
    名词解释 = 5
    论述题 = 6
    计算题 = 7
    其它 = 8
    分录题 = 9
    资料题 = 10
    连线题 = 11
    排序题 = 13
    完型填空 = 14
    阅读理解 = 15
    口语题 = 18
    听力题 = 19
    共用选项题 = 20
    测评题 = 21


@dataclass_json
@dataclass
class QuestionModel:
    "题目数据模型"
    id: int  # 题目 id
    value: str  # 题干
    type: QuestionType = field(metadata=config(encoder=lambda x: x.value))  # 题目类型
    options: dict[str, str] | list[str] = None  # 选项或填空
    answer: str | list[str] | bool = None  # 答案


class QuestionsExportType(Enum):
    """试题导出类型"""

    Exam = 0  # 试卷
    Work = 1  # 作业
    Mistakes = 2  # 错题


@dataclass_json
@dataclass
class QuestionsExportSchema:
    "试题导出规范"
    id: str  # 试题 id
    title: str  # 试题名
    type: QuestionsExportType = field(metadata=config(encoder=lambda x: x.value))  # 导出类型
    questions: list[QuestionModel]  # 题目列表


class ExamStatus(Enum):
    "考试完成状态"
    未开始 = "未开始"
    未交 = "未交"
    已完成 = "已完成"


@dataclass
class ClassExamModule:
    "课程考试数据模型"
    exam_id: int  # 考试 id
    course_id: int  # 课程 id
    class_id: int  # 班级 id
    cpi: int
    enc_task: int  # 考试校验 key
    name: str  # 考试标题
    status: ExamStatus  # 考试状态
    expire_time: str  # 剩余时间
