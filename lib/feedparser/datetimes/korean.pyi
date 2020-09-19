from .w3dtf import _parse_date_w3dtf as _parse_date_w3dtf
from typing import Any

_korean_year: str
_korean_month: str
_korean_day: str
_korean_am: str
_korean_pm: str
_korean_onblog_date_re: Any
_korean_nate_date_re: Any

def _parse_date_onblog(dateString: Any): ...
def _parse_date_nate(dateString: Any): ...
