import difflib
import json
import re
import time
from typing import Literal

import requests
from bs4 import BeautifulSoup
from rich.json import JSON
from rich.layout import Layout
from rich.panel import Panel
from rich.table import Table

from logger import Logger
from searcher import SearcherBase, SearchResp

from ..schema import (
    AccountInfo, 
    ExamQuestionExportSchema, 
    QuestionModel,
    QuestionType
)

# 接口-单元测验答题提交
API_EXAM_COMMIT = "https://mooc1-api.chaoxing.com/work/addStudentWorkNew"

# SSR页面-客户端章节任务卡片
PAGE_MOBILE_CHAPTER_CARD = "https://mooc1-api.chaoxing.com/knowledge/cards"

# SSR页面-客户端单元测验答题页
PAGE_MOBILE_EXAM = "https://mooc1-api.chaoxing.com/android/mworkspecial"

# 搜索器槽位
searcher_slot: list[SearcherBase] = []


def add_searcher(searcher: SearcherBase):
    "添加搜索器"
    searcher_slot.append(searcher)


def remove_searcher(searcher: SearcherBase):
    "移除搜索器"
    searcher_slot.remove(searcher)


def invoke_searcher(question: QuestionModel) -> list[SearchResp]:
    "调用搜索器"
    result = []
    if searcher_slot:
        for searcher in searcher_slot:
            result.append(searcher.invoke(question))
        return result
    raise NotImplementedError("至少需要加载一个搜索器")


def parse_question(question_node: BeautifulSoup) -> QuestionModel:
    "解析题目"
    # 获取题目 id
    question_id = int(question_node.select_one("input[id*='answertype']")["id"][10:])
    # 获取题目类型
    question_type = QuestionType(int(question_node.select_one("input[id*='answertype']")["value"]))
    # 查找并净化题目字符串
    # 因为题目所在标签不确定, 可能为 div.Py-m1-title/ 也可能为 div.Py-m1-title/span 也可能为 div.Py-m1-title/p
    q_title_node = question_node.find("div", {"class": "Py-m1-title"})
    value = (
        "".join(list(q_title_node.strings)[2:])
        .strip()
        .replace("\n", "")
        .replace("\r", "")
        .replace("\u200b", "")
    )
    # 开始解析选项
    answer_map = {}
    if question_type in (QuestionType.单选题, QuestionType.多选题):
        answers = question_node.find("ul", {"class": "answerList"}).find_all("li", {"class": "more-choose-item"})
        # 遍历选项
        for answer in answers:
            k = answer.find("em", {"class": "choose-opt"})["id-param"]
            answer_map[k] = (
                "".join(
                    set(
                        node.text.strip()
                        for node
                        in answer.find_all(["p", "cc"])
                    )
                )
                .strip()
                .replace("\u200b", "")
            )
    return QuestionModel(
        q_id=question_id, value=value, q_type=question_type, options=answer_map
    )


class ChapterExam:
    "章节测验"
    logger: Logger
    session: requests.Session
    acc: AccountInfo
    # 基本参数
    card_index: int  # 卡片索引位置
    point_index: int  # 任务点索引位置
    course_id: int
    knowledge_id: int
    cpi: int
    clazz_id: int
    # 考试参数
    title: str
    work_id: str
    school_id: str
    job_id: str
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
    # 施法参数
    need_jobid: bool

    def __init__(
            self,
            session: requests.Session,
            acc: AccountInfo,
            card_index: int,
            course_id: int,
            work_id: str,
            school_id: str,
            job_id: str,
            knowledge_id: int,
            clazz_id: int,
            cpi: int,
    ) -> None:
        self.session = session
        self.acc = acc
        self.card_index = card_index
        self.course_id = course_id
        self.work_id = work_id
        self.school_id = school_id
        self.job_id = job_id
        self.knowledge_id = knowledge_id
        self.clazz_id = clazz_id
        self.cpi = cpi
        self.logger = Logger("PointExam")
        self.logger.set_loginfo(self.acc.phone)

    def pre_fetch(self) -> bool:
        "预拉取试题  返回是否需要完成"
        resp = self.session.get(
            PAGE_MOBILE_CHAPTER_CARD,
            params={
                "clazzid": self.clazz_id,
                "courseid": self.course_id,
                "knowledgeid": self.knowledge_id,
                "num": self.card_index,
                "isPhone": 1,
                "control": "true",
                "cpi": self.cpi,
            },
        )
        resp.raise_for_status()
        html = BeautifulSoup(resp.text, "lxml")
        try:    
            if r := re.search(
                r"window\.AttachmentSetting *= *(.+?);",
                html.head.find("script", type="text/javascript").text,
            ):
                attachment = json.loads(r.group(1))
            else:
                raise ValueError
            self.logger.debug(f"attachment: {attachment}")
            # 定位资源 workid
            for point in attachment["attachments"]:
                if prop := point.get("property"):
                    if prop.get("workid") == self.work_id:
                        break
            else:
                self.logger.warning("定位任务资源失败")
                return False
            self.ktoken = attachment["defaults"]["ktoken"]
            self.enc = point["enc"]
            if (job := point.get("job")) is not None:
                needtodo = job in (True, None)  # 这里有部分试题不存在`job`字段
                self.need_jobid = True  # 不知道为什么这里的`job`字段和请求试题的接口的`jobid`参数有关
            else:
                self.need_jobid = False
                needtodo = True
            self.logger.info("预拉取成功")
        except Exception:
            self.logger.error("预拉取失败")
            raise RuntimeError("试题预拉取出错")
        return needtodo

    def fetch(self) -> bool:
        "拉取并解析试题"
        resp = self.session.get(
            PAGE_MOBILE_EXAM,
            params={
                "courseid": self.course_id,
                "workid": f"{self.school_id}-{self.work_id}" if self.school_id else self.work_id,   # 这里分类讨论两种形式的 workid
                "jobid": self.job_id if self.need_jobid else "",
                "needRedirect": "true",
                "knowledgeid": self.knowledge_id,
                "userid": self.acc.puid,
                "ut": "s",
                "clazzId": self.clazz_id,
                "cpi": self.cpi,
                "ktoken": self.ktoken,
                "enc": self.enc,
            },
            allow_redirects=True,
        )
        resp.raise_for_status()
        self.logger.info("拉取成功")
        html = BeautifulSoup(resp.text, "lxml")
        # 抓取标题并判断有效性
        if re.search(r"已批阅", html.find("title").text):
            self.logger.warning("试题已批阅")
            return False
        if p := html.find("p", {"class": "blankTips"}):
            if re.search(r"(无效的权限|此作业已被老师删除！)", p.text):
                self.logger.warning("试题无权限/被删除")
                return False
        self.title = html.find("h3", {"class": ["py-Title", "chapter-title"]}).text.strip()
        # 提取答题表单参数
        self.workAnswerId = int(html.find("input", {"name": "workAnswerId"})["value"])
        self.enc_work = html.find("input", {"name": "enc_work"})["value"]
        self.totalQuestionNum = html.find("input", {"name": "totalQuestionNum"})["value"]
        self.fullScore = html.find("input", {"name": "fullScore"})["value"]
        self.workRelationId = int(html.find("input", {"name": "workRelationId"})["value"])
        self.questions = []
        # 提取并遍历题目
        for question_node in html.find_all("div", {"class": "Py-mian1"}):
            question = parse_question(question_node)
            self.questions.append(question)
            self.logger.debug(f"question schema: {question.__dict__}")
        self.logger.info(
            f"试题解析成功 共 {len(self.questions)} 道 [{self.title}(J.{self.job_id}/W.{self.work_id})]"
        )
        return True

    def __fill_answer(self, question: QuestionModel, search_results: list[SearchResp]) -> bool:
        "查询并填充对应选项"
        log_suffix = f"[{question.value}(Id.{question.q_id})]"
        self.logger.debug(f"开始填充题目 {log_suffix}")
        # 遍历多个搜索器返回以适配结果
        for result in search_results:
            if result.code != 0 or result.answer is None:
                continue
            search_answer = result.answer.strip()
            match question.q_type:
                case QuestionType.单选题:
                    for k, v in question.options.items():
                        if difflib.SequenceMatcher(a=v, b=search_answer).ratio() >= 0.9:
                            question.answer = k
                            self.logger.debug(f"单选题命中 {k}={v} {log_suffix}")
                            return True
                case QuestionType.判断题:
                    if re.search(r"(错|否|错误|false|×)", search_answer):
                        question.answer = False
                        self.logger.debug(f"判断题命中 true {log_suffix}")
                        return True
                    elif re.search(r"(对|是|正确|true|√)", search_answer):
                        question.answer = True
                        self.logger.debug(f"判断题命中 false {log_suffix}")
                        return True
                case QuestionType.多选题:
                    option_lst = []
                    if len(part_answer_lst := search_answer.split("#")) <= 1:
                        part_answer_lst = search_answer.split(";")
                    for part_answer in part_answer_lst:
                        for k, v in question.options.items():
                            if difflib.SequenceMatcher(a=v, b=part_answer).ratio() >= 0.9:
                                option_lst.append(k)
                                self.logger.debug(f"多选题命中 {k}={v} {log_suffix}")
                    # 多选题选项必须排序，否则提交错误
                    option_lst.sort()
                    if len(option_lst):
                        question.answer = "".join(option_lst)
                        self.logger.debug(f"多选题最终选项 {question.answer}")
                        return True
                case QuestionType.填空题:
                    blanks_answer = search_answer.split("#")
                    if blanks_answer:
                        question.answer = blanks_answer
                        self.logger.debug(f"填空题内容 {question.answer}")
                        return True
        if question.q_type in (
            QuestionType.单选题,
            QuestionType.判断题,
            QuestionType.多选题,
            QuestionType.填空题
        ):
            self.logger.warning(f"{question.q_type.name}填充失败 {log_suffix}")
        else:
            self.logger.warning(
                f"未实现的题目类型 {question.q_type.name}/{question.q_type.value} {log_suffix}"
            )
        return False

    def export(self, format: Literal["schema", "dict", "json"] = None):
        "导出当前试题"
        schema = ExamQuestionExportSchema(
            title=self.title,
            work_id=self.work_id,
            questions=self.questions
        )
        match format:
            case "schema" | None:
                return schema
            case "dict":
                return schema.to_dict()
            case "json":
                return schema.to_json(ensure_ascii=False, separators=(",", ":"))
        
    
    def fill_and_commit(self, tui_ctx: Layout, fail_save: bool = True) -> None:
        "填充并提交试题 答题主逻辑"
        self.logger.info(f"开始完成试题 " f"[{self.title}(J.{self.job_id}/W.{self.work_id})]")
        tb = Table("id", "类型", "题目", "选项")
        msg = Layout(name="msg", size=9)
        tui_ctx.split_column(tb, msg)
        tb.title = f"[bold yellow]答题中[/]  {self.title}"
        tb.border_style = "yellow"
        mistake_questions: list[tuple[QuestionModel, str]] = []  # 答错题列表
        for question in self.questions:
            results = invoke_searcher(question)  # 调用搜索器搜索方法
            self.logger.debug(f"题库调用成功 req={question.value} rsp={results}")
            msg.update(
                Panel(
                    "\n".join(
                        (
                            f"[{'green' if result.code == 0 else 'red'}]"
                            f"{result.searcher.__class__.__name__} -> "
                            f"{'搜索成功' if result.code == 0 else f'搜索失败{result.code}:{result.message}'} -> [/]"
                            f"[cyan]{result.answer}[/]"
                        )
                        for result in results
                    ),
                    title="题库接口返回",
                )
            )
            # 填充选项
            status = self.__fill_answer(question, results)
            tb.add_row(
                str(question.q_id),
                question.q_type.name,
                question.value,
                (f"[green]{question.answer}" if status else "[red]未匹配"),
            )
            # 记录错题
            if status == False:
                mistake_questions.append(
                    (question, "/".join(str(result.answer) for result in results))
                )
            time.sleep(1.0)

        # 开始答题结束处理
        if (mistake_num := len(mistake_questions)) == 0:
            # 没有错误
            tb.title = f"[bold green]答题完毕[/]  {self.title}"
            tb.border_style = "green"
            # 提交试题
            commit_result = self.__commit()
            j = JSON.from_data(commit_result, ensure_ascii=False)
            if commit_result["status"] == True:
                self.logger.info(
                    f"试题提交成功 "
                    f"[{self.title}(J.{self.job_id}/W.{self.work_id})]"
                )
                msg.update(Panel(j, title="提交成功 TAT！", border_style="green"))
            else:
                self.logger.warning(
                    f"试题提交失败 "
                    f"[{self.title}(J.{self.job_id}/W.{self.work_id})]"
                )
                msg.update(Panel(j, title="提交失败！", border_style="red"))

        else:
            # 存在错误
            tb.title = f"[bold red]有{mistake_num}道错误[/]  {self.title}"
            tb.border_style = "red"
            msg.update(
                Panel(
                    "\n".join(f"q：{q.value}\na：{a}" for q, a in mistake_questions),
                    title="有错误的题",
                    highlight=False,
                    style="red",
                )
            )
            self.logger.warning(f"试题未完成 " f"[{self.title}(J.{self.job_id}/W.{self.work_id})]")
            
            # 构建未完成题目提示信息
            incomplete_msg = f"共 {mistake_num} 题未完成\n"
            incomplete_msg += "--------------------\n"
            for i, (q, a) in enumerate(mistake_questions, 1):
                incomplete_msg += f"{i}.\tq({q.q_type.name}/{q.q_type.value}): {q.value}\n"
                if q.q_type in (QuestionType.单选题, QuestionType.多选题):
                    incomplete_msg += f"\to: {' '.join(f'{k}={v}' for k, v in q.options.items())}\n"
                incomplete_msg += f"\ta: {a}\n"
            incomplete_msg += "--------------------"
            self.logger.warning(incomplete_msg)
            
            # 保存未完成的试卷
            if fail_save:
                save_result = self.__save()
                j = JSON.from_data(save_result, ensure_ascii=False)
                if save_result["status"] == True:
                    self.logger.info(f"试题保存成功 " f"[{self.title}(J.{self.job_id}/W.{self.work_id})]")
                    msg.update(Panel(j, title="保存成功 TAT！", border_style="green"))
                else:
                    self.logger.warning(f"试题保存失败 " f"[{self.title}(J.{self.job_id}/W.{self.work_id})]")
                    msg.update(Panel(j, title="保存失败！", border_style="red"))
        time.sleep(5.0)

    def __mk_answer_reqform(self) -> dict[str, str]:
        "输出试题答案表单信息"
        form = {"answerwqbid": ",".join(str(q.q_id) for q in self.questions)}
        for q in self.questions:
            form[f"answertype{q.q_id}"] = q.q_type.value
            match q.q_type:
                case QuestionType.判断题:
                    form[f"answer{q.q_id}"] = "true" if q.answer else "false"
                case QuestionType.填空题:
                    if isinstance(q.answer, list):
                        blank_amount = len(q.answer)
                        form[f"tiankongsize{q.q_id}"] = blank_amount
                        for blank_index in range(blank_amount):
                            form[f"answer{q.q_id}{blank_index + 1}"] = q.answer[blank_index]
                case _:
                    form[f"answer{q.q_id}"] = q.answer
        return form

    def __commit(self) -> dict:
        "提交答题信息"
        answer_form = self.__mk_answer_reqform()
        self.logger.debug(f"试题提交 payload: {answer_form}")
        resp = self.session.post(
            API_EXAM_COMMIT,
            params={
                "keyboardDisplayRequiresUserAction": 1,
                "_classId": self.clazz_id,
                "courseid": self.course_id,
                "token": self.enc_work,
                "workAnswerId": self.workAnswerId,
                "workid": self.workRelationId,
                "cpi:": self.cpi,
                "jobid": self.job_id,
                "knowledgeid": self.knowledge_id,
                "ua": "app",
            },
            data={
                "pyFlag": "",
                "courseId": self.course_id,
                "classId": self.clazz_id,
                "api": 1,
                "mooc": 0,
                "workAnswerId": self.workAnswerId,
                "totalQuestionNum": self.totalQuestionNum,
                "fullScore": self.fullScore,
                "knowledgeid": self.knowledge_id,
                "oldSchoolId": "",
                "oldWorkId": self.work_id,
                "jobid": self.job_id,
                "workRelationId": self.workRelationId,
                "enc_work": self.enc_work,
                "isphone": "true",
                "userId": self.acc.puid,
                "workTimesEnc": "",
                **answer_form,
            },
        )
        resp.raise_for_status()
        json_content = resp.json()
        self.logger.debug(f"试题提交 resp: {json_content}")
        return json_content

    def __save(self) -> dict:
        "保存答题信息"
        answer_form = self.__mk_answer_reqform()
        self.logger.debug(f"试题保存 payload: {answer_form}")
        resp = self.session.post(
            API_EXAM_COMMIT,
            params={
                "_classId": self.clazz_id,
                "courseid": self.course_id,
                "token": self.enc_work,
                "workAnswerId": self.workAnswerId,
                "ua": "app",
                "formType2": "post",
                "saveStatus": 1,
                "version": 1,
                "tempsave": 1
            },
            data={
                "pyFlag": "1",
                "courseId": self.course_id,
                "classId": self.clazz_id,
                "api": 1,
                "mooc": 0,
                "workAnswerId": self.workAnswerId,
                "totalQuestionNum": self.totalQuestionNum,
                "fullScore": self.fullScore,
                "knowledgeid": self.knowledge_id,
                "oldSchoolId": "",
                "oldWorkId": self.work_id,
                "jobid": self.job_id,
                "workRelationId": self.workRelationId,
                "enc_work": self.enc_work,
                "isphone": "true",
                "userId": self.acc.puid,
                "workTimesEnc": "",
                **answer_form,
            },
        )
        resp.raise_for_status()
        json_content = resp.json()
        self.logger.debug(f"试题保存 resp: {json_content}")
        return json_content


__all__ = ["ChapterExam"]
