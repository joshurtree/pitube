#
#    Copyright 2013 Josh Andrews
#
#    This file is part of PiTube
#
#    PiTube is free software: you can redistribute it and/or modify
#    it under the terms of the GNU General Public License as published by
#    the Free Software Foundation, either version 3 of the License, or
#    (at your option) any later version.
#
#    PiTube is distributed in the hope that it will be useful,
#    but WITHOUT ANY WARRANTY; without even the implied warranty of
#    MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
#    GNU General Public License for more details.
#
#    You should have received a copy of the GNU General Public License
#    along with this program.  If not, see <http://www.gnu.org/licenses/>.

import os.path
import sys
import tempfile
from gettext import gettext as _

APPLICATION_DIR = os.path.abspath(sys.path[0] + '/..')
IMAGE_DIR = APPLICATION_DIR + '/images/'
DATA_DIR = tempfile.gettempdir() + '/pitube/'
SETTINGS_DIR = os.path.expanduser('~/.pitube/')

APPLICATION_NAME = 'PiTube'
APPLICATION_VERSION = '0.1'
APPLICATION_ICON= IMAGE_DIR + 'PiTube-medium.png'
APPLICATION_ICON_LARGE = IMAGE_DIR + 'PiTube-large.png'
APPLICATION_AUTHOR = 'Josh Andrews'

ABOUT_TEXT = '''<p align='center'>%s<br/>
             Online media player for the Raspberry Pi.<br/>
             Version %s<br/>
             Written by %s</p>
             <p>Omxplayer interface based on pyomxplayer developed by Johannes Baiter</p>''' % (APPLICATION_NAME, APPLICATION_VERSION, APPLICATION_AUTHOR)