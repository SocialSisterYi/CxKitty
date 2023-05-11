import difflib
import json
import sqlite3
from dataclasses import dataclass
from pathlib import Path
from typing import Literal, Optional, Union

import jsonpath
import requests


@dataclass
class SearchResp:
    "搜索器返回"
    code: int  # 错误代码
    message: str  # 错误信息
    searcher: "SearcherBase"  # 搜索器对象
    question: str  # 源题干信息
    answer: Optional[str]  # 答案

    def __repr__(self) -> str:
        return f"SearchResp(code={self.code}, message={self.message}, searcher={self.searcher}, question={self.question}, answer={self.answer})"


def suffix_filter(text: str) -> str:
    "过滤题目的各种符号后缀"
    return text.strip("()（）.。?？")


class SearcherBase:
    "搜索器基类"

    def invoke(self, question_value: str) -> SearchResp:
        """搜题器调用接口
        >>> SearchResp(
        >>>     code=0,  # 错误码为 0 表示成功, 否则为失败
        >>>     message=ok,  # 错误信息, 默认为 ok
        >>>     question=题目,
        >>>     answer=答案
        >>> )
        """
        raise NotImplementedError


class RestApiSearcher(SearcherBase):
    "REST API 在线搜索器"
    session: requests.Session
    req_field: str
    rsp_query: jsonpath.JSONPath
    url: str
    method: Literal["GET", "POST"]

    def __init__(
        self,
        url,
        req_field: str = "question",  # 请求字段
        rsp_field: str = "$.data",  # 答案字段 使用 jsonpath 语法
        headers: Optional[dict] = None,  # 自定义头部
        ext_params: Optional[dict] = None,  # 扩展请求字段
        method: Literal["GET", "POST"] = "POST",  # 请求方式
    ) -> None:
        self.session = requests.Session()
        self.url = url
        self.method = method
        if headers:
            self.session.headers.update(headers)
        self.req_field = req_field
        self.rsp_query = jsonpath.compile(rsp_field)
        self.ext_params = ext_params or {}

    def parse(self, json_content: dict | list) -> SearchResp:
        if result := self.rsp_query.parse(json_content):
            return SearchResp(0, "ok", self, self.question_value, result[0])
        return SearchResp(-500, "未匹配答案字段", self, self.question_value, None)

    def invoke(self, question_value: str) -> SearchResp:
        self.question_value = question_value
        try:
            if self.method == "GET":
                resp = self.session.get(
                    self.url,
                    params={self.req_field: self.question_value, **self.ext_params},
                )
            elif self.method == "POST":
                resp = self.session.post(
                    self.url,
                    data={self.req_field: self.question_value, **self.ext_params},
                )
            else:
                raise TypeError
            resp.raise_for_status()
            return self.parse(resp.json())
        except Exception as err:
            return SearchResp(-500, err.__str__(), self, question_value, None)


class EnncySearcher(RestApiSearcher):
    "Enncy 题库搜索器"

    def __init__(self, token: str) -> None:
        super().__init__(
            url="https://tk.enncy.cn/query",
            method="GET",
            ext_params={"v": 1, "token": token},
            req_field="title",
            rsp_field="$.data.answer",
        )

    def parse(self, json_content: dict) -> SearchResp:
        if "".join(jsonpath.compile("$.data.answer").parse(json_content)) == "很抱歉, 题目搜索不到。":
            return SearchResp(-404, "搜索失败", self, self.question_value, None)
        if "".join(jsonpath.compile("$.data.answer").parse(json_content)) in (
            "配置为空或者配置错误，请自行检查或者联系作者查看。",
            "题库配置的“凭证”被刷新，不要刷新你的凭证！只有当你的题库被别人盗用时才能进行刷新操作，否则会导致题库配置失效，请您前往 https://tk.enncy.cn/ 登录后到个人中心复制题库配置，并重新在脚本设置中粘贴题库配置。",
        ):
            return SearchResp(-403, "Token无效", self, self.question_value, None)
        if result := self.rsp_query.parse(json_content):
            return SearchResp(0, "ok", self, self.question_value, result[0])
        return SearchResp(-500, "未匹配答案字段", self, self.question_value, None)

class cxSearcher(RestApiSearcher):
    "网课小工具(Go题)题库搜索器"

    def __init__(self, token: str) -> None:
        super().__init__(
            url="https://cx.icodef.com/wyn-nb?v=4",
            method="POST",
            req_field="question",
            headers={"Content-Type": "application/x-www-form-urlencoded",
                     "Authorization": token},
            rsp_field="$.data",
        )

    def parse(self, json_content: dict) -> SearchResp:
        if jsonpath.compile("$.code").parse(json_content)[0] != 1:
            return SearchResp(-404, "搜索失败", self, self.question_value, None)
        if result := self.rsp_query.parse(json_content):
            return SearchResp(0, "ok", self, self.question_value, result[0])
        return SearchResp(-500, "未匹配答案字段", self, self.question_value, None)

class JsonFileSearcher(SearcherBase):
    "JSON 数据库搜索器"
    db: dict[str, str]

    def __init__(self, file_path: Union[Path, str]) -> None:
        try:
            with open(file_path, "r", encoding="utf8") as fp:
                self.db = json.load(fp)
        except FileNotFoundError:
            raise RuntimeError("JSON 题库文件无效, 请检查配置")

    def invoke(self, question_value: str) -> SearchResp:
        for q, a in self.db.items():
            # 遍历题库缓存并判断相似度
            if (
                difflib.SequenceMatcher(a=suffix_filter(q), b=suffix_filter(question_value)).ratio()
                >= 0.9
            ):
                return SearchResp(0, "ok", self, q, a)
        return SearchResp(-404, "题目未匹配", self, question_value, None)


class SqliteSearcher(SearcherBase):
    "SQLite 数据库搜索器"
    db: sqlite3.Connection
    table: str
    rsp_field: str

    def __init__(
        self,
        file_path: Union[Path, str],
        req_field: str = "question",
        rsp_field: str = "answer",
        table: str = "question",
    ) -> None:
        self.db = sqlite3.connect(file_path)
        self.table = table
        self.req_field = req_field
        self.rsp_field = rsp_field

    def invoke(self, question_value: str) -> SearchResp:
        try:
            cur = self.db.execute(
                f"SELECT {self.req_field},{self.rsp_field} FROM {self.table} WHERE {self.req_field}=(?)",
                (question_value,),
            )
            q, a = cur.fetchone()
            return SearchResp(0, "ok", self, q, a)
        except Exception as err:
            return SearchResp(-500, err.__str__(), self, question_value, None)


__all__ = [
    "SearcherBase",
    "RestApiSearcher",
    "JsonFileSearcher",
    "SqliteSearcher",
    "EnncySearcher",
    "cxSearcher"
]