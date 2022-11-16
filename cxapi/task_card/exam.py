import difflib
import json
import re
import time
from dataclasses import dataclass
from enum import Enum
from typing import Any

import jsonpath
import lxml.html
import requests
from rich.json import JSON
from rich.layout import Layout
from rich.panel import Panel
from rich.table import Table

from searcher import SearcherBase

API_EXAM_COMMIT = 'https://mooc1-api.chaoxing.com/work/addStudentWorkNew'        # 接口-单元测验答题提交
PAGE_MOBILE_CHAPTER_CARD = 'https://mooc1-api.chaoxing.com/knowledge/cards'      # SSR页面-客户端章节任务卡片
PAGE_MOBILE_EXAM = 'https://mooc1-api.chaoxing.com/android/mworkspecial'         # SSR页面-客户端单元测验答题页

class QuestionEnum(Enum):
    '题目类型枚举'
    单选题 = 0
    多选题 = 1
    判断题 = 3

@dataclass
class QuestionModel:
    '题目数据模型'
    question_id: int
    value: str
    question_type: QuestionEnum
    answers: dict[str, str]
    option: str

class ChapterExam:
    '章节测验'
    session: requests.Session
    # 基本参数
    card_index: int
    courseid: int
    knowledgeid: int
    cpi: int
    clazzid: int
    puid: int
    # 考试参数
    title: str
    workid: str
    jobid: str
    ktoken: str
    enc: str
    # 提交参数
    workAnswerId: int
    totalQuestionNum: str
    fullScore: str
    workRelationId: int
    enc_work: str
    # 答题参数
    questions: list[QuestionModel]
    # 搜题器对象
    searcher: SearcherBase
    # 施法参数
    need_jobid: bool
    
    def __init__(self, session: requests.Session, card_index: int, courseid: int, workid: str, jobid: str, knowledgeid: int, puid: int, clazzid: int, cpi: int) -> None:
        self.session = session
        self.card_index = card_index
        self.courseid = courseid
        self.workid = workid
        self.jobid = jobid
        self.knowledgeid = knowledgeid
        self.puid = puid
        self.clazzid = clazzid
        self.cpi = cpi
    
    def pre_fetch(self) -> bool:
        '预拉取试题  返回是否需要完成'
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
            self.ktoken = j['defaults']['ktoken']
            self.enc = j['attachments'][0]['enc']
            if (job := j['attachments'][0].get('job')) is not None:
                needtodo = job in (True, None)  # 这里有部分试题不存在`job`字段
                self.need_jobid = True  # 不知道为什么这里的`job`字段和请求试题的接口的`jobid`参数有关
            else:
                self.need_jobid = False
                needtodo = True
        except Exception:
            raise RuntimeError('试题预拉取出错')
        return needtodo
    
    def fetch(self) -> bool:
        '拉取并解析试题'
        resp = self.session.get(PAGE_MOBILE_EXAM, params={
            'courseid': self.courseid,
            'workid': self.workid,
            'jobid': self.jobid if self.need_jobid else '',
            'needRedirect': 'true',
            'knowledgeid': self.knowledgeid,
            'userid':self.puid,
            'ut': 's',
            'clazzId': self.clazzid,
            'cpi': self.cpi,
            'ktoken': self.ktoken,
            'enc': self.enc
        }, allow_redirects=True)
        resp.raise_for_status()
        root = lxml.html.fromstring(resp.text)
        if re.search(r'已批阅', root.xpath("//title/text()")[0]):
            return False
        if p := root.xpath("//p[@class='blankTips']/text()"):
            if re.search(r'无效的权限', p[0]):
                return False
        self.title = root.xpath("//h3[contains(@class, 'py-Title')]/text()")[0].strip()
        # 提取答题表单参数
        self.workAnswerId = int(root.xpath("//input[@name='workAnswerId']/@value")[0])
        self.enc_work = root.xpath("//input[@name='enc_work']/@value")[0]
        self.totalQuestionNum = root.xpath("//input[@name='totalQuestionNum']/@value")[0]
        self.fullScore = root.xpath("//input[@name='fullScore']/@value")[0]
        self.workRelationId = int(root.xpath("//input[@name='workRelationId']/@value")[0])
        # 提取并解析题目
        question_node = root.xpath("//div[@class='zquestions']/div[@class='Py-mian1']")
        self.questions = []
        for question in question_node:  # 遍历题目
            # 查找并净化题目字符串
            # 因为题目所在标签不确定, 可能为 div.Py-m1-title/ 也可能为 div.Py-m1-title/span 也可能为 div.Py-m1-title/p
            q_title_node = question.xpath("div/div[contains(@class, 'Py-m1-title')]")[0]
            value = ''.join(q_title_node.xpath("text() | */text()")[2:]).strip().replace('\n', '').replace('\r', '')
            if r := re.match(r'answers?(\d+)', question.xpath("div/input[@class='answerInput']/@id")[0]):
                question_id = int(r.group(1))
            else:
                raise ValueError
            answers = question.xpath("div/ul[contains(@class, 'answerList')]/li")
            question_type = QuestionEnum(int(question.xpath("div/input[starts-with(@id, 'answertype')]/@value")[0]))
            answer_map = {}
            for answer in answers: # 遍历选项
                match question_type:
                    case QuestionEnum.单选题 | QuestionEnum.多选题:
                        k = answer.xpath("em/@id-param")[0].strip()
                        if x := answer.xpath("p/cc/text()"):
                            v = x[0].strip()
                        elif x := answer.xpath("cc/p/text()"):
                            v = x[0].strip()
                        else:
                            v = answer.xpath("p/cc/p/text()")[0].strip()
                        answer_map[k] = v
                    case QuestionEnum.判断题:
                        k = answer.xpath("@val-param")[0].strip()
                        v = answer.xpath("p/text()")[0].strip()
                        answer_map[k] = v
                    case _:
                        raise NotImplementedError('不支持的题目类型')
            self.questions.append(QuestionModel(
                question_id=question_id,
                value=value,
                question_type=question_type,
                answers=answer_map,
                option=''
            ))
        return True
    
    def __fill_answer(self, question: QuestionModel, search_resp: dict) -> bool:
        '查询并填充对应选项'
        if search_resp.get('code') == 1:
            if (r := self.searcher.rsp_query.parse(search_resp)):
                search_answer: str = r[0].strip()
            else:
                return False  # JsonPath 选择器匹配失败返回
            match question.question_type:
                case QuestionEnum.单选题:
                    for k, v in question.answers.items():
                        if difflib.SequenceMatcher(a=v, b=search_answer).ratio() >= 0.9:
                            question.option = k
                            return True
                    else:
                        return False
                case QuestionEnum.判断题:
                    if re.search(r'(错|错误|×)', search_answer):
                        question.option = 'false'
                        return True
                    elif re.search(r'(对|正确|√)', search_answer):
                        question.option = 'true'
                        return True
                    else:
                        return False
                case QuestionEnum.多选题:
                    option_lst = []
                    if len(part_answer_lst := search_answer.split('#')) <= 1:
                        part_answer_lst = search_answer.split(';')
                    for part_answer in part_answer_lst:
                        for k, v in question.answers.items():
                            if difflib.SequenceMatcher(a=v, b=part_answer).ratio() >= 0.9:
                                option_lst.append(k)
                    option_lst.sort()  # 多选题选项必须排序，否则提交错误
                    if len(option_lst):
                        question.option = ''.join(option_lst)
                        return True
                    return False
                case _:
                    raise NotImplementedError
        else:
            return False
    
    def mount_searcher(self, searcher_obj: Any) -> None:
        '挂载搜题器对象'
        self.searcher = searcher_obj
    
    def fill_and_commit(self, tui_ctx: Layout) -> None:
        '填充并提交试题 答题主逻辑'
        tb = Table('id', '类型', '题目', '选项')
        msg = Layout(name='msg')
        tui_ctx.split_column(tb, msg)
        tb.title = f'[bold yellow]答题中[/]  {self.title}'
        tb.border_style = 'yellow'
        mistake_questions = {}  # 答错题列表
        for question in self.questions:
            search_resp = self.searcher.invoke(question.value)  # 调用搜索器搜索方法
            msg.update(Panel(
                JSON.from_data(search_resp, ensure_ascii=False),
                title='题库接口返回'
            ))
            status = self.__fill_answer(question, search_resp)  # 填充选项
            tb.add_row(
                str(question.question_id),
                question.question_type.name,
                question.value,
                (f'[green]{question.option}' if status else '[red]未匹配')
            )
            if status == False:
                mistake_questions[question.value] = self.searcher.rsp_query.parse(search_resp)  # 记录错题
            time.sleep(1.0)
        # 没有错误
        if (mistake_num := len(mistake_questions)) == 0:
            tb.title = f'[bold green]答题完毕[/]  {self.title}'
            tb.border_style = 'green'
            commit_result = self.__commit()  # 提交试题
            j = JSON.from_data(commit_result, ensure_ascii=False)
            if commit_result['status'] == True:
                msg.update(Panel(j, title='提交成功 TAT！', border_style='green'))
            else:
                msg.update(Panel(j, title='提交失败！', border_style='red'))
        # 存在错误
        else:
            tb.title = f'[bold red]有{mistake_num}道错误[/]  {self.title}'
            tb.border_style = 'red'
            msg.update(Panel(
                '\n'.join(f'q：{q}\na：{a}' for q, a in mistake_questions.items()),
                title='有错误的题', highlight=False, style='red'
            ))
            # TODO:提交保存试题
        time.sleep(5.0)
    
    def __mk_answer_reqdata(self) -> dict[str, str]:
        '输出试题答案表单信息'
        result = {
            'answerwqbid': ','.join(str(q.question_id) for q in self.questions)
        }
        for q in self.questions:
            result[f'answer{q.question_id}'] = q.option
            result[f'answertype{q.question_id}'] = q.question_type.value
        return result
    
    def __commit(self) -> dict:
        '提交答题信息'
        answer_data = self.__mk_answer_reqdata()
        resp = self.session.post(API_EXAM_COMMIT,
            params={
                'keyboardDisplayRequiresUserAction': 1,
                '_classId': self.clazzid,
                'courseid': self.courseid,
                'token': self.enc_work,
                'workAnswerId': self.workAnswerId,
                'workid': self.workRelationId,
                'cpi:': self.cpi,
                'jobid': self.jobid,
                'knowledgeid': self.knowledgeid,
                'ua': 'app'
            },
            data={
                'pyFlag': '',
                'courseId': self.courseid,
                'classId': self.clazzid,
                'api':1,
                'mooc': 0,
                'workAnswerId': self.workAnswerId,
                'totalQuestionNum': self.totalQuestionNum,
                'fullScore': self.fullScore,
                'knowledgeid': self.knowledgeid,
                'oldSchoolId': '',
                'oldWorkId': self.workid,
                'jobid': self.jobid,
                'workRelationId': self.workRelationId,
                'enc_work': self.enc_work,
                'isphone': 'true',
                'userId': self.puid,
                'workTimesEnc': '',
                **answer_data
            }
        )
        resp.raise_for_status()
        json_content = resp.json()
        return json_content

__all__ = ['ChapterExam']