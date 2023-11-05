from dataclasses import dataclass
from typing import Optional

from cxapi.schema import QuestionModel
from logger import Logger


@dataclass
class SearcherResp:
    """搜索器返回协议"""

    code: int  # 错误代码
    message: str  # 错误信息
    searcher: "SearcherBase"  # 搜索器对象
    question: str  # 源题干信息
    answer: Optional[str]  # 答案

    def __repr__(self) -> str:
        return f"SearchResp(code={self.code}, message={self.message}, searcher={self.searcher}, question={self.question}, answer={self.answer})"


class SearcherBase:
    """搜索器基类"""

    def invoke(self, question: QuestionModel) -> SearcherResp:
        """搜题器调用接口
        >>> SearchResp(
        >>>     code=0,  # 错误码为 0 表示成功, 否则为失败
        >>>     message=ok,  # 错误信息, 默认为 ok
        >>>     question=题目,
        >>>     answer=答案
        >>> )
        """
        raise NotImplementedError


class MultiSearcherWraper:
    """搜索器封装
    可用于多搜索器同时搜索
    """

    slot: list[SearcherBase]  # 搜索器槽位
    logger: Logger  # 日志记录器

    def __init__(self) -> None:
        self.logger = Logger("Searcher")
        self.slot = []

    def add(self, searcher: SearcherBase) -> None:
        """添加搜索器
        Args:
            searcher: 欲添加的搜索器对象
        """
        if not isinstance(searcher, SearcherBase):
            raise TypeError
        self.slot.append(searcher)

    def invoke(self, question: QuestionModel) -> list[SearcherResp]:
        """调用搜索器
        Args:
            question: 题目数据模型
        Returns:
            list[SearchResp]: 搜索器响应列表, 可为多个搜索器搜索到的结果
        """
        if not self.slot:
            raise RuntimeError("至少需要加载一个搜索器")
        result = [searcher.invoke(question) for searcher in self.slot]
        self.logger.info(f"搜索器调用成功 (共 {len(result)} 个结果)")
        self.logger.debug(f"搜索器 Req={question} Rsp={result}")
        return result


__all__ = ["SearcherResp", "SearcherBase", "MultiSearcherWraper"]
