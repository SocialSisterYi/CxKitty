import difflib
import json
import re
import time
from typing import Any

import requests
from bs4 import BeautifulSoup
from rich.json import JSON
from rich.layout import Layout
from rich.panel import Panel
from rich.table import Table

from logger import Logger
from searcher import SearcherBase

from ..schema import AccountInfo, QuestionType, QuestionModel

API_EXAM_COMMIT = 'https://mooc1-api.chaoxing.com/work/addStudentWorkNew'        # 接口-单元测验答题提交
PAGE_MOBILE_CHAPTER_CARD = 'https://mooc1-api.chaoxing.com/knowledge/cards'      # SSR页面-客户端章节任务卡片
PAGE_MOBILE_EXAM = 'https://mooc1-api.chaoxing.com/android/mworkspecial'         # SSR页面-客户端单元测验答题页


def parse_question(question_node: BeautifulSoup):
    '解析题目'
    question_id = int(question_node.select_one("input[id*='answertype']")['id'][10:])  # 获取题目 id
    question_type = QuestionType(int(question_node.select_one("input[id*='answertype']")['value']))  # 获取题目类型
    # 查找并净化题目字符串
    # 因为题目所在标签不确定, 可能为 div.Py-m1-title/ 也可能为 div.Py-m1-title/span 也可能为 div.Py-m1-title/p
    q_title_node = question_node.find('div', {'class': 'Py-m1-title'})
    value = ''.join(list(q_title_node.strings)[2:]).strip().replace('\n', '').replace('\r', '')
    # 开始解析选项
    answer_map = {}
    if question_type in (QuestionType.单选题, QuestionType.多选题):
        answers = question_node.find('ul', {'class': 'answerList'}).find_all('li')
        for answer in answers: # 遍历选项
            k = answer.em['id-param'].strip()
            answer_map[k] = answer.find_all(['p','cc'])[-1].text.strip()
    return QuestionModel(
        q_id=question_id,
        value=value,
        q_type=question_type,
        answers=answer_map,
        answer=''
    )
    

class ChapterExam:
    '章节测验'
    logger: Logger
    session: requests.Session
    acc: AccountInfo
    # 基本参数
    card_index: int  # 卡片索引位置
    point_index: int  # 任务点索引位置
    courseid: int
    knowledgeid: int
    cpi: int
    clazzid: int
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
    
    def __init__(self, session: requests.Session, acc: AccountInfo, card_index: int, courseid: int, workid: str, jobid: str, knowledgeid: int, clazzid: int, cpi: int, point_index: int) -> None:
        self.session = session
        self.acc = acc
        self.card_index = card_index
        self.courseid = courseid
        self.workid = workid
        self.jobid = jobid
        self.knowledgeid = knowledgeid
        self.clazzid = clazzid
        self.cpi = cpi
        self.point_index = point_index
        self.logger = Logger('PointExam')
        self.logger.set_loginfo(self.acc.phone)
    
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
        html = BeautifulSoup(resp.text, 'lxml')
        try:
            if r := re.search(r'window\.AttachmentSetting *= *(.+?);', html.head.find('script', type='text/javascript').text):
                attachment = json.loads(r.group(1))
            else:
                raise ValueError
            self.logger.debug(f'attachment: {attachment}')
            self.ktoken = attachment['defaults']['ktoken']
            self.enc = attachment['attachments'][self.point_index]['enc']
            if (job := attachment['attachments'][self.point_index].get('job')) is not None:
                needtodo = job in (True, None)  # 这里有部分试题不存在`job`字段
                self.need_jobid = True  # 不知道为什么这里的`job`字段和请求试题的接口的`jobid`参数有关
            else:
                self.need_jobid = False
                needtodo = True
            self.logger.info('预拉取成功')
        except Exception:
            self.logger.error('预拉取失败')
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
            'userid':self.acc.puid,
            'ut': 's',
            'clazzId': self.clazzid,
            'cpi': self.cpi,
            'ktoken': self.ktoken,
            'enc': self.enc
        }, allow_redirects=True)
        resp.raise_for_status()
        self.logger.info('拉取成功')
        html = BeautifulSoup(resp.text, 'lxml')
        # 抓取标题并判断有效性
        if re.search(r'已批阅', html.find('title').text):
            self.logger.warning('试题已批阅')
            return False
        if p := html.find('p', {'class': 'blankTips'}):
            if re.search(r'无效的权限', p.text):
                self.logger.warning('试题无权限')
                return False
        self.title = html.find('h3', {'class': 'py-Title'}).text.strip()
        # 提取答题表单参数
        self.workAnswerId = int(html.find('input', {'name': 'workAnswerId'})['value'])
        self.enc_work = html.find('input', {'name': 'enc_work'})['value']
        self.totalQuestionNum = html.find('input', {'name': 'totalQuestionNum'})['value']
        self.fullScore = html.find('input', {'name': 'fullScore'})['value']
        self.workRelationId = int(html.find('input', {'name': 'workRelationId'})['value'])
        self.questions = []
        # 提取并遍历题目
        for question_node in html.find_all('div', {'class': 'Py-mian1'}):
            question = parse_question(question_node)
            self.questions.append(question)
            self.logger.debug(f"question schema: {question.__dict__}")
        self.logger.info(
            f'试题解析成功 共 {len(self.questions)} 道 '
            f'[{self.title}(J.{self.jobid}/W.{self.workid})]'
        )
        return True
    
    def __fill_answer(self, question: QuestionModel, search_resp: dict) -> bool:
        '查询并填充对应选项'
        log_sufixx = f'[{question.value}(Id.{question.q_id})]'
        self.logger.debug(f'开始填充题目 {log_sufixx}')
        if search_resp.get('code') == 1:
            if (r := self.searcher.rsp_query.parse(search_resp)):
                search_answer: str = r[0].strip()
            else:
                return False  # JsonPath 选择器匹配失败返回
            match question.q_type:
                case QuestionType.单选题:
                    for k, v in question.answers.items():
                        if difflib.SequenceMatcher(a=v, b=search_answer).ratio() >= 0.9:
                            question.answer = k
                            self.logger.debug(f'单选题命中 {k}={v} {log_sufixx}')
                            return True
                    else:
                        self.logger.warning(f'单选题填充失败 {log_sufixx}')
                        return False
                case QuestionType.判断题:
                    if re.search(r'(错|错误|×)', search_answer):
                        question.answer = 'false'
                        self.logger.debug(f'判断题命中 true {log_sufixx}')
                        return True
                    elif re.search(r'(对|正确|√)', search_answer):
                        question.answer = 'true'
                        self.logger.debug(f'判断题命中 false {log_sufixx}')
                        return True
                    else:
                        self.logger.warning(f'判断题填充失败 {log_sufixx}')
                        return False
                case QuestionType.多选题:
                    option_lst = []
                    if len(part_answer_lst := search_answer.split('#')) <= 1:
                        part_answer_lst = search_answer.split(';')
                    for part_answer in part_answer_lst:
                        for k, v in question.answers.items():
                            if difflib.SequenceMatcher(a=v, b=part_answer).ratio() >= 0.9:
                                option_lst.append(k)
                                self.logger.debug(f'多选题命中 {k}={v} {log_sufixx}')
                    option_lst.sort()  # 多选题选项必须排序，否则提交错误
                    if len(option_lst):
                        question.answer = ''.join(option_lst)
                        self.logger.debug(f'多选题最终选项 {question.answer}')
                        return True
                    self.logger.warning(f'多选题填充失败 {log_sufixx}')
                    return False
                case _:
                    self.logger.warning(f'未实现的题目类型 {question.q_type.name}/{question.q_type.value} {log_sufixx}')
                    return False
        else:
            self.logger.warning(f"题库接口响应码异常 errCode={search_resp.get('code')} {log_sufixx}")
            return False
    
    def mount_searcher(self, searcher_obj: Any) -> None:
        '挂载搜题器对象'
        self.searcher = searcher_obj
    
    def fill_and_commit(self, tui_ctx: Layout) -> None:
        '填充并提交试题 答题主逻辑'
        self.logger.info(
            f'开始完成试题 '
            f'[{self.title}(J.{self.jobid}/W.{self.workid})]'
        )
        tb = Table('id', '类型', '题目', '选项')
        msg = Layout(name='msg')
        tui_ctx.split_column(tb, msg)
        tb.title = f'[bold yellow]答题中[/]  {self.title}'
        tb.border_style = 'yellow'
        mistake_questions = []  # 答错题列表
        for question in self.questions:
            try:
                search_resp = self.searcher.invoke(question.value)  # 调用搜索器搜索方法
            except Exception as err:
                status = False
                search_resp = ''
                self.logger.warning(f'题库调用异常 err={err.__str__()}')
                msg.update(Panel(
                    err.__str__(),
                    title='[red]题库接口异常',
                    border_style='red'
                ))
            else:
                self.logger.debug(f'题库调用成功 req={question.value} rsp={search_resp}')
                msg.update(Panel(
                    JSON.from_data(search_resp, ensure_ascii=False),
                    title='题库接口返回'
                ))
                status = self.__fill_answer(question, search_resp)  # 填充选项
                tb.add_row(
                    str(question.q_id),
                    question.q_type.name,
                    question.value,
                    (f'[green]{question.answer}' if status else '[red]未匹配')
                )
            if status == False:
                mistake_questions.append((question, self.searcher.rsp_query.parse(search_resp)))  # 记录错题
            time.sleep(1.0)
        # 没有错误
        if (mistake_num := len(mistake_questions)) == 0:
            tb.title = f'[bold green]答题完毕[/]  {self.title}'
            tb.border_style = 'green'
            commit_result = self.__commit()  # 提交试题
            j = JSON.from_data(commit_result, ensure_ascii=False)
            if commit_result['status'] == True:
                self.logger.info(
                    f'试题提交成功 '
                    f'[{self.title}(J.{self.jobid}/W.{self.workid})]'
                )
                msg.update(Panel(j, title='提交成功 TAT！', border_style='green'))
            else:
                self.logger.warning(
                    f'试题提交失败 '
                    f'[{self.title}(J.{self.jobid}/W.{self.workid})]'
                )
                msg.update(Panel(j, title='提交失败！', border_style='red'))
        # 存在错误
        else:
            tb.title = f'[bold red]有{mistake_num}道错误[/]  {self.title}'
            tb.border_style = 'red'
            msg.update(Panel(
                '\n'.join(f"q：{q.value}\na：{a}" for q, a in mistake_questions),
                title='有错误的题', highlight=False, style='red'
            ))
            self.logger.warning(
                f'试题未完成 '
                f'[{self.title}(J.{self.jobid}/W.{self.workid})]'
            )
            self.logger.warning(
                f'共 {mistake_num} 题未完成\n' +
                '--------------------\n' +
                '\n'.join((
                        f"{i}.\tq({q.q_type.name}/{q.q_type.value}): {q.value} " + (
                            f"\n\to: {' '.join(f'{k}={v}' for k, v in q.answers.items())}" 
                            if q.q_type in (QuestionType.单选题, QuestionType.多选题) 
                            else '') +
                        f"\n\ta: {a}"  
                    ) for i, (q, a)
                    in enumerate(mistake_questions, 1)
                ) +
                '\n--------------------'
            )
            # TODO: 答题失败提交保存
        time.sleep(5.0)
    
    def __mk_answer_reqdata(self) -> dict[str, str]:
        '输出试题答案表单信息'
        result = {
            'answerwqbid': ','.join(str(q.q_id) for q in self.questions)
        }
        for q in self.questions:
            result[f'answer{q.q_id}'] = q.answer
            result[f'answertype{q.q_id}'] = q.q_type.value
        return result
    
    def __commit(self) -> dict:
        '提交答题信息'
        answer_data = self.__mk_answer_reqdata()
        self.logger.debug(f'试题提交 payload: {answer_data}')
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
                'userId': self.acc.puid,
                'workTimesEnc': '',
                **answer_data
            }
        )
        resp.raise_for_status()
        json_content = resp.json()
        self.logger.debug(f'试题提交 resp: {json_content}')
        return json_content

__all__ = ['ChapterExam']