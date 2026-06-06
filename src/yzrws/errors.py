"""yzrws 自定义异常层级。

所有 yzrws 抛出的业务异常都应继承 YzrwsError，
便于上层用 `except YzrwsError` 统一捕获并转换为用户可读的错误信息。
"""

from pathlib import Path


class YzrwsError(Exception):
    """yzrws 工具顶层异常基类。"""


class PathOccupiedError(YzrwsError):
    """workspace 路径已存在但是文件（不是目录），无法初始化。"""

    def __init__(self, path: Path) -> None:
        super().__init__(f"{path} 已存在但不是目录")
        self.path = path


class WritePermissionError(YzrwsError):
    """对 workspace 路径（或其父目录）无写权限。"""

    def __init__(self, path: Path) -> None:
        super().__init__(f"对 {path} 无写权限")
        self.path = path


class MetadataVersionError(YzrwsError):
    """metadata.json 的 version 字段与当前工具期望的版本不兼容。

    当前仅区分"低于"和"高于"两种情况，统一抛此异常，
    由调用方根据 actual / expected 决定提示文案。
    """

    def __init__(self, actual: str, expected: str) -> None:
        super().__init__(f"metadata.json 版本 {actual} 与期望 {expected} 不兼容")
        self.actual = actual
        self.expected = expected
