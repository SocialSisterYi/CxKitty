import difflib
import json
import sqlite3
from pathlib import Path
from typing import Literal, Union

import jsonpath
import requests


def suffix_filter(text: str) -> str:
    '过滤题目的各种符号后缀'
    return text.strip('()（）.。?？')

class SearcherBase:
    '搜索器基类'
    req_field: str  # 请求字段
    rsp_query: jsonpath.JSONPath  # 返回字段选择器
    
    def __init__(self, req_field: str='question', rsp_field: str='$.data') -> None:
        self.req_field = req_field
        self.rsp_query = jsonpath.compile(rsp_field)
    
    def invoke(self, question_value: str) -> dict:
        """
        搜题器调用接口
        规定第一个返回值结果dict
        >>> {
        >>>     'code': 1,  # 响应code 1为成功, 其他值为失败
        >>>     'data': '答案',
        >>>     'question': '题目',
        >>>     'err': '错误信息'
        >>> },
        >>> 'data'  # 规定第二个返回值为结果中的答案字段名
        >>>
        """
        raise NotImplementedError


class RestAPISearcher(SearcherBase):
    session: requests.Session
    url: str
    method: Literal['GET', 'POST']
    
    def __init__(self, url, req_field: str, rsp_field: str, method: Literal['GET', 'POST']='POST') -> None:
        self.session = requests.Session()
        self.url = url
        self.method = method
        super().__init__(req_field, rsp_field)
    
    def invoke(self, question_value: str) -> dict:
        try:
            if self.method == 'GET':
                resp = self.session.get(self.url, params={self.req_field: question_value})
            elif self.method == 'POST':
                resp = self.session.post(self.url, data={self.req_field: question_value})
            else:
                raise TypeError
            resp.raise_for_status()
            return resp.json()
        except Exception as err:
            return {'code': -1, 'error': f'{err.__str__()}'}

class JsonFileSearcher(SearcherBase):
    db: dict[str, str]
    
    def __init__(self, file_path: Union[Path, str]) -> None:
        try:
            with open(file_path, 'r', encoding='utf8') as fp:
                self.db = json.load(fp)
        except FileNotFoundError:
            raise RuntimeError('JSON 题库文件无效, 请检查配置')
        super().__init__('', '$.data')
    
    def invoke(self, question_value: str) -> dict:
        for q, a in self.db.items():
            # 遍历题库缓存并判断相似度
            if difflib.SequenceMatcher(
                a=suffix_filter(q),
                b=suffix_filter(question_value)
            ).ratio() >= 0.9:
                return {'code': 1, 'question': q, 'data': a}
        return {'code': -1, 'error': '题目未匹配'}

class SqliteSearcher(SearcherBase):
    db: sqlite3.Connection
    table: str
    rsp_field: str
    
    def __init__(self, file_path: Union[Path, str], req_field: str, rsp_field: str, table: str='question') -> None:
        self.db = sqlite3.connect(file_path)
        self.table = table
        self.rsp_field = rsp_field
        super().__init__(req_field, '$.data')
        
    def invoke(self, question_value: str) -> dict:
        try:
            cur = self.db.execute(f'SELECT {self.req_field},{self.rsp_field} FROM {self.table} WHERE {self.req_field}=(?)', (question_value,))
            q, a = cur.fetchone()
            return {'code': 1, 'question': q, 'data': a}
        except Exception as err:
            return {'code': -1, 'error': f'{err.__str__()}'}

__all__ = ['SearcherBase', 'RestAPISearcher', 'JsonFileSearcher', 'SqliteSearcher']