import re

from openai import OpenAI

from cxapi.schema import QuestionModel
from logger import Logger
from . import SearcherBase, SearcherResp


class OpenAISearcher(SearcherBase):
    """ChatGPT 在线答题器"""

    client: OpenAI
    config: dict

    def __init__(self, **config) -> None:
        super().__init__()
        self.config = config
        self.client = OpenAI(api_key=config["api_key"], base_url=config["base_url"])
        self.logger = Logger("OpenAISearcher")

    def invoke(self, question: QuestionModel) -> SearcherResp:

        # self.logger.info("传入的question.options" + json.dumps(question.options))

        # 将选项从JSON转换成人类(GPT)易读形式
        options_str = ""
        if type(question.options) is not None:
            options_str = "选项：\n"
            if type(question.options) is dict:
                for k, v in question.options.items():
                    options_str += k + ". " + v + ";"
            elif type(question.options) is list:
                for v in question.options:
                    options_str += v + ";"

        self.logger.info(
            "从 "
            + self.config["prompt"]
            + " 生成提问："
            + str(self.config["prompt"]).format(
                type=question.type.name,
                value=question.value,
                options=options_str,
            ),
        )
        try:
            response = self.client.chat.completions.create(
                model=self.config["model"],
                temperature=0.5,  # 答题场景适合把temperature调低
                messages=[
                    {"role": "system", "content": self.config["system_prompt"]},
                    {
                        "role": "user",
                        "content": str(self.config["prompt"]).format(
                            type="单选题",
                            value="We didn’t have health____________ at the time and when I got a third infection, my parents couldn’t pay for the treatment.",
                            options="选项：\nA. assurance;B. insurance;C. requirement;D. issure;",
                        )
                    },  # 这里给个单选题回复示例供 AI 模仿
                    {"role": "assistant", "content": "A. insurance"},
                    {
                        "role": "user",
                        "content": str(self.config["prompt"]).format(
                            type=question.type.name,
                            value=question.value,
                            options=options_str,
                        ),
                    },
                ],
            )

            response = response.choices[0].message.content
            if response is None:
                # 防止预处理时报错
                response = ''
        except Exception as err:
            return SearcherResp(-500, err.__str__(), self, question.value, None)

        # 单选题需要进一步预处理AI返回结果，以使 QuestionResolver 能正确命中
        if question.type.value is 0:
            response = response.strip()  # A. insurance
            for k, v in question.options.items():
                # 以 A. 开头、或者包含 insurance
                if response.startswith(k + '.') or (v in response):
                    response = v
                    break
        # 多选同理
        if question.type.value is 1:
            awa = ""
            for k, v in question.options.items():
                if v in response:
                    awa += v + "#"
            response = awa

        # 填空须删除"第x空"提示
        if question.type.value is 2:
            response = response.strip()
            # 特殊规则: 假如ai对提示词理解错误(一般发生在仅有一个空的情况)
            # 如: Q: 以_______为代表，标志着第四代计算机网络的兴起
            #     A: 以#互联网#为代表，标志着第四代计算机网络的兴起。
            # note: 但是似乎当空在开头或结尾时不起作用
            if len(question.options) == 1 and len(response.split("#")) == 3:
                response = response.split("#")[1]

            response = response.lstrip("#").rstrip("#")
            response = re.sub(r"第.{1,3}空[：:，,]", "", response)  # 假定填空题的空数不超过"一百"个
            self.logger.info("填空题答案：" + response)
            if len(response.split("#")) != len(question.options):
                return SearcherResp(-500, "未匹配答案字段", self, question.value, None)
        self.logger.info("返回结果：" + response)
        return SearcherResp(0, "", self, question.value, response)
