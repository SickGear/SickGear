# Copyright 2022 Akamai Technologies, Inc
# Largely rewritten in 2023 for urllib3-future
# Copyright 2024 Ahmed Tahri
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#     http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.

from __future__ import annotations

import dataclasses
from typing import Any


@dataclasses.dataclass
class QuicTLSConfig:
    """
    Client TLS configuration.
    """

    #: Allows to proceed for server without valid TLS certificates.
    insecure: bool = False

    #: File with CA certificates to trust for server verification
    cafile: str | None = None

    #: Directory with CA certificates to trust for server verification
    capath: str | None = None

    #: Blob with CA certificates to trust for server verification
    cadata: bytes | None = None

    #: If provided, will trigger an additional load_cert_chain() upon the QUIC Configuration
    certfile: str | bytes | None = None

    keyfile: str | bytes | None = None

    keypassword: str | bytes | None = None

    #: The QUIC session ticket which should be used for session resumption
    session_ticket: Any | None = None

    cert_fingerprint: str | None = None
    cert_use_common_name: bool = False

    verify_hostname: bool = True
    assert_hostname: str | None = None

    idle_timeout: float = 300.0

    ech_config_list: bytes | None = None
