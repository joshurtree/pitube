from YouTubeHandler import YouTubeHandler, tzoffset
from gdata.service import BadAuthentication
import unittest
from datetime import datetime

class YouTubeHandlerTest(unittest.TestCase) :
	def setUp(self) :
		self.yt = YouTubeHandler()
		
	def test_login(self) :
		self.assertRaises(BadAuthentication, self.yt.login('bad', 'login'))
		self.yt.login('joshurtree@gmail.com', 'philbert20')
		
		
	def test_parseTimestamp(self) :
		testdt = YouTubeHandler.parseTimestamp('2008-07-05T19:56:35.000-07:00')
		self.assertEqual(testdt, datetime(2008, 7, 5, 19, 56, 35, 0, tzoffset(-7)))
		
if __name__ == '__main__':
    unittest.main()