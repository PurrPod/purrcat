class BashExecutionError(Exception):
    """基础的命令执行异常"""
    pass

class DockerEnvironmentError(Exception):
    """Docker 环境相关的异常"""
    pass