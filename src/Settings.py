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
from xml.sax import parse
from xml.sax.saxutils import XMLFilterBase

class SettingsLoader(XMLFilterBase) :
        def loadSetting(self, name, attrs, conv) :
            Settings.values[attrs.getValue('name')] = conv(attrs.getValue('value'))
            
        def startElement(self, name, attrs) :
            if name == type('').__name__ :
                self.loadSetting(name, attrs, str)
            elif name == type(0).__name__ :
                self.loadSetting(name, attrs, int)
            elif name == type(0.0).__name__ :
                self.loadSetting(name, attrs, float)
            elif name == type(False).__name__ :
                self.loadSetting(name, attrs, lambda val : val == 'True')

class Settings :
    @staticmethod
    def load(path) :
        Settings.values = dict()
        Settings.settingsFile = path
        Settings.path = path
        if os.path.exists(path) :
            parse(path, SettingsLoader())
      
    @staticmethod
    def write() :
        settingsFile = open(Settings.path, 'w')
        settingsFile.write(Settings.toXML())
        settingsFile.close()
    

    def __init__(self, namespace = None) :
        if namespace :
            self.namespace = namespace + '.'
        else :
            self.namespace = ''
         
    def keys(self) :
        if self.namespace :
            return [key for key in Settings.values.keys() 
                    if key.startswith(self.namespace)]
        else :
            return Settings.values.keys()
         
    def get(self, name, default) :
        fullname = self.namespace + name
        if not fullname in self.values:
            self.values[fullname] = default
            
        return self.values[fullname]
    
    def set(self, name, value) :
        self.values[self.namespace + name] = value
     
    @staticmethod
    def toXML() :
        xml = '<settings>\n'
        
        for name in Settings.values :
            xml += "  <%s name='%s' value='%s' />\n" % (type(Settings.values[name]).__name__, name, 
                                                      Settings.values[name])
            
        xml += '</settings>'
        return xml
                