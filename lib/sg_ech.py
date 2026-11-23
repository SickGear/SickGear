# coding=utf-8
#
# This file is part of SickGear.
#
# SickGear is free software: you can redistribute it and/or modify
# it under the terms of the GNU General Public License as published by
# the Free Software Foundation, either version 3 of the License, or
# (at your option) any later version.
#
# SickGear is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
# GNU General Public License for more details.
#
# You should have received a copy of the GNU General Public License
# along with SickGear.  If not, see <http://www.gnu.org/licenses/>.

# Encrypted Client Hello (ECH) route past an ISP that blocks a site by the server name in the TLS handshake.
# A blocked domain is looked up via DNS over HTTPS (DoH), that gives the ECH config, and the name is then hidden

# noinspection PyUnreachableCode
if False:
    from typing import List, Optional, Union

BUILTIN_DOH = ('doh+cloudflare://', 'doh+quad9://', 'doh+google://')

blocked_domains = set()  # host names that go via DoH for this run


def session_resolver(user_resolver):
    # type: (Optional[str]) -> Union[None, str, List[str]]
    """
    :param user_resolver: resolver url of the user setting, empty for system DNS
    :return: the resolver for a session, the user setting as is when no domain is blocked, else a DoH chain limited
     to the blocked domains, then the user setting (or system DNS) for all else
    """
    if not blocked_domains:
        return user_resolver or None

    hosts = 'hosts=%s' % ','.join(sorted(blocked_domains))
    chain = ([user_resolver] if (user_resolver or '').startswith('doh') else []) \
        + [_r for _r in BUILTIN_DOH if _r != user_resolver]
    return ['%s%s%s' % (_r, ('?', '&')['?' in _r], hosts) for _r in chain] + [user_resolver or 'system://']
