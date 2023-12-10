from typing import Literal, Optional

import jsonpath
import requests
from bs4 import BeautifulSoup
from rich import json

from cxapi.schema import QuestionModel
from . import SearcherBase, SearcherResp


class RestApiSearcher(SearcherBase):
    """UrlQuery REST API 在线搜索器"""

    session: requests.Session
    q_field: str
    o_field: list[str] | None
    a_query: jsonpath.JSONPath
    url: str
    method: Literal["GET", "POST"]

    def __init__(
        self,
        url,
        q_field: str = "question",  # 题目文本字段
        o_field: Optional[str] = None,  # 选项字段
        a_field: str = "$.data",  # 答案字段 使用 jsonpath 语法
        headers: Optional[dict] = None,  # 自定义头部
        ext_params: Optional[dict] = None,  # 扩展请求字段
        method: Literal["GET", "POST"] = "POST",  # 请求方式
    ) -> None:
        self.session = requests.Session()
        self.url = url
        self.method = method
        if headers:
            self.session.headers.update(headers)
        self.q_field = q_field
        self.o_field = o_field
        self.rsp_query = jsonpath.compile(a_field)
        self.ext_params = ext_params or {}

    def parse(self, json_content: dict | list) -> SearcherResp:
        if result := self.rsp_query.parse(json_content):
            return SearcherResp(0, "ok", self, self.question_value, result[0])
        return SearcherResp(-500, "未匹配答案字段", self, self.question_value, None)

    def invoke(self, question: QuestionModel) -> SearcherResp:
        self.question_value = question.value
        params = {self.q_field: self.question_value, **self.ext_params}
        if self.o_field and question.options and isinstance(question.options, dict):
            params[self.o_field] = "#".join(question.options.values())
        try:
            if self.method == "GET":
                resp = self.session.get(
                    self.url,
                    params=params,
                )
            elif self.method == "POST":
                resp = self.session.post(
                    self.url,
                    data=params,
                )
            else:
                raise TypeError
            resp.raise_for_status()
            return self.parse(resp.json())
        except Exception as err:
            return SearcherResp(-500, err.__str__(), self, self.question_value, None)


class JsonApiSearcher(SearcherBase):
    """JSON REST API 在线搜索器"""

    session: requests.Session
    q_field: str
    o_field: Optional[str]
    a_query: jsonpath.JSONPath
    url: str

    def __init__(
        self,
        url,
        q_field: str = "question",  # 题目文本字段
        o_field: Optional[str] = None,  # 选项字段
        a_field: str = "$.data",  # 答案字段 使用 jsonpath 语法
        headers: Optional[dict] = None,  # 自定义头部
        ext_params: Optional[dict] = None,  # 扩展请求字段
    ) -> None:
        self.question: str | None = None
        self.session = requests.Session()
        self.url = url
        if headers:
            self.session.headers.update(headers)
        self.q_field = q_field
        self.o_field = o_field
        self.rsp_query = jsonpath.compile(a_field)
        self.ext_params = ext_params or {}

    def invoke(self, question: QuestionModel) -> SearcherResp:
        self.question = question.value
        payload = {
            self.q_field: self.question,
            "type": question.type.value,
            "id": question.id,
            **self.ext_params,
        }
        if question.options is not None:
            if self.o_field and question.options and isinstance(question.options, dict):
                payload[self.o_field] = "#".join(question.options.values())
            else:
                payload["options"] = question.options
        try:
            resp = self.session.post(
                self.url,
                json=payload,
            )
            resp.raise_for_status()
            return self.parse(resp.json())
        except Exception as err:
            return SearcherResp(-500, err.__str__(), self, self.question, None)

    def parse(self, json_content: dict | list) -> SearcherResp:
        if result := self.rsp_query.parse(json_content):
            return SearcherResp(0, "ok", self, self.question, result[0])
        return SearcherResp(-500, "未匹配答案字段", self, self.question, None)


class EnncySearcher(RestApiSearcher):
    """Enncy 题库搜索器"""

    def __init__(self, token: str) -> None:
        super().__init__(
            url="https://tk.enncy.cn/query",
            method="GET",
            ext_params={
                "v": 1,
                "token": token,
            },
            q_field="title",
            a_field="$.data.answer",
        )

    def parse(self, json_content: dict) -> SearcherResp:
        parse_result = self.rsp_query.parse(json_content)
        if "".join(parse_result) in (
            "很抱歉, 题目搜索不到。",
            "非常抱歉，题目搜索不到。",
        ):
            return SearcherResp(-404, "搜索失败", self, self.question_value, None)
        if "".join(parse_result) in (
            "配置为空或者配置错误，请自行检查或者联系作者查看。",
            "题库配置的“凭证”被刷新，不要刷新你的凭证！只有当你的题库被别人盗用时才能进行刷新操作，否则会导致题库配置失效，请您前往 https://tk.enncy.cn/ "
            "登录后到个人中心复制题库配置，并重新在脚本设置中粘贴题库配置。",
        ):
            return SearcherResp(-403, "Token无效", self, self.question_value, None)
        if parse_result:
            return SearcherResp(0, "ok", self, self.question_value, parse_result[0])
        return SearcherResp(-500, "未匹配答案字段", self, self.question_value, None)


class CxSearcher(RestApiSearcher):
    """网课小工具(Go题)题库搜索器"""

    def __init__(self, token: str) -> None:
        super().__init__(
            url="https://cx.icodef.com/wyn-nb",
            method="POST",
            q_field="question",
            headers={
                "Content-Type": "application/x-www-form-urlencoded",
                "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/113.0.0.0 Safari/537.36 Edg/113.0.1774.35",
                "Authorization": token,
            },
            ext_params={
                "v": 4,
            },
            a_field="$.data",
        )

    def parse(self, json_content: dict) -> SearcherResp:
        if jsonpath.compile("$.code").parse(json_content)[0] != 1:
            return SearcherResp(-404, "搜索失败", self, self.question_value, None)
        if result := self.rsp_query.parse(json_content):
            return SearcherResp(0, "ok", self, self.question_value, result[0])
        return SearcherResp(-500, "未匹配答案字段", self, self.question_value, None)


class TiKuHaiSearcher(JsonApiSearcher):
    """题库海在线搜索器"""

    token: str

    def __init__(self, token: str) -> None:
        super().__init__(
            url="http://api.tikuhai.com/search",
            headers={
                "Host": "api.tikuhai.com",  # 缺少无法搜索
                "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/117.0.0.0 Safari/537.36 Edg/117.0.2045.60",
                "referer": "https://mooc1.chaoxing.com",
                "Content-Type": "application/json",  # 缺少无法搜索
            },
            a_field="$.data.answer",
            ext_params={
                "key": token,
            },
        )

    def parse(self, json_content: dict | list) -> SearcherResp:
        if jsonpath.compile("$.code").parse(json_content)[0] != 200:
            if jsonpath.compile("$.msg").parse(json_content):
                soup = BeautifulSoup(jsonpath.compile("$.msg").parse(json_content)[0], "lxml")
                msg = soup.find_all("a")
                if msg:
                    return SearcherResp(
                        -1,
                        "搜索失败,付费库:" + str(msg[0].text) + "请前往购买" + str(msg[1].attrs["href"]),
                        self,
                        self.question,
                        None,
                    )
            return SearcherResp(-404, "搜索失败", self, self.question, None)
        if result := self.rsp_query.parse(json_content):
            return SearcherResp(0, "ok", self, self.question, result[0][0])
        return SearcherResp(-500, "未匹配答案字段", self, self.question, None)


class MukeSearcher(JsonApiSearcher):
    """Muke在线搜索器"""

    def __init__(self) -> None:
        super().__init__(
            url="https://api.muketool.com/cx/v2/query",
            headers={
                "Host": "api.muketool.com",
                "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/117.0.0.0 Safari/537.36 Edg/117.0.2045.60",
                "Content-Type": "application/json",
            },
            a_field="$.data",
        )

    def parse(self, json_content: dict | list) -> SearcherResp:
        if jsonpath.compile("$.code").parse(json_content)[0] != 1:
            return SearcherResp(-404, "搜索失败", self, self.question, None)
        if result := self.rsp_query.parse(json_content):
            return SearcherResp(0, "ok", self, self.question, result[0][0])
        return SearcherResp(-500, "未匹配答案字段", self, self.question, None)


class LyCk6Searcher(JsonApiSearcher):
    """冷月题库搜索器"""

    def __init__(self, token: str, gpt: int) -> None:
        if token is None or len(token) != 10:
            super().__init__(
                url="https://lyck6.cn/scriptService/api/autoFreeAnswer",
                headers={
                    "Content-Type": "application/json",
                },
                a_field="$.result.answers[0][0]",
            )
        else:
            super().__init__(
                url="https://lyck6.cn//scriptService/api/autoAnswer/" + token + "?gpt=" + str(gpt),
                headers={
                    "Content-Type": "application/json",
                },
                a_field="$.result.answers[0][0]",
            )

    @staticmethod
    def code_to_err(num):
        numbers = {
            403: "请不要挂梯子或使用任何网络代理工具",
            444: "您请求速率过大,IP已经被封禁,请等待片刻或者更换IP",
            415: "请不要使用手机运行此脚本，否则可能出现异常",
            429: "免费题库搜题整体使用人数突增,系统繁忙,请耐心等待或使用付费题库...",
            500: "服务器发生预料之外的错误",
            502: "运维哥哥正在火速部署服务器,请稍等片刻,1分钟内恢复正常",
            503: "搜题服务不可见,请稍等片刻,1分钟内恢复正常",
            504: "系统超时",
        }
        return numbers.get(num, None)

    def parse(self, json_content: dict) -> SearcherResp:
        code = jsonpath.compile("$.code").parse(json_content)[0]
        if code != 0:
            return SearcherResp(code, self.code_to_err(code), self, self.question, None)
        if result := self.rsp_query.parse(json_content):
            return SearcherResp(0, "ok", self, self.question, result[0])
        return SearcherResp(-500, "未匹配答案字段", self, self.question, None)


class LemonSearcher(JsonApiSearcher):
    """柠檬题库搜索器"""

    def __init__(self, token: str) -> None:
        super().__init__(
            url="https://api.lemtk.xyz/api/v1/mcx",
            headers={
                "Authorization": "Bearer " + token,
                "Content-Type": "application/json",
                "User-Agent": "CxKitty",
            },
            ext_params={
                "v": "1.0",
                "uid": "703382225",
            },
            q_field="question",
            a_field="$.data.answer",
        )

    def parse(self, json_content: dict) -> SearcherResp:
        code = jsonpath.compile("$.code").parse(json_content)[0]
        if code != 1000:
            msg = jsonpath.compile("$.msg").parse(json_content)[0]
            return SearcherResp(-403, msg, self, self.question, None)
        if result := self.rsp_query.parse(json_content):
            return SearcherResp(0, "ok", self, self.question, result[0])
        return SearcherResp(-500, "未匹配答案字段", self, self.question, None)


__all__ = [
    "RestApiSearcher",
    "JsonApiSearcher",
    "EnncySearcher",
    "CxSearcher",
    "TiKuHaiSearcher",
    "MukeSearcher",
    "LyCk6Searcher",
    "LemonSearcher",
]
