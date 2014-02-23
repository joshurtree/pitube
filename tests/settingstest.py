#!/usr/bin/python 

#import sys
#sys.path.append('..')

from Settings import Settings
import unittest
import os.path

class SettingsTest(unittest.TestCase) :
    SETTINGS_PATH = os.path.expanduser('settingstest.xml')
	
    @classmethod
    def setUpClass(self) :    
        Settings.loadSettings(self.SETTINGS_PATH)
        self.settings = Settings("test")
	
    def test_string(self) :
        defaulttest = self.settings.get('defaulttest', 'defaulttest')
        self.settings.set('gettest', 'gettest')
        gettest2 = self.settings.get('gettest', 'defaulttest')
		
        self.assertEquals(defaulttest, 'defaulttest')
        self.assertEquals(gettest2, 'gettest')
	
    def test_int(self) :
        gettest1 = self.settings.get('gettest', 4)
        self.settings.set('gettest', 1)
        gettest2 = self.settings.get('gettest', 4)
                
        self.assertEquals(gettest1, 4)
        self.assertEquals(gettest2, 1)
        
    def test_bool(self) :
        gettest1 = self.settings.get('gettest', False)
        self.settings.set('gettest2', True)
        self.settings.set('gettest3', False)
        gettest2 = self.settings.get('gettest2', False)
        gettest3 = self.settings.get('gettest3', False)
        
        self.assertEquals(gettest1, False)
        self.assertEquals(gettest2, True)
        self.assertEquals(gettest3, False)
        	
    def test_write(self) :
        self.settings.write()
        self.assertTrue(os.path.exists(self.SETTINGS_PATH))
		
    @classmethod
    def tearDownClass(self) :
        os.remove(self.SETTINGS_PATH)
        #self.settings.dump()
	
if __name__ == '__main__':
    unittest.main()