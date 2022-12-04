import base64

import requests
import requests.utils
from bs4 import BeautifulSoup
from Crypto.Cipher import AES
from Crypto.Util.Padding import pad

from logger import Logger

from . import APIError, get_ua
from .classes import Classes
from .schema import AccountInfo

API_LOGIN_WEB = 'https://passport2.chaoxing.com/fanyalogin'                      # 接口-web端登录
API_QRCREATE = 'https://passport2.chaoxing.com/createqr'                         # 接口-激活二维码key并返回二维码图片
API_QRLOGIN = 'https://passport2.chaoxing.com/getauthstatus'                     # 接口-web端二维码登录
API_CLASS_LST = 'https://mooc1-api.chaoxing.com/mycourse/backclazzdata'          # 接口-课程列表
API_SSO_LOGIN = 'https://sso.chaoxing.com/apis/login/userLogin4Uname.do'         # 接口-SSO二步登录
PAGE_LOGIN = 'https://passport2.chaoxing.com/login'                              # SSR页面-登录 用于提取二维码key


class ChaoXingAPI:
    '学习通爬虫主类'
    logger: Logger
    session: requests.Session
    acc: AccountInfo
    # 二维码登录用
    qr_uuid: str
    qr_enc: str
    
    def __init__(self) -> None:
        self.logger = Logger('MainAPI')
        self.session = requests.Session()
        # 默认使用 APP 的 UA, 因为一些接口为 APP 独占
        self.session.headers.update({
            'User-Agent': get_ua('mobile'),
            'X-Requested-With': 'com.chaoxing.mobile'
        })

    def ck_load(self, ck: dict[str, str]) -> None:
        '加载dict格式的ck'
        requests.utils.add_dict_to_cookiejar(self.session.cookies, ck)
    
    def ck_dump(self) -> dict[str, str]:
        '输出ck为dict'
        return requests.utils.dict_from_cookiejar(self.session.cookies)
        
    def login_passwd(self, uname: str, passwd: str) -> tuple[bool, dict]:
        '以web方式使用手机号+密码账号'
        self.logger.set_loginfo(uname)
        key = b'u2oh6Vu^HWe4_AES'
        # 开始加密参数
        cryptor = AES.new(key, AES.MODE_CBC, key)
        uname = base64.b64encode(cryptor.encrypt(pad(uname.encode(), 16))).decode()
        cryptor = AES.new(key, AES.MODE_CBC, key)
        passwd = base64.b64encode(cryptor.encrypt(pad(passwd.encode(), 16))).decode()
        
        resp = self.session.post(API_LOGIN_WEB, data={
            'fid': -1,
            'uname': uname,
            'password': passwd,
            't': 'true',
            'forbidotherlogin': 0,
            'validate': '',
        })
        resp.raise_for_status()
        json_content = resp.json()
        if json_content['status'] != True:
            self.logger.warning(f'密码登录失败 {json_content}')
            return False, json_content
        self.logger.debug('密码登录成功')
        return True, json_content
    
    def qr_get(self) -> None:
        '获取二维码登录key'
        self.session.cookies.clear()
        resp = self.session.get(PAGE_LOGIN,
            headers={'User-Agent': get_ua('web')}  # 这里不可以用移动端 UA 否则鉴权失败
        )
        resp.raise_for_status()
        html = BeautifulSoup(resp.text, 'lxml')
        self.qr_uuid = html.find('input', id='uuid')['value']
        self.qr_enc = html.find('input', id='enc')['value']
        
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
        resp = self.session.get(API_SSO_LOGIN)
        resp.raise_for_status()
        json_content = resp.json()
        if json_content['result'] == 0:
            return False
        # 开始解析数据
        self.acc = AccountInfo(
            puid=json_content['msg']['puid'],
            name=json_content['msg']['name'],
            sex=['女', '男'][json_content['msg']['sex']],
            phone=json_content['msg']['phone'],
            school=json_content['msg']['schoolname'],
            stu_id=json_content['msg']['uname']
        )
        self.logger.set_loginfo(self.acc.phone)
        self.logger.info(f"账号会话验证成功 {' '.join(f'{k}={v}' for k, v in self.acc.__dict__.items())}")
        return True
    
    def fetch_classes(self) -> Classes:
        '拉取课程'
        resp = self.session.get(API_CLASS_LST)
        resp.raise_for_status()
        content_json = resp.json()
        if content_json['result'] != 1:
            self.logger.error(f"课程列表拉取失败")
            raise APIError
        self.logger.info(f"课程列表拉取成功 共 {len(content_json['channelList'])} 个")
        return Classes(
            session=self.session,
            acc=self.acc,
            classes_lst=content_json['channelList']
        )
    
__all__ = ['ChaoXingAPI']