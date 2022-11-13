import urllib.parse
from hashlib import md5

def calc_infenc(params: dict) -> str:
    '计算infenc hash参数'
    query = urllib.parse.urlencode(params) + '&DESKey=Z(AfY@XS'
    return md5(query.encode()).hexdigest()