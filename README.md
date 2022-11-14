<div align="center">
    <h1>超星学习通答题姬</h1>
    <h2>CxKitty</h2>
    <img alt="Github Stars" src="https://img.shields.io/github/stars/SocialSisterYi/CxKitty">
    <img alt="Github Forks" src="https://img.shields.io/github/forks/SocialSisterYi/CxKitty">
    <img alt="Lines of code" src="https://img.shields.io/tokei/lines/github/SocialSisterYi/CxKitty">
    <img alt="Github License" src="https://img.shields.io/github/license/SocialSisterYi/CxKitty">
</div>

本项目旨在研究学习爬虫技术和网络接口编程技术，同时致力于以开源方式抵制并消灭各种付费“刷课平台”和“黑产”

效果演示视频 https://www.bilibili.com/video/BV1yt4y1P7NF

## Features

### 支持的功能

- ✅支持手机号+密码登录、二维码登录
- ✅自带多会话管理器，自动获取用户信息，以 json 格式存档在本地
- ✅Terminal-UI 方式进行人机交互，展示任务进程、任务点状态
- ✅视频课程任务点模拟播放
- ✅章节测验任务点自动答题，支持单选题、多选题、判断题
- ✅支持`REST API`、`JSON`、`SQLite`三种类型的题库

### 暂不支持的功能

以下特性有可能逐渐被添加

- ❌短信验证码登录、学号登录
- ❌文件任务点（如 word ppt pdf 等）
- ❌直播任务点、文章阅读任务点、课程考试
- ❌章节测验任务点简答题
- ❌保存未完成的章节测验任务点
- ❌多题库搜索器实例混用及负载均衡
- ❌记录错题到日志

### 已知存在 BUG 的功能

- ⭕获取任务点状态会出现 `0/0`的情况 (即使任务点存在未做)
- ⭕拉取试题有概率出现权限无效情况

## Typographical

![](imgs/typo.png)

## Build Repo

### 本地化构建项目

使用 Python 版本 >= 3.10.0

clone 项目到本地，并使用 poetry 安装依赖和管理 venv

```bash
git clone 'https://github.com/SocialSisterYi/CxKitty'
cd CxKitty
poetry install
```

运行主程序

```bash
poetry run python3 main.py
```

### 使用  Docker  构建项目

clone 项目到本地，并开始构建 Docker 镜像

```bash
git clone 'https://github.com/SocialSisterYi/CxKitty'
cd CxKitty
docker build --tag cx_kitty .
```

运行容器

```bash
docker run -it \
  --name shuake_task1 \
  -v "$PWD/session:/app/session" \
  -v "$PWD/config.yml:/app/config.yml" \  # 程序配置文件
  #-v "$PWD/questions.json:/app/questions.json" \  # json题库 (根据配置文件修改路径映射)
  #-v "$PWD/questions.db:/app/questions.db" \  # sqlite题库 (根据配置文件修改路径映射)
  cx_kitty
```

## Configuration

配置文件使用 Yaml 语法编写，存放于 [config.yml](config.yml)

```yaml
multiSession: true  # 是否开启多会话模式
sessionPath: "session/"  # 会话存档路径
maskAcc: true  # 是否开启姓名手机号打码
tUIMaxHeight: 20  # TUI 最大显示高度

# 视频
video:
  enable: true  # 是否执行任务
  speed: 1.0  # 播放速度
  wait: 15  # 完成等待时间
  report_rate: 58  # 视频播放汇报率 (没事别改)

# 试题
exam:
  enable: true  # 是否执行任务
  wait: 15  # 完成等待时间
  #fail_save: true  # 是否匹配失败自动保存 (未实现)

# 搜索器
searcher:
  use: "jsonFileSearcher"  # 当前选择的搜索器
  # REST API 在线搜题
  restApiSearcher:
    url: "http://127.0.0.1:88/cx/v1"  # API url
    method: "POST"  # 请求方式
    req: "question"  # 请求参数
    rsp: "data"  # 返回参数
  # 本地 JSON 数据库搜索器 (key为题, value为答案)
  jsonFileSearcher:
    path: "questions.json"  # 数据库文件路径
  # 本地 sqlite 数据库搜索器
  sqliteSearcher:
    parh: "questions.db"  # 数据库文件路径
    table: "question"  # 表名
    req: "question"  # 请求字段
    rsp: "answer"  # 返回字段
```

### 题库配置

单选题问题与答案应当一一对应，多选题使用`#`或`;`分隔每个选项，判断题答案只能为`对`、`错`、`正确`、`错误`、`√`、`×`

REST API 搜题接口配置，确保接口`searcher->restApiSearcher->url`可以正确访问访问（如使用 Docker 搭建，宿主主机运行服务，则应使用宿主机虚拟网关 IP 地址而不是回环地址）

eg：

```bash
curl 'http://127.0.0.1:88/cx/v1' \
  --data-urlencode 'question=国字的演变的过程告诉我们,国防就是国家的防务,国防与()是密不可分的'  #  这里`question`为请求字段名
```

```json
{
    "code": 1,
    "question": "国字的演变的过程告诉我们,国防就是国家的防务,国防与()是密不可分的",
    "data": "国家",  // 这里的`data`为响应字段名
    "hit": true
}
```

JSON 题库，确保`searcher->jsonFileSearcher->file`可以访问（使用 Docker 需要设置映射），key 为题目，value 为与之对应的答案

eg：

```json
{
  "国字的演变的过程告诉我们,国防就是国家的防务,国防与()是密不可分的": "国家"
}
```

SQLite 题库，确保`searcher->sqliteSearcher->file`可以访问（使用 Docker 需要设置映射），表中应存在配置的请求和响应字段

eg：

```sql
SELECT answer FROM questions WHERE question = '国字的演变的过程告诉我们,国防就是国家的防务,国防与()是密不可分的';
```

```
国家
```

## Using & Demo

**注：本项目非“开箱即用”，如需使用自动答题功能，请确保拥有准确无误的题库资源**

当配置文件和题库资源无误后，运行主程序，进行选择会话存档

若少于一个会话存档，则需要进行账号登录

![](imgs/demo1.png)

按照提示输入序号选择目标课程

![](imgs/demo2.png)

程序会自动完成视频及测验任务点，并展示章节任务点情况

![](imgs/demo3.png)

## About Repo Name

项目的中文名`超星学习通答题姬`早已确定，英文名想到过`CxHime`、`CxExamHime`、`CxCourseHime`然而都非常拗口，故弃用

又想到`CxHelper`这个名，但`helper`一词易使人联想到木马病毒可执行程序的文件名，很不吉利

最后由`CxKit`衍生出`CxKitty`这个名，一语双关`kitty`自有“猫娘”含义，~~同时由于项目首字母缩写是`cxk`，亦可解释为`答题只因`~~

## Disclaimers

- 本项目以 [GPL-3.0 License](https://github.com/SocialSisterYi/CxKitty/blob/main/LICENSE) 作为开源协议，这意味着你需要遵守相应的规则
- 本项目仅适用于**学习研究**，任何人不得以此用于**盈利**
- 使用本项目造成的任何后果与本人无关

## Link Repos

[Samueli924/chaoxing: 超星学习通/超星尔雅/泛雅超星全自动无人值守完成任务点 (github.com)](https://github.com/Samueli924/chaoxing)

[RainySY/chaoxing-xuexitong-autoflush: 超星学习通全自动无人值守视频刷课程序，使用协议发包来实现。 (github.com)](https://github.com/RainySY/chaoxing-xuexitong-autoflush)

[lyj0309/chaoxing-xuexitong-autoflush: 超星学习通全自动无人值守刷课程序，使用协议发包来实现，无需浏览器，支持自动过测验、过视频。 (github.com)](https://github.com/lyj0309/chaoxing-xuexitong-autoflush)

[chettoy/FxxkStar: API and unofficial client for the SuperStar mooc platform | 超星学习通的API和非官方客户端脚本，为学生提供更好的学习体验 (github.com)](https://github.com/chettoy/FxxkStar)

[ocsjs/ocsjs: OCS 网课助手，网课脚本，帮助大学生解决网课难题 ，目前支持网课：超星学习通，知道智慧树 ， 支持脚本猫以及油猴脚本运行。 (github.com)](https://github.com/ocsjs/ocsjs)

[SocialSisterYi/xuexiaoyi-to-xuexitong-tampermonkey-proxy: 基于“学小易”搜题API的学习通答题/考试油猴脚本题库代理 (github.com)](https://github.com/SocialSisterYi/xuexiaoyi-to-xuexitong-tampermonkey-proxy)