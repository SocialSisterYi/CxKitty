import json
import sqlite3
from pathlib import Path
from typing import Literal
import difflib
import requests


class SearcherBase:
    def __init__(self) -> None:
        pass
    
    def invoke(self, question_value: str) -> tuple[dict, str]:
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
    req: str
    rsp: str
    def __init__(self, url, method: Literal['GET', 'POST']='POST', req: str='question', rsp: str='data') -> None:
        self.session = requests.Session()
        self.url = url
        self.method = method
        self.req = req
        self.rsp = rsp
    
    def invoke(self, question_value: str) -> tuple[dict, str]:
        try:
            if self.method == 'GET':
                resp = self.session.get(self.url, params={self.req: question_value})
            elif self.method == 'POST':
                resp = self.session.post(self.url, data={self.req: question_value})
            else:
                raise TypeError
            resp.raise_for_status()
            return resp.json(), self.rsp
        except Exception as err:
            return {'code': -1, 'error': f'{err.__str__()}'}, self.rsp

class JsonFileSearcher(SearcherBase):
    db: dict[str, str]
    def __init__(self, file_path: Path) -> None:
        with open(file_path, 'r', encoding='utf8') as fp:
            self.db = json.load(fp)
    
    def invoke(self, question_value: str) -> tuple[dict, str]:
        for q, a in self.db.items():
            # 遍历题库缓存并判断相似度
            if difflib.SequenceMatcher(a=q, b=question_value).ratio() >= 0.8:
                return {'code': 1, 'question': q, 'data': a}, 'data'
        else:
            return {'code': -1, 'error': '题目未匹配'}, 'data'

class SqliteSearcher(SearcherBase):
    db: sqlite3.Connection
    req: str
    rsp: str
    table: str
    
    def __init__(self, file_path: Path, table: str='question', req: str='question', rsp: str='answer') -> None:
        self.db = sqlite3.connect(file_path)
        self.table = table
        self.req = req
        self.rsp = rsp
        
    def invoke(self, question_value: str):
        try:
            cur = self.db.execute(f'SELECT {self.req},{self.rsp} FROM {self.table} WHERE {self.req}=(?)', (question_value,))
            q, a = cur.fetchone()
            return {'code': 1, 'question': q, 'data': a}, self.rsp
        except Exception as err:
            return {'code': -1, 'error': f'{err.__str__()}'}, self.rsp

__all__ = ['SearcherBase', 'RestAPISearcher', 'JsonFileSearcher', 'SqliteSearcher']