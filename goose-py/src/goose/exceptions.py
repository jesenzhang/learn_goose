class GooseError(Exception):
    """
    Goose 项目的基础异常类
    """
    def __init__(self, message: str):
        self.message = message
        super().__init__(self.message)

class AuthError(GooseError):
    """
    鉴权失败异常 (密码错误、Token 过期、被封禁等)
    """
    pass

class ResourceNotFoundError(GooseError):
    """
    资源不存在异常
    """
    pass