from dataclasses import dataclass
from enum import Enum


@dataclass
class AccountInfo:
    "账号个人信息"
    puid: int  # 用户 puid
    name: str  # 真实姓名
    sex: str  # 性别
    phone: str  # 手机号
    school: str  # 学校
    stu_id: str  # 学号


@dataclass
class ClassModule:
    "课程数据模型"
    courseid: int
    clazzid: int
    cpi: int
    key: int
    name: str
    teacher_name: str
    state: int


@dataclass
class ChapterModel:
    "章节数据模型"
    chapter_id: int
    jobs: int
    index: int
    name: str
    label: str
    layer: int
    status: str
    point_total: int
    point_finish: int


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


@dataclass
class QuestionModel:
    "题目数据模型"
    q_id: int
    value: str
    q_type: QuestionType
    answers: dict[str, str]
    answer: str
