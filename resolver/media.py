import time

from rich.align import Align
from rich.console import (
    Console,
    ConsoleOptions,
    RenderResult
)
from rich.json import JSON
from rich.layout import Layout
from rich.panel import Panel
from rich.progress import Progress

from cxapi.exception import APIError
from cxapi.jobs.video import PointVideoDto
from logger import Logger


class MediaPlayResolver:
    """媒体播放解决器
    用于 媒体播放心跳上报 的自动接管
    """
    logger: Logger              # 日志记录器
    media_dto: PointVideoDto    # 实例化的媒体接口对象
    speed: float                # 播放倍速
    report_rate: int            # 播放汇报率
    duration: int               # 媒体长度
    
    tui_ctx: Layout
    
    def __init__(
        self,
        media_dto: PointVideoDto,
        speed: float = 1.0,
        report_rate: int = 58
    ) -> None:
        """constructor
        Args:
            media_dto: 实例化的媒体接口对象
            speed: 播放倍速
            report_rate: 播放汇报率
        """
        self.logger = Logger("MediaPlayResolver")
        self.media_dto = media_dto
        self.speed = speed
        self.report_rate = report_rate
        self.duration = self.media_dto.duration
        
        self.tui_ctx = Layout(name="Resolver")  # 当前类所属 TUI 的 ctx
    
    def __rich_console__(self, console: Console, options: ConsoleOptions) -> RenderResult:
        yield self.tui_ctx
    
    def execute(self) -> None:
        """执行自动接管逻辑
        """
        s_counter = self.report_rate        # 上报计时器
        playing_time = 0                    # 当前播放时间
        progress = Progress()
        info = Layout()
        self.tui_ctx.split_column(
            info, Panel(progress, title=f"模拟播放视频[green]《{self.media_dto.title}》[/]", border_style="yellow")
        )
        bar = progress.add_task("playing...", total=self.duration)

        def _update_bar():
            "更新进度条"
            progress.update(
                bar,
                completed=playing_time,
                description=f"playing... [blue]{playing_time // 60:02d}:{playing_time % 60:02d}[/blue] [yellow]{self.report_rate - s_counter}s后汇报[/yellow](X{self.speed})",
            )

        self.logger.info(
            f"开始播放 倍速=x{self.speed} 汇报率={self.report_rate}s "
            f"[{self.media_dto}]"
        )
        while True:
            if s_counter >= self.report_rate or playing_time >= self.duration:
                s_counter = 0
                try:
                    report_result = self.media_dto.play_report(playing_time)
                except APIError as e:
                    info.update(Panel(e.__str__(), title="上报失败", border_style="red"))
                else:
                    info.update(
                        Panel(
                            JSON.from_data(
                                report_result,
                                ensure_ascii=False,
                            ),
                            title="上报成功",
                            border_style="green",
                        )
                    )
                    if report_result.get("isPassed") == True:
                        playing_time = self.duration  # 强制100%, 解决强迫症
                        self.logger.info(f"播放完毕")
                        _update_bar()
                        info.update(
                            Panel(
                                Align.center(
                                    "OHHHHHHHH",
                                    vertical="middle",
                                ),
                                title="播放完毕",
                                border_style="green",
                            )
                        )
                        time.sleep(5.0)
                        break
            playing_time += round(1 * self.speed)
            s_counter += round(1 * self.speed)
            _update_bar()
            time.sleep(1.0)

__all__ = ["MediaPlayResolver"]
