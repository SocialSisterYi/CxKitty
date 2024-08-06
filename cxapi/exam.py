import json
import random
import re
from datetime import datetime
from pathlib import Path
from typing import Literal

from bs4 import BeautifulSoup, Tag
from bs4.element import NavigableString
from rich.columns import Columns
from rich.console import Console, ConsoleOptions, Group, RenderResult
from rich.layout import Layout
from rich.table import Table
from rich.text import Text
from yarl import URL

from logger import Logger

from .base import QAQDtoBase
from .captcha.image import ImageCaptchaDto, ImageCaptchaType, fuck_slide_image_captcha
from .exception import (
    APIError,
    ChaptersNotComplete,
    ExamAccessDenied,
    ExamCodeDenied,
    ExamCompleted,
    ExamEnterError,
    ExamError,
    ExamInvalidParams,
    ExamIsCommitted,
    ExamNotStart,
    ExamSubmitError,
    ExamSubmitTooEarly,
    ExamTimeout,
    FaceDetectionError,
    HandleCaptchaError,
    IPNotAllow,
    PCExamClintOnly,
)
from .schema import (
    AccountInfo,
    QuestionModel,
    QuestionsExportSchema,
    QuestionsExportType,
    QuestionType,
)
from .session import SessionWraper
from .utils import get_exam_signature, get_imei, remove_escape_chars

# SSR页面-考试入口封面
PAGE_EXAM_COVER = "https://mooc1-api.chaoxing.com/exam-ans/exam/phone/task-exam"

# SSR页面-考试单题
PAGE_EXAM_QUESTION = "https://mooc1-api.chaoxing.com/exam-ans/exam/test/reVersionTestStartNew"

# SSR页面-考试整卷预览
PAGE_EXAM_PREVIEW = "https://mooc1-api.chaoxing.com/exam-ans/exam/phone/preview"

# API-开始考试
API_START_START = "https://mooc1-api.chaoxing.com/exam-ans/exam/phone/start"

# API-答案提交
API_SUBMIT_ANSWER = "https://mooc1.chaoxing.com/exam-ans/exam/test/reVersionSubmitTestNew"

# API-获取答题卡状态
API_ANSWER_SHEET = "https://mooc1-api.chaoxing.com/exam-ans/exam/phone/loadAnswerStatic"


def parse_question(question_node: Tag) -> QuestionModel:
    """解析题目
    Args:
        question_node: 题目 html 标签节点
    需要符合这种标签的下级结构:
        <div class="allAnswerList questionWrap singleQuesId ans-cc-exam" data="1234">
        <div class="answerMain questionWrap singleQuesId ans-cc-exam" data="1234">
    Returns:
        QuestionModel: 题目数据模型
    """
    question_id = int(question_node.select_one("input[name='questionId']")["value"])
    question_type = QuestionType(int(question_node.select_one("input[name^='type']")["value"]))
    options = None

    # 解析题干
    question_value_node = question_node.select_one("div.tit")
    question_value = ""
    if "answerMain" in question_node["class"]:
        # 单题
        # eg:
        # <div class="tit">
        #   <h3>判断题（共4题，20.0分）</h3>
        #   1.<span style="color: #999;display: inline-block;">（5.0分）</span>题目正文
        # </div>
        for tag in list(question_value_node.children)[4:]:
            if isinstance(tag, NavigableString):
                question_value += tag.strip()
            elif tag.name == "p":
                question_value += f"\n{tag.text.strip()}"
    elif "allAnswerList" in question_node["class"]:
        # 整卷预览
        # eg:
        # <div class="tit">
        #     <h3>判断题（5.0分）</h3>
        #     2.题目正文
        # </div>
        for tag_index, tag in enumerate(list(question_value_node.children)[2:]):
            if isinstance(tag, NavigableString):
                tag = tag.strip()
                if tag_index == 0 and re.match(r"^\d+.", tag):
                    _, temp = tag.split(".", 1)
                    if temp:
                        question_value = temp
                        break
                else:
                    question_value += tag
            elif tag.name == "p":
                question_value += "\n" + tag.text.strip()
    else:
        raise ExamError("题目解析异常")
    question_value = remove_escape_chars(question_value)

    # 分类讨论题型解析
    match question_type:
        case QuestionType.单选题 | QuestionType.多选题:
            options = {}

            # 解析答案
            answer = question_node.select_one("input[id^='answer']")["value"] or None

            # 解析选项
            for option_node in question_node.select("div.answerList.radioList"):
                option_key = option_node["name"]
                option_value = "".join(s.strip() for s in option_node.select_one("cc").strings)
                option_value = remove_escape_chars(option_value)
                options[option_key] = option_value
        case QuestionType.填空题:
            answer = []
            options = []

            # 解析填空项和答案
            for blank_node in question_node.select("div.completionList.objectAuswerList"):
                options.append(blank_node.select_one("span.grayTit").text)
                answer.append(blank_node.select_one("textarea.blanktextarea").text)
        case QuestionType.判断题:
            # 解析答案
            match question_node.select_one("input[id^='answer']")["value"]:
                case "true":
                    answer = True
                case "false":
                    answer = False
                case _:
                    answer = None
        case _:
            raise NotImplementedError

    return QuestionModel(
        id=question_id,
        type=question_type,
        value=question_value,
        options=options,
        answer=answer,
    )


def construct_question_form(question: QuestionModel) -> dict[str, int | str]:
    """构建答题表单
    Args:
        question: 题目数据模型
    Retuerns:
        dict: 用于提交的题目表单
    不同类型的题目会生成 key-value 不同的表单
    """
    form = {
        f"type{question.id}": question.type.value,
        "questionId": question.id,
        f"typeName{question.id}": question.type.name,
        "hidetext": "",
    }
    match question.type:
        case QuestionType.单选题:
            form[f"answer{question.id}"] = question.answer
        case QuestionType.多选题:
            form[f"answers{question.id}"] = question.answer
        case QuestionType.填空题:
            blank_num = ""
            for i, value in enumerate(question.answer, 1):
                form[f"answer{question.id}{i}"] = value
                blank_num += f"{i},"
            form[f"blankNum{question.id}"] = blank_num
        case QuestionType.判断题:
            form[f"answer{question.id}"] = "true" if question.answer else "false"
        case _:
            raise NotImplementedError
    return form


class AnswerSheetComp:
    """答题卡显示组件"""

    answer_sheet: dict[str, dict[str, bool]]

    def __init__(self, answer_sheet: dict[str, dict[str, bool]]) -> None:
        self.answer_sheet = answer_sheet

    def __rich_console__(self, console: Console, options: ConsoleOptions) -> RenderResult:
        tb = Table(show_header=False, padding=(0, 0))
        for question_type, question_group in self.answer_sheet.items():
            cols = []
            for index, (qustion_num, status) in enumerate(question_group.items()):
                if index % 10 == 0:
                    col = Columns()
                col.add_renderable(
                    Text(
                        f"{qustion_num + 1:<2}",
                        style="bold green" if status else "white",
                    )
                )
                if index % 10 == 0:
                    cols.append(col)
            tb.add_row(question_type, Group(*cols))
            tb.add_section()
        yield tb


class ExamDto(QAQDtoBase):
    """课程考试客户端接口 (手机客户端协议)"""

    session: SessionWraper
    acc: AccountInfo
    logger: Logger

    exam_id: int  # 考试 id
    course_id: int  # 课程 id
    class_id: int  # 班级 id
    title: str  # 考试标题
    exam_student: str  # 考生信息
    cpi: int
    enc_task: int  # 考试校验 key
    exam_answer_id: int
    monitor_enc: str
    need_code: bool  # 是否要求考试码
    need_face: bool  # 是否要求人脸识别
    need_captcha: bool  # 是否要求人机验证码
    captcha_id: str # 人机验证码id
    captcha_validate: str   # 人机验证码结果
    enc: str  # 动态行为校验
    remain_time: int
    enc_remain_time: int
    last_update_time: int
    face_detection_result: dict  # 人脸识别结果
    face_key: str  # 人脸识别成功验证 Token

    tui_ctx: Layout

    def __init__(
        self,
        session: SessionWraper,
        acc: AccountInfo,
        exam_id: int,
        course_id: int,
        class_id: int,
        cpi: int,
        enc_task: str,
    ) -> None:
        self.logger = Logger("Exam")
        self.session = session
        self.acc = acc
        self.exam_id = exam_id
        self.course_id = course_id
        self.class_id = class_id
        self.cpi = cpi
        self.enc_task = enc_task

        self.exam_answer_id = 0
        self.monitor_enc = None
        self.need_code = False
        self.need_face = False
        self.need_captcha = False
        self.remain_time = 0
        self.enc = None
        self.enc_remain_time = 0
        self.last_update_time = 0
        self.title = None
        self.exam_student = None
        self.face_detection_result = None
        self.face_key = None
        self.captcha_id = ""
        self.captcha_validate = ""

        self.tui_ctx = Layout(name="Exam")

        super().__init__()

    def __str__(self) -> str:
        return f"<Exam id={self.exam_id} title='{self.title}' remainTime={self.remain_time_str}>"

    def __rich_console__(self, console: Console, options: ConsoleOptions) -> RenderResult:
        yield self.tui_ctx

    def __iter__(self):
        self.current_index = 0  # 复位索引计数器
        return self

    def refresh_tui(self) -> None:
        answer_sheet = self.get_answer_sheet()
        self.tui_ctx.update(
            Group(
                Text("考试标题：", end="", style="bold green"),
                Text(self.title),
                Text("考试 id：", end="", style="bold green"),
                Text(f"{self.exam_id}"),
                Text("考生信息：", end="", style="bold green"),
                Text(self.exam_student, style="italic blue"),
                Text("剩余时间：", end="", style="bold green"),
                Text(self.remain_time_str, style="yellow"),
                Text("最近操作时间：", end="", style="bold green"),
                Text(
                    datetime.fromtimestamp(self.last_update_time / 1000).strftime(
                        "%Y-%m-%d %H:%M:%S"
                    )
                ),
                Text("答题状态：", style="bold green"),
                AnswerSheetComp(answer_sheet),
            )
        )

    def __next__(self) -> tuple[int, QuestionModel]:
        """迭代返回
        Returns:
            int: 题目索引
            QuestionModel: 题目模型
        """
        try:
            question = self.fetch(self.current_index)
        except ExamInvalidParams:
            raise StopIteration
        else:
            index = self.current_index
            self.current_index += 1
            return index, question

    @property
    def remain_time_str(self) -> str:
        """获取剩余时间 (字符串形式)
        eg: 57:42
        Returns:
            str: 剩余时间
        """
        return f"{self.enc_remain_time // 60:02d}:{self.enc_remain_time % 60:02d}"

    def get_meta(self) -> None:
        """拉取封面元数据
        用于初始化必要参数, 需要在开始考试前执行
        """
        resp = self.session.get(
            PAGE_EXAM_COVER,
            params={
                "redo": 1,  # 强制跳过重新作答重定向
                "taskrefId": self.exam_id,  # 考试 id
                "courseId": self.course_id,
                "classId": self.class_id,
                "userId": self.acc.puid,
                "role": "",
                "source": 0,
                "enc_task": self.enc_task,
                "cpi": self.cpi,
                "vx": 0,
                "examsignal": 1,  # 强制跳过考试承诺书
            },
            allow_redirects=False,
        )
        resp.raise_for_status()

        # 考试已完成, 会重定向到结果页
        if resp.status_code == 302:
            if URL(resp.headers["Location"]).path == "/exam-ans/exam/phone/look":
                self.logger.error(f"考试已完成 (I.{self.exam_id})")
                raise ExamCompleted
            else:
                raise APIError

        html = BeautifulSoup(resp.text, "lxml")

        # 考试封面页报错信息解析
        if t := html.select_one("h2.color6.fs36.textCenter.marBom60.line64"):
            self.logger.error(f"获取考试失败 ({t.text}) (I.{self.exam_id})")
            if t.text == "考试尚未开始":
                raise ExamNotStart
            elif t.text.startswith("章节任务点未完成"):
                raise ChaptersNotComplete(t.text)
            elif t.text == "请使用指定的IP环境进行考试。":
                raise IPNotAllow
            elif t.text == "该试卷只允许在电脑考试客户端考试,完成考试后可在手机端查看":
                raise PCExamClintOnly
            else:
                raise ExamEnterError(t.text)

        # 进入考试封面页成功, 解析元数据
        self.exam_answer_id = int(html.select_one("input#testUserRelationId")["value"])
        self.monitor_enc = html.select_one("input#monitorEnc")["value"]
        self.title = html.select_one("span.overHidden2").text
        js_code = html.body.select_one("script").text
        self.need_code = bool(re.search(r"var *needcode *= *(\d+);", js_code).group(1))
        self.need_face = bool(html.select_one("input#faceRecognitionCompare")["value"])
        self.need_captcha = bool(html.select_one("input#captchaCheck")["value"])
        self.captcha_id = html.select_one("input#captchaCaptchaId")["value"]
        self.logger.info(f"获取考试成功 [{self.title}(I.{self.exam_id})]")

        # 解决人脸识别
        if self.need_face is True:
            self.logger.info(f"考试要求识别人脸 [{self.title}(I.{self.exam_id})]")
            self.__resolve_face_detection()

        # 解决人机验证码
        if self.need_captcha is True:
            self.logger.info(f"考试要求人机验证码 [{self.title}(I.{self.exam_id})]")
            self.__resolve_captcha(resp.url)

    def __resolve_face_detection(self):
        """解决人脸识别"""
        self.session.face_detection.get_upload_token()

        # 不知道为什么会上传两次
        object_id, _ = self.session.face_detection.upload_face_by_puid()
        object_id2, _ = self.session.face_detection.upload_face_by_puid()

        # 提交并比对人脸
        submit_result = self.session.face_detection.submit_face_exam(
            exam_id=self.exam_id,
            course_id=self.course_id,
            class_id=self.class_id,
            cpi=self.cpi,
            object_id=object_id,
        )

        # 生成人脸识别提交 Token 与 result 数据
        self.face_key = submit_result["facekey"]
        self.face_detection_result = {
            "collectedFaceId": submit_result["detail"]["collectObjectId"],
            "currentFaceId": submit_result["detail"]["faceObjectId"],
            "collectStatus": 1,
            "LiveDetectionStatus": 1,
            "extraData": {
                "a_eye": random.choices((-1, 0), (0.2, 0.8)),
                "a_score": 0,
                "f_extra": f"{random.randint(5000, 10000)}_0_-1_1_0",
                "ret": random.randint(100, 105),
                "s_objectId": object_id2,
                "s_score": random.randint(80000000, 99000000) / 1e8,
            },
            "ignoreLiveDetectionStatus": 1,
        }
        self.logger.debug(f"人脸识别数据: key={self.face_key} detail={self.face_detection_result}")

    def __resolve_captcha(self, referer: str):
        """解决人机验证码
        Args:
            referer(str): 验证码所在页面url
        """
        captcha = ImageCaptchaDto(
            session=self.session,
            referer=referer,
            captcha_id=self.captcha_id,
            type=ImageCaptchaType.SLIDE,
        )
        for cnt in range(3):
            captcha.get_server_time()
            shade_image, cutout_image = captcha.get_image()
            x_pos = fuck_slide_image_captcha(shade_image, cutout_image)
            try:
                self.captcha_validate = captcha.check_image([{"x": x_pos}])
                self.logger.debug(f"人机验证通过: validate={self.captcha_validate}")
                return
            except HandleCaptchaError:
                self.logger.debug(f"人机验证失败: cnt={cnt}")
                continue
        else:
            raise HandleCaptchaError("人机验证码处理失败")

    def start(self, code: str = None) -> QuestionModel:
        """开始考试
        Args:
            code: 考试码
        Return:
            QuestionModel: 第一题的题目数据模型
        """
        resp = self.session.get(
            API_START_START,
            params={
                "courseId": self.course_id,
                "classId": self.class_id,
                "examId": self.exam_id,
                "source": 0,
                "examAnswerId": self.exam_answer_id,
                "cpi": self.cpi,
                "keyboardDisplayRequiresUserAction": 1,
                "imei": get_imei(),
                "faceDetection": int(self.need_face),
                "facekey": (self.face_key if self.need_face else ""),
                "faceDetectionResult": (
                    json.dumps(self.face_detection_result, separators=(",", ":"))
                    if self.need_face
                    else ""
                ),
                "captchavalidate": self.captcha_validate,
                "jt": 0,
                "code": code or "",
            },
            allow_redirects=False,
        )
        resp.raise_for_status()

        if resp.status_code == 200:
            # 200 时可能为考试码错误
            html = BeautifulSoup(resp.text, "lxml")
            if t := html.select_one("p.blankTips,li.msg"):
                self.logger.error(f"开始考试错误 ({t.text}) [{self.title}(I.{self.exam_id})]")
                if t.text == "验证码错误！":
                    raise ExamCodeDenied(t.text)
                elif t.text == "人脸识别对比不通过，不允许进入考试":
                    raise FaceDetectionError(t.text)
                else:
                    raise ExamEnterError(t.text)
        elif resp.status_code == 302:
            # 302 时进入考试成功
            self.logger.info(f"开始考试成功 [{self.title}(I.{self.exam_id})]")
            redirect_url = resp.headers["Location"]
            self.logger.debug(f"redirect URL: {redirect_url}")
            query_params = URL(redirect_url).query
            self.enc = query_params["enc"]
            return self.fetch(0)  # 若成功返回第一道题
        else:
            raise APIError

    def get_answer_sheet(self):
        """获取当前答题卡状态
        Returns:
            dict: 题目序号-是否已答
        """
        resp = self.session.get(
            API_ANSWER_SHEET,
            params={
                "courseId": self.course_id,
                "classId": self.class_id,
                "source": 0,
                "start": 0,
                "cpi": self.cpi,
                "examRelationId": self.exam_id,
                "imei": get_imei(),
                "examRelationAnswerId": self.exam_answer_id,
                "remainTimeParam": self.enc_remain_time,
                "relationAnswerLastUpdateTime": self.last_update_time,
                "enc": self.enc,
            },
        )
        resp.raise_for_status()
        html = BeautifulSoup(resp.text, "lxml")
        sheet = {}
        # 遍历父节点 (题型)
        for sheet_father_node in html.select("ul"):
            type_name = re.search(
                r"[一二三四五六七八九].*、 *(?P<type_name>\S+)",
                sheet_father_node.select_one("h4.cardTit").text,
            ).group("type_name")
            # 遍历子节点 (题号+状态)
            sheet_son = {}
            for sheet_son_node in sheet_father_node.select("li"):
                index = int(sheet_son_node["data"])
                complated = "complated" in sheet_son_node["class"]
                sheet_son[index] = complated
            sheet[type_name] = sheet_son
        self.logger.info(f"获取答题卡状态成功 [{self.title}(I.{self.exam_id})]")
        self.logger.debug(f"答题卡状态: {sheet}")
        return sheet

    def fetch(self, index: int) -> QuestionModel:
        """拉取一道题
        Args:
            index: 题目索引 从 0 开始计数
        Returns:
            QuestionModel: 题目模型
        """
        resp = self.session.get(
            PAGE_EXAM_QUESTION,
            params={
                "courseId": self.course_id,
                "classId": self.class_id,
                # 考试 id
                "tId": self.exam_id,
                "id": self.exam_answer_id,
                "source": 0,
                "p": 1,
                "isphone": "true",
                # 计时触发标志, one shot 模式, 使用属性 enc_remain_time 是否为 0 来判断
                "tag": int(self.enc_remain_time == 0),
                "cpi": self.cpi,
                "imei": get_imei(),
                # 题目索引, 从 0 开始计数
                "start": index,
                "enc": self.enc,
                "keyboardDisplayRequiresUserAction": 1,
                "monitorStatus": 0,
                "monitorOp": -1,
                "remainTimeParam": self.enc_remain_time,
                "relationAnswerLastUpdateTime": self.last_update_time,
            },
        )
        resp.raise_for_status()
        html = BeautifulSoup(resp.text, "lxml")

        # 解析错误提示信息
        if t := html.body.select_one("p.blankTips"):
            self.logger.error(f"拉取题目 {index} 失败 ({t.text}) [{self.title}(I.{self.exam_id})]")
            if t.text == "考试已经提交":
                raise ExamIsCommitted
            elif t.text in (
                "无权限访问！",
                "当前用户账号发生异常，无法进行考试",
                "当前班级发生异常，无法进行考试",
            ):
                raise ExamAccessDenied(t.text)
            elif t.text == "无效参数！":
                raise ExamInvalidParams(t.text)
            else:
                raise ExamError(t.text)

        # 解析公共参数+单题表单
        self.exam_student = html.select_one("input#ExamWaterMark")["value"]
        submit_form = html.select_one("form#submitTest")
        self.enc = submit_form.select_one("input#enc")["value"]
        self.enc_remain_time = int(submit_form.select_one("input#encRemainTime")["value"])
        self.remain_time = int(submit_form.select_one("input#remainTime")["value"])
        self.last_update_time = int(submit_form.select_one("input#encLastUpdateTime")["value"])

        # 解析题目
        question_node = submit_form.select_one("div.questionWrap.singleQuesId.ans-cc-exam")
        question = parse_question(question_node)
        self.logger.info(f"拉取题目 {index} 成功 [{self.title}(I.{self.exam_id})]")
        self.logger.debug(f"题目 Content: {question.to_dict()}")
        self.refresh_tui()
        return question

    def fetch_all(self) -> list[QuestionModel]:
        """拉取整卷预览 (所有题目)
        Returns:
            list[QuestionModel]: 题目模型列表 (按题号顺序排列)
        """
        resp = self.session.get(
            PAGE_EXAM_PREVIEW,
            params={
                "courseId": self.course_id,
                "classId": self.class_id,
                "source": 0,
                "imei": get_imei(),
                "start": 0,
                "cpi": self.cpi,
                "examRelationId": self.exam_id,
                "examRelationAnswerId": self.exam_answer_id,
                "monitorStatus": 0,
                "monitorOp": -1,
                "remainTimeParam": self.enc_remain_time,
                "relationAnswerLastUpdateTime": self.last_update_time,
                "enc": self.enc,
            },
        )
        resp.raise_for_status()
        html = BeautifulSoup(resp.text, "lxml")

        # 解析错误提示信息
        if t := html.body.select_one("p.blankTips"):
            self.logger.error(f"整卷预览拉取失败 ({t.text}) [{self.title}(I.{self.exam_id})]")
            if t.text == "考试已经提交":
                raise ExamIsCommitted
            elif t.text in (
                "无权限访问！",
                "当前用户账号发生异常，无法进行考试",
                "当前班级发生异常，无法进行考试",
            ):
                raise ExamAccessDenied(t.text)
            else:
                raise ExamError(t.text)

        # 解析公共参数表单
        submit_form = html.body.select_one("form#submitTest")
        self.enc = submit_form.select_one("input#enc")["value"]
        self.enc_remain_time = int(submit_form.select_one("input#encRemainTime")["value"])
        self.remain_time = int(submit_form.select_one("input#remainTime")["value"])
        self.last_update_time = int(submit_form.select_one("input#encLastUpdateTime")["value"])

        # 解析题目列表
        question_nodes = html.body.select("div.questionWrap.singleQuesId.ans-cc-exam")
        questions = [parse_question(question_node) for question_node in question_nodes]
        self.logger.info(
            f"整卷预览拉取成功 (共 {len(questions)} 题) [{self.title}(I.{self.exam_id})]"
        )
        self.logger.debug(f"题目 list: {[question.to_dict() for question in questions]}")
        self.refresh_tui()
        return questions

    def submit(
        self,
        *,
        index: int = 0,
        question: QuestionModel | None = None,
        final: bool | None = False,
    ) -> dict:
        """提交答案或试卷
        Args:
            index: 题目索引
            question: 题目数据模型
            final: 是否交卷
        参数的 4 种 instance:
            如 final 为 True 时, index 和 question 同时存在则提交该题后直接交卷
            如 final 为 True 时, 不提供和 index 和 question 会直接交卷, 使用保存在服务器中的答案表单
            如 final 为 False 时, 需提供和 index 和 question, 做为当前考试 Session 的临时答案保存
            但 final 为 False 时, 如果不提供 index 和 question, 是毫无意义的非法请求
        Returns:
            dict: json 响应数据
        """
        self.logger.info(f"开始提交题目 ({index}) {question}")
        resp = self.session.post(
            API_SUBMIT_ANSWER,
            params={
                "classId": self.class_id,
                "courseId": self.course_id,
                "cpi": self.cpi,
                # 考试 id
                "testPaperId": self.exam_id,
                "testUserRelationId": self.exam_answer_id,
                # 是否交卷
                "tempSave": "false" if final is True else "true",
                # 计算提交签名参数集
                **get_exam_signature(
                    uid=self.acc.puid,
                    # 题目 id
                    qid=question.id if question else 0,
                    # 点击坐标
                    x=random.randint(100, 1000),
                    y=random.randint(100, 1000),
                ),
                # 题目 id
                "qid": question.id if question else "",
                "version": 1,
            },
            data={
                "courseId": self.course_id,
                "testPaperId": self.exam_id,
                "testUserRelationId": self.exam_answer_id,
                "classId": self.class_id,
                "type": 0,
                "isphone": "true",
                "imei": get_imei(),
                "subCount": "",
                "remainTime": self.remain_time,
                # 是否交卷
                "tempSave": "false" if final is True else "true",
                "timeOver": "false",
                "encRemainTime": self.enc_remain_time,
                "encLastUpdateTime": self.last_update_time,
                "enc": self.enc,
                "userId": self.acc.puid,
                "source": 0,
                # 题目序号, 如仅交卷不用提供
                "start": index,
                "enterPageTime": self.last_update_time,
                "monitorforcesubmit": 0,
                "answeredView": 0,
                "exitdtime": 0,
                # 合并答题表单, 如仅交卷不用提供
                **(construct_question_form(question) if question else {}),
            },
        )
        resp.raise_for_status()
        json_content = resp.json()
        self.logger.debug(f"提交 Resp: {json_content}")

        # 解析失败参数
        if (json_content.get("status")) != "success":
            if final is True:
                self.logger.error(
                    f"交卷失败 ({json_content.get('msg')}) [{self.title}(I.{self.exam_id})]"
                )
            else:
                self.logger.error(
                    f"提交失败 {index} ({json_content.get('msg')}) [{self.title}(I.{self.exam_id})]"
                )
            if json_content.get("msg") == "考试时间已用完,不允许提交答案!":
                raise ExamTimeout
            elif json_content.get("msg").endswith("分钟内不允许提交考试"):
                raise ExamSubmitTooEarly
            else:
                raise ExamSubmitError(json_content.get("msg"))

        # 非最终提交, 更新风控参数, 并刷新显示
        if final is False:
            enc_params = json_content["data"].split("|")
            self.last_update_time = int(enc_params[0])
            self.enc_remain_time = int(enc_params[1])
            self.enc = enc_params[2]
            self.refresh_tui()

        if final is True:
            self.logger.info(
                f"交卷成功 ({json_content.get('msg')}) [{self.title}(I.{self.exam_id})]"
            )
        else:
            self.logger.info(
                f"提交成功 {index} ({json_content.get('msg')}) [{self.title}(I.{self.exam_id})]"
            )
        return json_content

    def final_submit(self) -> dict:
        """直接交卷
        Returns:
            dict: json 响应数据
        """
        return self.submit(final=True)

    def fallback_save(self) -> dict:
        """保存答题信息
        考试接口不支持
        Returns:
            dict: 返回数据 (仅做展示)
        """
        self.refresh_tui()
        return {
            "status": True,
            "msg": "NotImplemented!",
        }

    def export(
        self,
        format_or_path: Literal["schema", "dict", "json"] | Path = "schema",
    ) -> QuestionsExportSchema | str | dict | None:
        """导出当前试题
        Args:
            format_or_path: 导出格式或路径
        """
        schema = QuestionsExportSchema(
            id=self.exam_id,
            title=self.title,
            type=QuestionsExportType.Exam,
            questions=self.fetch_all(),
        )
        self.logger.info(f"导出全部试题 ({format}) [{self.title}(I.{self.exam_id})]")
        if isinstance(format_or_path, Path):
            # 按路径导出
            with format_or_path.open("w", encoding="utf8") as fp:
                fp.write(schema.to_json(ensure_ascii=False, separators=(",", ":")))
        else:
            match format_or_path:
                case "schema":
                    return schema
                case "dict":
                    return schema.to_dict()
                case "json":
                    return schema.to_json(ensure_ascii=False, separators=(",", ":"))
                case _:
                    raise TypeError("未定义的导出类型")


__all__ = ["ExamDto"]
