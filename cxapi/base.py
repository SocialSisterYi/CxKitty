from pathlib import Path
from typing import Literal

from .schema import QuestionModel, QuestionsExportSchema


class QAQDtoBase:
    """答题接口基类
    用于定义 问题-回答-查询 类的各种 trait
    """
    current_index: int              # 当前题目索引 用于迭代
    title: str                      # 标题
    
    def __init__(self) -> None:
        self.current_index = 0

    def __iter__(self):
        self.fetch_all()    # 刷新提单缓存
        self.current_index = 0
        return self
    
    def __next__(self) -> tuple[int, QuestionModel]:
        """迭代返回
        Returns:
            int, QuestionModel: 题目索引 题目模型
        """
        raise NotImplemented
        
    def fetch(self, index: int) -> QuestionModel:
        """拉取一道题
        Args:
            index: 题目索引 从 0 开始计数
        Returns:
            QuestionModel: 题目模型
        """
        raise NotImplementedError
    
    def fetch_all(self) -> list[QuestionModel]:
        """拉取全部题单
        Returns:
            list[QuestionModel]: 题目模型列表 (按题号顺序排列)
        """
        raise NotImplementedError
    
    def submit(
        self, *, 
        index: int=0,
        question: QuestionModel,
        **kwargs
    ) -> dict:
        """提交试题
        Args:
            index: 题目索引
            question: 题目数据模型
        """
        raise NotImplementedError
    
    def final_submit(self) -> dict:
        """直接交卷
        """
        raise NotImplementedError
    
    def fallback_save(self) -> dict:
        """临时保存试题
        """
        raise NotImplementedError
    
    def export(
        self,
        format_or_path: Literal["schema", "dict", "json"] | Path = "schema"
    ) -> QuestionsExportSchema | str | dict | None:
        """导出当前试题
        Args:
            format_or_path: 导出格式或路径
        """
        raise NotImplementedError

__all__ = ["QAQDtoBase"]
