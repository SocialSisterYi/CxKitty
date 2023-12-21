class APIError(Exception):
    "接口错误"


class HandleCaptchaError(Exception):
    "处理风控验证码时错误"


class FaceDetectionError(Exception):
    def __str__(self):
        return "人脸识别错误"


class ChapterNotOpened(APIError):
    "章节未开放"


# 任务点相关
class TaskPointError(APIError):
    "任务点错误"


class PointWorkError(TaskPointError):
    "作业任务点错误"


class WorkAccessDenied(PointWorkError):
    def __str__(self):
        return "作业无权限访问"


# 考试相关
class ExamError(APIError):
    "考试错误"


class ExamEnterError(ExamError):
    "考试进入错误"


class ExamNotStart(ExamEnterError):
    def __str__(self):
        return "考试未开始"


class ChaptersNotComplete(ExamEnterError):
    def __str__(self):
        return "章节未完成"


class IPNotAllow(ExamEnterError):
    def __str__(self):
        return "考试 IP 不在白名单中"


class PCExamClintOnly(ExamEnterError):
    def __str__(self):
        return "PC 考试客户端限定"


class ExamCompleted(ExamEnterError):
    def __str__(self):
        return "考试已完成"


class ExamCodeDenied(ExamEnterError):
    def __str__(self):
        return "考试码鉴权失败"


class ExamAccessDenied(ExamError):
    def __str__(self):
        return "试题无权限访问"


class ExamIsCommitted(ExamError):
    def __str__(self):
        return "试题已经提交"


class ExamInvalidParams(ExamError):
    def __str__(self):
        return "参数错误"


class ExamSubmitError(ExamError):
    "考试提交失败"


class ExamSubmitTooEarly(ExamSubmitError):
    def __str__(self):
        return "不允许提前交卷"


class ExamTimeout(ExamSubmitError):
    def __str__(self):
        return "考试超时"
