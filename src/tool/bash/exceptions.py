class BashExecutionError(Exception):
    """基础的命令执行异常"""
    pass

class DockerEnvironmentError(Exception):
    """Docker 环境相关的异常"""
    pass

class DockerNotRunningError(DockerEnvironmentError):
    """Docker服务未启动或连接失败"""
    pass

class DockerImageNotFoundError(DockerEnvironmentError):
    """Docker没有对应的image/container或构建异常"""
    pass

class BashTimeoutError(BashExecutionError):
    """Bash命令执行超时"""
    pass