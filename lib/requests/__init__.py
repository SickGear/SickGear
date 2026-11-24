# compat shim: `requests` resolves to niquests so vendored libs keep their imports unchanged
import importlib
import sys

from niquests import *  # noqa: F401,F403
from niquests import __version__  # noqa: F401
from niquests import Session

session = Session  # requests.session() helper, dropped by niquests

for _name in ('adapters', 'api', 'auth', 'cookies', 'exceptions', 'hooks', 'models',
              'packages', 'sessions', 'status_codes', 'structures', 'utils'):
    globals()[_name] = sys.modules[__name__ + '.' + _name] = importlib.import_module('niquests.' + _name)
