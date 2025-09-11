from ..common import NotifyType as NotifyType
from ..url import PrivacyMode as PrivacyMode
from ..utils.parse import parse_bool as parse_bool, validate_regex as validate_regex
from .base import NotifyBase as NotifyBase
from _typeshed import Incomplete
from typing import Any

class NotifySIGNL4(NotifyBase):
    service_name: str
    service_url: str
    secure_protocol: str
    setup_url: str
    event_action: str
    notify_url: str
    templates: Incomplete
    template_tokens: Incomplete
    template_args: Incomplete
    secret: Incomplete
    service: Incomplete
    location: Incomplete
    alerting_scenario: Incomplete
    filtering: Incomplete
    external_id: Incomplete
    status: Incomplete
    def __init__(self, secret: str, service: str | None = None, location: str | None = None, alerting_scenario: str | None = None, filtering: bool | None = None, external_id: str | None = None, status: str | None = None, **kwargs: Any) -> None: ...
    def send(self, body, title: str = '', notify_type=..., **kwargs): ...
    @property
    def url_identifier(self): ...
    def url(self, privacy: bool = False, *args, **kwargs): ...
    @staticmethod
    def parse_url(url): ...
