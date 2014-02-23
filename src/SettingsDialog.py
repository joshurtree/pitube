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

from PySide.QtCore import *
from PySide.QtGui import *
from Settings import Settings
import pdb
import types

class SettingsDialog(QDialog) :
    def __init__(self, parent = None) :
        QDialog.__init__(self, parent)
        layout = QVBoxLayout()
        self.settings = Settings()
        self.edits = dict()
        
        for key in  Settings.values.keys():
            layout.addLayout(self.createSettingField(key))
            
        buttons = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)
        self.setLayout(layout)
        
    def createSettingField(self, key) :
        layout = QHBoxLayout()
        layout.addWidget(QLabel(key))
        value = Settings.values[key]
        edit = QLineEdit(str(value))

        if value == True or value == False :
            edit = QCheckBox()
            if value :
                edit.setCheckState(Qt.Checked)
        elif isinstance(value, int) :
            edit.setValidator(QIntValidator())
        elif isinstance(value, float) :
            edit.setValidator(QDoubleValidator())
                
        self.edits[key] = edit
        layout.addWidget(edit)
        return layout
        
    def accept(self) :
        value = Settings.values[key]
        
        for key in self.keys :
            if isinstance(value, int) :
                self.settings.set(key, int(edit.text()))
            elif isinstance(value, float) :
                self.settings.set(key, float(edit.text()))
            elif isinstance(value, bool) :
                self.settings.set(key, edit.checkState() == Qt.Checked)
            else :
                self.settings.set(key, edit.text())
        self.setVisible(False)
        
    def reject(self) :
        self.setVisible(False)
    