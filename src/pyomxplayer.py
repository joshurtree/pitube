#
#    Copyright 2013 Josh Andrews
#
#    This file is based on code develped by Johannes Baiter. 
#    See https://github.com/jbaiter/pyomxplayer
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

import re
import sys

from threading import Thread, Timer
from time import sleep
from VideoManager import VideoHandler
from constants import *
import os.path
import subprocess
from multire import multire

from PySide.QtGui import *
from PySide.QtCore import *

class OMXPlayer(QThread) :
    _FILEPROP_REXP = re.compile(r".*audio streams (\d+) video streams (\d+) chapters (\d+) subtitles (\d+).*")
    _VIDEOPROP_REXP = re.compile(r".*Video codec ([\w-]+) width (\d+) height (\d+) profile (\d+) fps ([\d.]+).*")
    _AUDIOPROP_REXP = re.compile(r"Audio codec (\w+) channels (\d+) samplerate (\d+) bitspersample (\d+).*")
    _STATUS_REXP = re.compile(r"V :\s*([\d.]+).*")
    _DONE_REXP = re.compile(r"have a nice day.*")
    ALL_REXP = multire([r"V :\s*([\d.]+).*", r"have a nice day.*"])
    
    _OMXPLAYER_CMD = '/usr/bin/omxplayer'
    _OMXPLAYER_ARGS = '-s %s %s'
    _INCREASE_SPEED_CMD = '1'
    _DECREASE_SPEED_CMD = '2'
    _SKIP_FWD_CMD = 0x5b44  #Left arrow
    _SKIP_BACK_CMD = 0x5b43 #Right arrow
    _SEEK_FWD_CMD = 0x5b41  #Up arrow
    _SEEK_BACK_CMD = 0x5b42 #Down arrow
    _PAUSE_CMD = 'p'
    _TOGGLE_SUB_CMD = 's'
    _QUIT_CMD = 'q'
    
    SEEK_SPEEDS = [-32, -16, -8, -4, -2, 0, 2, 4, 8, 16, 32 ]
    NO_SEEK = SEEK_SPEEDS.index(0)

    def __init__(self, parent, videoHandler) :
        QThread.__init__(self)
        self.controls = OMXPlayerControls(self)
        self.videoHandler = videoHandler
        self.args = self._OMXPLAYER_ARGS % ('', videoHandler.filename())
        
        if 'lastPosition' in videoHandler.details :
            self.args += ' --pos %d' % videoHandler.details['lastPosition']
            self.__position = videoHandler.details['lastPosition']
        else :
            self.__position = 0
        
        print "Command used: " + self._OMXPLAYER_CMD + " " + self.args
                
        #self.controls.showMaximized()
        self.start()
        
    def sendCommand(self, command, times = 1) :
        print "Sending command %s" % str(command)
        success = True
        
        for i in range(times) :
            if not self._process.stdin.write(command) :
                success = False
            
        return success
        
    def run(self) :
        preferredLag = 20
        while not 'eta' in self.videoHandler.downloadInfo() :
            if self.videoHandler.finishedDownload() :
                break
            sleep(1)
            
        eta = lambda val : val['eta'] < self.videoHandler.duration() if 'eta' in val else True
        
        # Hold playing until file is likely to be downloaded before finished playing
        while eta(self.videoHandler.downloadInfo()) :
            if self.videoHandler.finishedDownload() :
                break
            sleep(1)
            
        self._process = subprocess.Popen([self._OMXPLAYER_CMD] + self.args.split(), 
                                         0, None, subprocess.PIPE, subprocess.PIPE)
        #self._process.logfile = sys.stdout
        self.buffering = False
        self.paused = False 
                     
        self.subtitles_visible = True
        self.toggle_subtitles()
        self.seekIndex = self.NO_SEEK
        self.seekTimer = None

        self.video = dict()
        self.audio = dict()
        
        try :
            # Get file properties
            file_props = self._FILEPROP_REXP.match(self._process.stdout.readline())
            
            if file_props and file_props.groups() :
                (self.audio['streams'], self.video['streams'],
                self.chapters, self.subtitles) = [int(x) for x in file_props.groups()]

            # Get video properties
            video_props = self._VIDEOPROP_REXP.match(self._process.stdout.readline())
            
            if video_props and video_props.groups() :
                video_props = video_props.groups()
                self.video['decoder'] = video_props[0]
                self.video['dimensions'] = tuple(int(x) for x in video_props[1:3])
                self.video['profile'] = int(video_props[3])
                self.video['fps'] = float(video_props[4])

            # Get audio properties
            audio_props = self._AUDIOPROP_REXP.match(self._process.stdout.readline())
            
            if audio_props and audio_props.groups() :
                audio_props = audio_props.groups()
                self.audio['decoder'] = audio_props[0]
                (self.audio['channels'], self.audio['rate'],
                self.audio['bps']) = [int(x) for x in audio_props[1:]]

            if 'streams' in self.audio and self.audio['streams'] > 0:
                self.current_audio_stream = 1
                self.current_volume = 0.0
        except IOError :
            print 'Error in reading inital status of omxplayer'
            
        
        while not self.finished() :
            lag = self.videoHandler.durationDownloaded() - self.position()
            if self.buffering :
                if lag >= preferredLag and self.sendCommand(self._PAUSE_CMD) :
                    print 'buffering end'
                    self.buffering = False
            else :
                if not self.processPlayerOutput() :
                    break
                if lag <= 2 :
                    if self.sendCommand(self._PAUSE_CMD) :
                        print 'buffering start'
                        self.buffering = True
                
    def processPlayerOutput(self) :
        try :
            line = self._process.stdout.read(100)
            #print line
            index = self.ALL_REXP.search(line)
            
            if index == -1 : 
                print "no match"
                return True
            if index == 1 : 
                self.finished()
                return False
                                                
            # Got status line 
            position = float(float(self.ALL_REXP.lastmatch.group(1))/float(10**6))
            
            if position >= 1 and position < 10**6 :
                print "Position: " + str(position)
                self.videoHandler.details['lastPosition'] = position
                __position = position
                        
        except IOError :
            print 'I/O error in omxplayer pipe'
            
        return True
    
        #self.controls.setVisible(False)
        #self.controls.disconnect()
         
    def aborted(self) :
        self.videoHandler.details['lastPosition'] = 0
        print "video finished"
    
    def position(self) :
        return self.__position
    
    def finished(self) :
        self._process.poll()
        return not self._process.returncode == None
    
    def play(self) :
        self.setPause(False)
        
    def pause(self) :
        self.setPause(True)
    
    def togglePause(self) :
        if not self.buffering :
            self.sendCommand(self._PAUSE_CMD)
            
    def setPause(self, value = True) :
        self.seekIndex = self.NO_SEEK
        if self.seekTimer :
            self.seekTimer.cancel()
            self.seekTimer = None
        
        print 'Changing pause state from %s to %s' % (self.paused, value)
        if self.paused != value and not self.buffering :
            if self.sendCommand(self._PAUSE_CMD) :
                self.Paused = value
                
    def toggle_subtitles(self):
        if self.sendCommand(self._TOGGLE_SUB_CMD):
            self.subtitles_visible = not self.subtitles_visible
            
    def stop(self):
        self.sendCommand(self._QUIT_CMD)
        self._process.terminate(force=True)

    def increaseSpeed(self):
        self.sendCommand(self._INCREASE_SPEED_CMD)

    def decreaseSpeed(self) :
	self.sendCommand(self._DECREASE_SPEED_CMD)
	
    def set_audiochannel(self, channel_idx):
        raise NotImplementedError

    def set_subtitles(self, sub_idx):
        raise NotImplementedError

    def set_chapter(self, chapter_idx):
        raise NotImplementedError

    def set_volume(self, volume):
        raise NotImplementedError

    def seek(self, mseconds) :
        seeks = mseconds / 600
        skips = (mseconds % 600) / 30
        skip_cmd = self._SKIP_BACK_CMD
        seek_cmd = self._SEEK_BACK_CMD
        
        if mseconds > 0 :
            skip_cmd = self._SKIP_FWD_CMD
            seek_cmd = self._SEEK_FWD_CMD
          
        for i in range(seeks) :
            self._process.s(seek_cmd)
        for i in range(skips) :
            self.sendCommand(skip_cmd)

'''
    def changeSeekSpeed(self, direction) :   
        # Exit if new speed is outside allowed range
        if not (self.seekIndex + direction in range(len(self.SEEK_SPEEDS))) :
            return
        
        oldSeekSpeed = self.SEEK_SPEEDS[self.seekIndex]
        self.seekIndex += direction
        newSeekSpeed = self.SEEK_SPEEDS[self.seekIndex]
#       
        if self.buffering and newSeekSpeed > 0 :
            return      # Prevent forward movement while buffering
        
        if self.seekTimer :
            self.seekTimer.cancel()     # Cancel any current seeking
            self.seekTimer = None
       
        doSeek = lambda : 
        seekBack = lambda : Timer(0.6/abs(newSeekSpeed), self.sendCommand, [self._SEEK_BACK_CMD])
        seekForward = lambda : Timer(0.6/abs(newSeekSpeed), self.sendCommand, [self._SEEK_FWD_CMD])
        skipBack = lambda : Timer(0.03/abs(newSeekSpeed), self.sendCommand, [self._SKIP_BACK_CMD])
        skipForward = lambda : Timer(0.03/abs(newSeekSpeed), self.sendCommand, [self._SKIP_FWD_CMD])
        skipToPlay = lambda : self.sendCommand(self._INCREASE_SPEED_CMD, 3)

        seekCommands = [ [None, seekBack], 
                         [seekBack, seekBack], 
                         [seekBack, skipBack],
                         [skipBack, skipBack],
                         [skipBack, skipBack], 
                         [skipBack, self.play],
                         [self.decreaseSpeed,  self.increaseSpeed],
                         [self.decreaseSpeed, self.increaseSpeed],
                         [self.decreaseSpeed, skipForward], 
                         [skipToPlay, seekForward],
                         [seekForward, seekForward],
                         [seekForward, None] ]
        command = seekCommands[self.seekIndex][(direction+1)/2]
        isPlaying = lambda seek : seek in [0, 2, 4]
        if isPlaying(oldSeekSpeed) <> isPlaying(newSeekSpeed) :
            self.sendCommand(self._PAUSE_CMD)

        if command :
            result = command()
            print result
            
            if hasattr(result, 'start') :
                self.seekTimer = result
                self.seekTimer.start()
'''       

class OMXPlayerControls(Thread) :
    _PRESS_REXP = re.compile(r".*:44:([0-9a-f]{2})")
    _RELEASE_REXP = re.compile(r".*:8b:([0-9a-f]{2})")
    _CEC_CMD = '/usr/local/bin/cec-client'
    _CEC_ARGS = '-l 8'
    
    _BACK_CODE = 0x48
    _FWD_CODE = 0x49
    _PLAY_CODE = 0x44
    _STOP_CODE = 0x45
    _FWD_CHAPTER_CODE = 0x4b
    _BACK_CHAPTER_CODE = 0x4c
    
    _SELECT_CODE = 0x00
    _UP_CODE = 0x01
    _DOWN_CODE = 0x02
    _LEFT_CODE = 0x03
    _RIGHT_CODE = 0x04
    
    def __init__(self, player) :
        Thread.__init__(self)
        self.player = player
        self.seek = 0
        self._controls = subprocess.Popen([self._CEC_CMD] + self._CEC_ARGS.split(), 0, None, subprocess.PIPE, subprocess.PIPE)
        self.start()

    def startSeek(self, direction) :
        self.seek = direction
        
    def stopSeek(self) :
        self.seek = 0
        
    def run(self) :
        matches = multire([self._PRESS_REXP, self._RELEASE_REXP])
        while not self.player.finished :
            try :
                index = matches.match(self._controls.stdout.readline())
                
                code = self._controls.match.group(1) if index in (0, 1) else -1
                
                print 'index: %d, code: %d' % (index, code)
                
                if index == 0 :
                    if code == self._FWD_CODE :
                        self.startSeek(1)
                    elif code == self._BACK_CODE :
                        self.startSeek(-1)
                if index == 1 :
                    if code == self._PLAY_CODE :
                        self.player.togglePause()
                    elif code == self._STOP_CODE :
                        self.player.quit()
                    elif code in (self._BACK_CODE, self._FWD_CODE) :
                        self.stopSeek()
                    
                #process seeking behavouir
                self.player.seek(100 * self.__seek)
                threading.sleep(0.1)
            except IOError :
                print 'I/O error in CEC pipe'

'''
class OMXPlayerControls(QMainWindow) :
    PAUSE_IMAGE = QRect(0, 0, 122, 112)
    STOP_IMAGE = QRect(122, 0, 122, 112)
    PLAY_IMAGE = QRect(244, 0, 122, 112)
    FWD_IMAGE = QRect(366, 0, 122, 112)
    BACK_IMAGE = QRect(488, 0, 122, 112)
    BUTTON_SIZE = QSize(122, 112)
    
    def __init__(self, parent) :
        QMainWindow.__init__(self, parent)
        self.setWindowFlags(self.windowFlags() | Qt.FramelessWindowHint | 
                            Qt.WindowStaysOnTopHint | Qt.X11BypassWindowManagerHint)
        screenGeometry = QCoreApplication.instance().desktop().screenGeometry()
        self.setGeometry(screenGeometry.width() / 4, screenGeometry.height() - 140, 640, 140)
        
        #self.images = dict()
        buttonWidget = QWidget(self)
        layout = QHBoxLayout() 
        buttons = QPixmap(IMAGE_DIR + 'player-buttons.png')
        self.back = self.createButton(buttons.copy(rect=self.BACK_IMAGE))
        self.pause = self.createButton(buttons.copy(rect=self.PAUSE_IMAGE))
        self.play = self.createButton(buttons.copy(rect=self.PLAY_IMAGE))
        self.stop = self.createButton(buttons.copy(rect=self.STOP_IMAGE))
        self.forward = self.createButton(buttons.copy(rect=self.FWD_IMAGE))
        
        layout.addWidget(self.back)
        layout.addWidget(self.pause)
        layout.addWidget(self.play)
        layout.addWidget(self.stop)
        layout.addWidget(self.forward)
        
        buttonWidget.setLayout(layout)
        self.setCentralWidget(buttonWidget)
        
    def createButton(self, image) :
        button = QPushButton(self)
        button.setIconSize(self.BUTTON_SIZE)
        button.setIcon(image)
        button.setFixedSize(self.BUTTON_SIZE)
        #button.setFlat(True)
        return button
    
    def connectTo(self, player) :
        seek = lambda direction : lambda :player.changeSeekSpeed(direction)
        self.back.clicked.connect(seek(-1))
        self.pause.clicked.connect(player.pause)
        self.play.clicked.connect(player.play)
        self.stop.clicked.connect(player.stop)
        self.forward.clicked.connect(seek(1))

    def disconnect(self) :
        self.back.clicked.disconnect()
        self.pause.clicked.disconnect()
        self.play.clicked.disconnect()
        self.stop.clicked.disconnect()
        self.forward.clicked.disconnect()

class OMXPlayerControls(QMainWindow) :
    def __init__(self, parent, player=None) :
        QMainWindow.__init__(self, parent)
        self.setWindowFlags(self.windowFlags() | Qt.WindowFullScreen | Qt.WindowMaximized)
        self.player = player
        
    def mousePressEvent(self, event) :
        if event.button() == Qt.LeftButton :
            self.player.togglePause()
        elif event.button() == Qt.RightButton :
            self.gesturing = True
 
    def mouseReleaseEvent(self, event)  :
        if event.button() == Qt.RightButton :
            self.gesturing = False
        
            
    def wheelEvent(self, event) :
        if event.delta() >= 120 :
            self.player.changeSeekSpeed(event.delta()/120)         
'''