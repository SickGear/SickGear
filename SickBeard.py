#!/usr/bin/env python2
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

from __future__ import print_function
print(
    '------------------------------------------------------------------------------------------------------------------'
)
print(
    '2019 Jan: You can now run sickgear.py directly'
    ' (SickBeard.py now serves as a legacy convenience which prints this message on every startup)'
)
print(
    '------------------------------------------------------------------------------------------------------------------'
)
import runpy
runpy.run_module('sickgear', {'_legacy_sickbeard_runner': True}, '__main__')
