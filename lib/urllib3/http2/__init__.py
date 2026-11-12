# Dummy file to match upstream modules
# without actually serving them.
# urllib3-future diverged from urllib3.
# only the top-level (public API) are guaranteed to be compatible.
# in-fact urllib3-future propose a better way to migrate/transition toward
# newer protocols.

from __future__ import annotations


def inject_into_urllib3() -> None:
    pass


def extract_from_urllib3() -> None:
    pass
