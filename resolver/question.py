import difflib
import random
import re
import secrets
import time
from functools import lru_cache
from typing import Callable, List, Optional

from rich import errors
from rich.align import Align
from rich.console import Console, ConsoleOptions, Group, RenderableType, RenderResult
from rich.json import JSON
from rich.layout import Layout
from rich.panel import Panel
from rich.protocol import is_renderable
from rich.style import StyleType
from rich.styled import Styled
from rich.table import Column, Row, Table
from rich.text import Text

import config
from cxapi.base import QAQDtoBase
from cxapi.exception import APIError
from cxapi.schema import QuestionModel, QuestionsExportSchema, QuestionsExportType, QuestionType
from logger import Logger

from .searcher import MultiSearcherWraper, SearcherResp

from .searcher.json import JsonFileSearcher
from .searcher.openai import OpenAISearcher
from .searcher.restapi import (
    CxSearcher,
    EnncySearcher,
    RestApiSearcher,
    TiKuHaiSearcher,
    LyCk6Searcher,
    MukeSearcher,
    JsonApiSearcher,
    LemonSearcher,
)
from .searcher.sqlite import SqliteSearcher

# 所有的搜索器类
SEARCHERS = {
    "JsonFileSearcher": JsonFileSearcher,
    "CxSearcher": CxSearcher,
    "EnncySearcher": EnncySearcher,
    "RestApiSearcher": RestApiSearcher,
    "SqliteSearcher": SqliteSearcher,
    "TiKuHaiSearcher": TiKuHaiSearcher,
    "LyCk6Searcher": LyCk6Searcher,
    "MukeSearcher": MukeSearcher,
    "JsonApiSearcher": JsonApiSearcher,
    "LemonSearcher": LemonSearcher,
    "OpenAISearcher": OpenAISearcher,
}


@lru_cache(maxsize=128)
def load_searcher() -> MultiSearcherWraper:
    """加载搜索器实例 缓存最终加载结果
    Returns:
        MultiSearcherWraper: 多搜索器封装
    """
    searcher = MultiSearcherWraper()
    # 检查题库后端配置
    if not config.SEARCHERS:
        raise AttributeError("请先配置题库后端再运行，如不需要使用答题功能请修改config.yml进行关闭。")
    # 按需实例化并添加搜索器
    for searcher_conf in config.SEARCHERS:
        typename = searcher_conf["type"]
        typename = typename[0].upper() + typename[1:]
        if typename not in SEARCHERS:
            raise AttributeError(f'Searcher "{typename}" not found')
        del searcher_conf["type"]
        # 动态加载搜索器类
        searcher.add(SEARCHERS[typename](**searcher_conf))

    return searcher


class MyTable(Table):
    def push_row(
        self,
        *renderables: Optional["RenderableType"],
        style: Optional[StyleType] = None,
    ) -> None:
        """向表格顶部插入行"""

        def add_cell(column: Column, renderable: "RenderableType") -> None:
            column._cells.insert(0, renderable)

        cell_renderables: List[Optional["RenderableType"]] = list(renderables)

        columns = self.columns
        if len(cell_renderables) < len(columns):
            cell_renderables = [
                *cell_renderables,
                *[None] * (len(columns) - len(cell_renderables)),
            ]
        for index, renderable in enumerate(cell_renderables):
            if index == len(columns):
                column = Column(_index=index)
                for _ in self.rows:
                    add_cell(column, Text(""))
                self.columns.append(column)
            else:
                column = columns[index]
            if renderable is None:
                add_cell(column, "")
            elif is_renderable(renderable):
                add_cell(column, renderable)
            else:
                raise errors.NotRenderableError(
                    f"unable to render {type(renderable).__name__}; a string or other renderable object is required"
                )
        self.rows.insert(0, Row(style=style))


class SearchRespShowComp:
    """搜索结果展示组件
    用于 TUI 显示
    """

    question: QuestionModel  # 题目
    results: list[SearcherResp]  # 搜索返回

    def __init__(self, question: QuestionModel, results: list[SearcherResp]) -> None:
        self.question = question
        self.results = results

    def __rich_console__(self, console: Console, options: ConsoleOptions) -> RenderResult:
        """rich 渲染接口"""
        yield Group(Text("q: ", end=""), Text(self.question.value, style="cyan"))
        for result in self.results:
            yield Group(
                Text("a: ", end=""),
                Styled(
                    Group(
                        Text(f"{result.searcher.__class__.__name__}", end=" "),
                        Text(
                            "Ok" if result.code == 0 else f"Err {result.code}:{result.message}",
                            end="",
                        ),
                        Text(" -> " if result.code == 0 else "", end=""),
                    ),
                    style="green" if result.code == 0 else "red",
                ),
                Text(result.answer, style="cyan", overflow="ellipsis") if result.code == 0 else "",
            )


class QuestionResolver:
    """题目解决器
    用于 拉取-搜索-填充-提交 工作流的自动接管
    """

    searcher: MultiSearcherWraper  # 搜索器
    logger: Logger  # 日志记录器
    exam_dto: QAQDtoBase  # 实例化的答题接口对象
    enable_fallback_save: bool  # 是否失败时保存
    enable_fallback_fuzzer: bool  # 是否答案匹配失败时随机填充
    persubmit_delay: float  # 每次提交的延迟
    auto_final_submit: bool  # 是否自动交卷
    cb_confirm_submit: Callable[[int, int, list, QAQDtoBase], bool]  # 交卷确认回调函数

    tui_ctx: Layout

    mistakes: list[tuple[QuestionModel, str]]  # 答错题列表
    completed_cnt: int  # 已答题计数
    incompleted_cnt: int  # 未答题计数
    finish_flag: bool  # 答题完毕标志

    def __init__(
        self,
        exam_dto: QAQDtoBase,
        fallback_save: bool = True,
        fallback_fuzzer: bool = False,
        persubmit_delay: float = 1.0,
        auto_final_submit: bool = True,
        cb_confirm_submit: Callable[[int, int, list, QAQDtoBase], bool] = None,
    ) -> None:
        """constructor
        Args:
            exam_dto: 答题接口对象
            fallback_save: 是否失败时保存
            fallback_fuzzer: 是否答案匹配失败时随机填充
            persubmit_delay: 每次提交的延迟
            auto_final_submit: 是否自动交卷
            cb_confirm_submit： 交卷确认回调函数(completed_cnt, incompleted_cnt, mistakes, exam_dto)
        """
        self.logger = Logger("QuestionResolver")
        self.exam_dto = exam_dto
        self.enable_fallback_save = fallback_save
        self.enable_fallback_fuzzer = fallback_fuzzer
        self.persubmit_delay = persubmit_delay
        self.auto_final_submit = auto_final_submit
        self.cb_confirm_submit = cb_confirm_submit
        self.searcher = load_searcher()  # 从配置文件加载搜索器

        self.tui_ctx = Layout(name="Resolver")  # 当前类所属 TUI 的 ctx
        self.mistakes = []
        self.completed_cnt = 0
        self.incompleted_cnt = 0
        self.finish_flag = False

    def __rich_console__(self, console: Console, options: ConsoleOptions) -> RenderResult:
        yield self.tui_ctx

    def fill(self, question: QuestionModel, search_results: list[SearcherResp]) -> bool:
        "查询并填充对应选项"
        self.logger.debug(f"开始填充题目 {question}")
        # 遍历多个搜索器返回以适配结果
        for result in search_results:
            if result.code != 0 or result.answer is None:
                continue
            search_answer = result.answer.strip()
            match question.type:
                case QuestionType.单选题:
                    for k, v in question.options.items():
                        if difflib.SequenceMatcher(a=v, b=search_answer).ratio() >= 0.95:
                            question.answer = k
                            self.logger.debug(f"单选题命中 {k}={v}")
                            return True
                case QuestionType.判断题:
                    if re.search(r"(错|否|错误|false|×)", search_answer):
                        question.answer = False
                        self.logger.debug(f"判断题命中 true")
                        return True
                    elif re.search(r"(对|是|正确|true|√)", search_answer):
                        question.answer = True
                        self.logger.debug(f"判断题命中 false")
                        return True
                case QuestionType.多选题:
                    option_lst = []
                    if len(part_answer_lst := search_answer.split("#")) <= 1:
                        part_answer_lst = search_answer.split(";")
                    for part_answer in part_answer_lst:
                        for k, v in question.options.items():
                            if v == part_answer:
                                option_lst.append(k)
                                self.logger.debug(f"多选题命中 {k}={v}")
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
                case _:
                    self.logger.warning(f"未实现的题目类型 {question.type.name}/{question.type.value}")
                    return False

        # 如匹配失败, 则 fallback 到 fuzzer 填充
        if self.enable_fallback_fuzzer is True:
            match question.type:
                case QuestionType.单选题 | QuestionType.多选题:
                    question.answer = random.choice(list(question.options.keys()))
                    self.logger.warning(f"选择题 fuzzer 填充 {question}")
                    return True
                case QuestionType.判断题:
                    question.answer = bool(random.randint(0, 1))
                    self.logger.warning(f"判断题 fuzzer 填充 {question}")
                    return True
                case QuestionType.填空题:
                    question.answer = [
                        secrets.token_urlsafe() for _ in range(len(question.options))
                    ]
                    self.logger.warning(f"填空题 fuzzer 填充 {question}")
                case _:
                    self.logger.warning(f"不支持 fuzzer 填充 {question}")
                    return False

        self.logger.warning(f"填充失败")
        return False

    def logging_mistake(self) -> None:
        """记录错题到日志"""
        incomplete_msg = []

        incomplete_msg.append(f"\n-----*共 {self.incompleted_cnt} 题未完成*-----")
        for index, (q, a) in enumerate(self.mistakes, 1):
            incomplete_msg.append(f"{index}.\tq({q.type.name}/{q.type.value}): {q.value}")
            if q.type in (QuestionType.单选题, QuestionType.多选题):
                incomplete_msg.append("\to: " + " ".join(f"{a}={o}" for a, o in q.options.items()))
            incomplete_msg.append(f"\ta: {a}")
        incomplete_msg.append("------------")

        self.logger.warning("\n".join(incomplete_msg))

    def save_mistake(self) -> None:
        """保存错题到文件"""
        schema = QuestionsExportSchema(
            id=0,
            title=self.exam_dto.title,
            type=QuestionsExportType.Mistakes,
            questions=[q for q, a in self.mistakes],
        )
        export_path = config.EXPORT_PATH / f"mistakes_{int(time.time())}.json"
        with export_path.open("w", encoding="utf8") as fp:
            fp.write(schema.to_json(ensure_ascii=False, separators=(",", ":")))

    def reg_confirm_submit_cb(self, cb: Callable[[int, int, list, QAQDtoBase], bool]):
        """注册提交确认函数"""
        self.cb_confirm_submit = cb
        return cb

    def execute(self) -> None:
        """执行自动接管逻辑"""
        self.logger.info(f"开始完成试题 {self.exam_dto}")
        msg_console = Layout(name="Message", size=9)  # 信息显示窗口

        # 答题可视化信息表格
        tb = MyTable(
            "题号 / id",
            "类型",
            "题目",
            "答案",
            expand=True,
            border_style="yellow",
        )
        self.tui_ctx.split_column(tb, msg_console)

        def refresh_title():
            "构建表格标题"
            title = []
            if self.finish_flag is True:
                if self.incompleted_cnt == 0:
                    title.append("[bold green]答题完毕[/]")
                else:
                    title.append(f"[bold red]有 {self.incompleted_cnt} 道错题[/]")
            else:
                title.append("[yellow]答题中[/]")
            title.append(self.exam_dto.title)
            title.append(f"[green]{self.completed_cnt}[/]/[red]{self.incompleted_cnt}")

            tb.title = "  ".join(title)

        refresh_title()
        # 迭代答题接口, 遍历所有题目
        for index, question in self.exam_dto:
            # 调用搜索器
            results = self.searcher.invoke(question)

            # 显示搜索器返回
            msg_console.update(
                Panel(
                    SearchRespShowComp(question, results),
                    title="搜索器返回",
                )
            )

            # 填充选项
            status = self.fill(question, results)
            tb.push_row(
                f"[green]{index + 1}[/] ({question.id})",
                question.type.name,
                question.value,
                (f"[green]{question.answer}" if status else "[red]未匹配"),
            )

            # 记录错题
            if status == False:
                self.incompleted_cnt += 1
                self.mistakes.append((question, "/".join(str(result.answer) for result in results)))
            else:
                self.completed_cnt += 1
            refresh_title()

            # 单题提交
            time.sleep(self.persubmit_delay)  # 提交延迟
            try:
                result = self.exam_dto.submit(index=index, question=question)
            except APIError as e:
                self.logger.warning(
                    f"题目提交失败 -> {e.__class__.__name__} {e.__str__()} " f"[{self.exam_dto}]"
                )
                msg_console.update(
                    Panel(
                        f"{e.__class__.__name__} {e.__str__()}", title="提交失败！", border_style="red"
                    )
                )
            else:
                self.logger.info(f"提交成功 [{self.exam_dto}]")
                msg_console.update(
                    Panel(
                        JSON.from_data(result, ensure_ascii=False),
                        title="题目提交成功 QwQ！",
                        border_style="green",
                    )
                )
            time.sleep(1.0)

        # 答题完毕处理
        self.finish_flag = True

        # 没有错误
        if self.incompleted_cnt == 0:
            refresh_title()
            tb.border_style = "green"

            # 不自动交卷, 即退出工作流
            if not self.auto_final_submit:
                return

            # 交卷确认不通过, 即退出工作流
            if self.cb_confirm_submit is not None:
                if not self.cb_confirm_submit(
                    self.completed_cnt,
                    self.incompleted_cnt,
                    self.mistakes,
                    self.exam_dto,
                ):
                    return

            # 提交试题
            try:
                result = self.exam_dto.final_submit()
            except APIError as e:
                self.logger.warning(
                    f"试题交卷失败 -> {e.__class__.__name__} {e.__str__()} [{self.exam_dto}]"
                )
                msg_console.update(
                    Panel(
                        f"{e.__class__.__name__} {e.__str__()}",
                        title="交卷失败！",
                        border_style="red",
                    )
                )
            else:
                self.logger.info(f"交卷成功 [{self.exam_dto}]")
                msg_console.update(
                    Panel(
                        JSON.from_data(result, ensure_ascii=False),
                        title="交卷成功 QAQ！",
                        border_style="green",
                    )
                )

        # 存在错误
        else:
            refresh_title()
            tb.border_style = "red"
            msg_console.update(
                Panel(
                    Align.center(
                        f"[red]{self.incompleted_cnt} 道试题未完成, 请查看日志了解详情"
                        + (", 即将临时保存！" if self.enable_fallback_save else "！"),
                        vertical="middle",
                    ),
                    title="试题未完成",
                    highlight=False,
                    style="red",
                )
            )
            self.logger.warning(f"试题未完成 [{self.exam_dto}]")
            self.logging_mistake()
            self.save_mistake()
            time.sleep(5.0)

            # 临时保存未完成的试卷
            if self.enable_fallback_save is True:
                try:
                    result = self.exam_dto.fallback_save()
                except APIError as e:
                    self.logger.warning(
                        f"试题保存失败 -> {e.__class__.__name__} {e.__str__()} [{self.exam_dto}]"
                    )
                    msg_console.update(
                        Panel(
                            f"{e.__class__.__name__} {e.__str__()}",
                            title="保存失败！",
                            border_style="red",
                        )
                    )
                else:
                    self.logger.info(f"试题保存成功 [{self.exam_dto}]")
                    msg_console.update(
                        Panel(
                            JSON.from_data(result, ensure_ascii=False),
                            title="保存成功 TAT！",
                            border_style="green",
                        )
                    )

        time.sleep(5.0)


__all__ = ["QuestionResolver"]
