import base64
import re

import lxml.html
import requests
import requests.utils
from Crypto.Cipher import AES
from Crypto.Util.Padding import pad

from .classes import Classes
from .exceptions import APIError

API_LOGIN_WEB = 'https://passport2.chaoxing.com/fanyalogin'                      # 接口-web端登录
API_QRCREATE = 'https://passport2.chaoxing.com/createqr'                         # 接口-激活二维码key并返回二维码图片
API_QRLOGIN = 'https://passport2.chaoxing.com/getauthstatus'                     # 接口-web端二维码登录
API_CLASS_LST = 'https://mooc1-api.chaoxing.com/mycourse/backclazzdata'          # 接口-课程列表
PAGE_ACCINFO = 'https://passport2.chaoxing.com/mooc/accountManage'               # SSR页面-登录信息
PAGE_LOGIN = 'https://passport2.chaoxing.com/login'                              # SSR页面-登录 用于提取二维码key

UA_MOBILE = 'Dalvik/2.1.0 (Linux; U; Android 12; M2102K1C Build/SKQ1.211006.001) Language/zh_CN com.chaoxing.mobile/ChaoXingStudy_3_6.0.5_android_phone_899_99'
UA_WEB = 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/107.0.0.0 Safari/537.36 Edg/107.0.1418.35'

class ChaoXingAPI:
    '学习通爬虫主类'
    session: requests.Session
    # 二维码登录用
    qr_uuid: str
    qr_enc: str
    # 账号个人信息
    puid: int  # 用户 puid
    name: str  # 真实姓名
    sex: str  # 性别
    phone: str  # 手机号
    schools: list  # 单位列表
    
    def __init__(self) -> None:
        self.session = requests.Session()
        # 默认使用 APP 的 UA, 因为一些接口为 APP 独占
        self.session.headers['User-Agent'] = UA_MOBILE
        self.schools = []

    def ck_load(self, ck: dict[str, str]) -> None:
        '加载dict格式的ck'
        requests.utils.add_dict_to_cookiejar(self.session.cookies, ck)
    
    def ck_dump(self) -> dict[str, str]:
        '输出ck为dict'
        return requests.utils.dict_from_cookiejar(self.session.cookies)
        
    def login_passwd(self, unmae: str, passwd: str) -> tuple[bool, dict]:
        '以web方式使用手机号+密码账号'
        key = b'u2oh6Vu^HWe4_AES'
        # 开始加密参数
        cryptor = AES.new(key, AES.MODE_CBC, key)
        unmae = base64.b64encode(cryptor.encrypt(pad(unmae.encode(), 16))).decode()
        cryptor = AES.new(key, AES.MODE_CBC, key)
        passwd = base64.b64encode(cryptor.encrypt(pad(passwd.encode(), 16))).decode()
        
        resp = self.session.post(API_LOGIN_WEB, data={
            'fid': -1,
            'uname': unmae,
            'password': passwd,
            't': 'true',
            'forbidotherlogin': 0,
            'validate': '',
        })
        resp.raise_for_status()
        content_json = resp.json()
        if content_json['status'] != True:
            return False, content_json
        return True, content_json
    
    def qr_get(self) -> None:
        '获取二维码登录key'
        self.session.cookies.clear()
        resp = self.session.get(PAGE_LOGIN,
            headers={
                'User-Agent': UA_WEB  # 这里不可以用移动端UA否则鉴权失败
            }
        )
        resp.raise_for_status()
        root = lxml.html.fromstring(resp.content)
        self.qr_uuid = root.xpath("//div//input[@id='uuid']/@value")[0]
        self.qr_enc = root.xpath("//input[@id='enc']/@value")[0]
        
        # 激活qr但忽略返回的图片bin
        resp = self.session.get(API_QRCREATE, params={
            'uuid': self.qr_uuid,
            'fid': -1
        })
        resp.raise_for_status()
    
    def qr_geturl(self) -> str:
        '合成二维码内容url'
        return f'https://passport2.chaoxing.com/toauthlogin?uuid={self.qr_uuid}&enc={self.qr_enc}&xxtrefer=&clientid=&type=0&mobiletip='
    
    def login_qr(self) -> dict:
        '使用二维码登录'
        resp = self.session.post(API_QRLOGIN, data={
            'enc': self.qr_enc,
            'uuid': self.qr_uuid
        })
        resp.raise_for_status()
        content_json = resp.json()
        return content_json
    
    def accinfo(self) -> bool:
        '获取登录用户信息 同时判断ck有效'
        resp = self.session.get(PAGE_ACCINFO)
        resp.raise_for_status()
        root = lxml.html.fromstring(resp.content)
        # 开始解析数据
        if x:= root.xpath("//p[@id='uid']/text()"):  # 获取 puid 同时判定 session 的有效性
            self.puid = int(x[0])
            self.name = root.xpath("//p[@id='messageName']/text() | //span[@id='messageName']/text()")[0]  # 获取姓名
            self.sex = root.xpath("//p[contains(@class,'sex')]/span/text()")[0].strip()  # 获取性别
            self.phone = root.xpath("//span[@id='messagePhone']/text()")[0]  # 获取手机号
            for sch in root.xpath("//ul[@class='listCon']/li"):  # 获取单位列表
                school_name = sch.xpath("text()")[0].strip()
                if (r := re.search(r'(\d+)', sch.xpath("p[@class='xuehao']/text()")[0])) is not None:
                    student_id = int(r.group(1))
                else:
                    student_id = None
                self.schools.append((school_name, student_id))
            return True
        return False
    
    def fetch_classes(self) -> Classes:
        '拉取课程'
        resp = self.session.get(API_CLASS_LST)
        resp.raise_for_status()
        content_json = resp.json()
        if content_json['result'] != 1:
            raise APIError
        return Classes(
            session=self.session,
            puid=self.puid,
            classes_lst=content_json['channelList']
        )
    
__all__ = ['ChaoXingAPI']