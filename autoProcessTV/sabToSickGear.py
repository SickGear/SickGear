#!/usr/bin/env python

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
import sys

try:
    import autoProcessTV
except ImportError:
    # 0  sys.argv[0] is the name of this script
    print('Can\'t import autoProcessTV.py, make sure it\'s in the same folder as %s' % sys.argv[0])
    sys.exit(1)

if 2 > len(sys.argv):
    print('No folder supplied - is this being called from SABnzbd?')
    sys.exit(1)

# SABnzbd user script parameters - see: https://sabnzbd.org/wiki/scripts/post-processing-scripts
autoProcessTV.process_files(
    # 1  The final directory of the job (full path)
    sys.argv[1],
    # 2  The original name of the NZB file
    None if 3 >= len(sys.argv) else sys.argv[2],
    # 7  Status of processing. 0 = OK, 1 = Failed verification, 2 = Failed unpack, 3 = 1+2, -1 = Failed post processing
    None if 8 >= len(sys.argv) else sys.argv[7]
)
