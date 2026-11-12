# Dummy file to match upstream modules
# without actually serving them.
# urllib3-future diverged from urllib3.
# only the top-level (public API) are guaranteed to be compatible.
# in-fact urllib3-future propose a better way to migrate/transition toward
# newer protocols.

from __future__ import annotations

import warnings


def inject_into_urllib3() -> None:
    warnings.warn(
        (
            "urllib3-future does not currently support Emscripten Pyodide. "
            "Use upstream urllib3 on these platforms. See the cohabitation "
            "instructions at "
            "https://niquests.readthedocs.io/en/latest/community/faq.html#cohabitation"
        ),
        FutureWarning,
        stacklevel=2,
    )


def extract_from_urllib3() -> None:
    pass
