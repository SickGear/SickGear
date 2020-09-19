from .asctime import _parse_date_asctime as _parse_date_asctime
from .greek import _parse_date_greek as _parse_date_greek
from .hungarian import _parse_date_hungarian as _parse_date_hungarian
from .iso8601 import _parse_date_iso8601 as _parse_date_iso8601
from .korean import _parse_date_nate as _parse_date_nate, _parse_date_onblog as _parse_date_onblog
from .perforce import _parse_date_perforce as _parse_date_perforce
from .rfc822 import _parse_date_rfc822 as _parse_date_rfc822
from .w3dtf import _parse_date_w3dtf as _parse_date_w3dtf
from typing import Any

_date_handlers: Any

def registerDateHandler(func: Any) -> None: ...
def _parse_date(date_string: Any): ...
