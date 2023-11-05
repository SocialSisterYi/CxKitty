import difflib
import json
from pathlib import Path

from cxapi.schema import QuestionModel

from . import SearcherBase, SearcherResp


def filter_suffix(text: str) -> str:
    "过滤题目的各种符号后缀"
    return text.strip("()（）.。?？")


class JsonFileSearcher(SearcherBase):
    "JSON 数据库搜索器"
    db: dict[str, str]

    def __init__(self, file_path: Path | str) -> None:
        try:
            with open(file_path, "r", encoding="utf8") as fp:
                self.db = json.load(fp)
        except FileNotFoundError:
            raise RuntimeError("JSON 题库文件无效, 请检查配置")

    def invoke(self, question: QuestionModel) -> SearcherResp:
        for q, a in self.db.items():
            # 遍历题库缓存并判断相似度
            if (
                difflib.SequenceMatcher(a=filter_suffix(q), b=filter_suffix(question.value)).ratio()
                >= 0.9
            ):
                return SearcherResp(0, "ok", self, q, a)
        return SearcherResp(-404, "题目未匹配", self, question.value, None)


__all__ = ["JsonFileSearcher"]
