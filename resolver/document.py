import time

from rich.console import Console, ConsoleOptions, RenderResult
from rich.json import JSON
from rich.layout import Layout
from rich.panel import Panel

from cxapi.exception import APIError
from cxapi.task_point import PointDocumentDto
from logger import Logger


class DocumetResolver:
    """文档阅读解决器"""

    logger: Logger
    document_dto: PointDocumentDto

    tui_ctx: Layout

    def __init__(
        self,
        document_dto: PointDocumentDto,
    ):
        """constructor
        Args:
            document_dto: 实例化的文档接口对象
        """
        self.logger = Logger("QuestionResolver")
        self.tui_ctx = Layout(name="Resolver")  # 当前类所属 TUI 的 ctx
        self.document_dto = document_dto

    def __rich_console__(self, console: Console, options: ConsoleOptions) -> RenderResult:
        yield self.tui_ctx

    def execute(self) -> None:
        """执行自动接管逻辑"""
        self.logger.info(f"开始完成文档阅读 {self.document_dto}")
        msg_console = Layout(name="Message", size=9)  # 信息显示窗口

        self.tui_ctx.split_column(
            Panel(
                f"模拟浏览：{self.document_dto.title}",
                title="正在模拟浏览",
            ),
            msg_console,
        )

        try:
            report_result = self.document_dto.report()
        except APIError as e:
            msg_console.update(
                Panel(
                    e.__str__(),
                    title="上报失败",
                    border_style="red",
                )
            )
        else:
            msg_console.update(
                Panel(
                    JSON.from_data(
                        report_result,
                        ensure_ascii=False,
                    ),
                    title="上报成功",
                    border_style="green",
                )
            )
        time.sleep(1.0)


__all__ = ["DocumetResolver"]
