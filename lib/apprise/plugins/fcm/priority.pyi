from ...logger import logger as logger
from .common import FCMMode as FCMMode, FCM_MODES as FCM_MODES
from _typeshed import Incomplete

class NotificationPriority:
    NORMAL: str
    HIGH: str

class FCMPriority:
    MIN: str
    LOW: str
    NORMAL: str
    HIGH: str
    MAX: str

FCM_PRIORITIES: Incomplete

class FCMPriorityManager:
    priority_map: Incomplete
    mode: Incomplete
    priority: Incomplete
    def __init__(self, mode, priority=None) -> None: ...
    def payload(self): ...
    def __str__(self) -> str: ...
    def __bool__(self) -> bool: ...
