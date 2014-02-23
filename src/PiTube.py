#!/usr/bin/python
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

import sys
from PySide.QtCore import *
from PySide.QtGui import *
import pdb

from pyomxplayer import *
from Settings import Settings
from VideoManager import *
from constants import *
from YouTube import YouTubeService
from SettingsDialog import SettingsDialog
import os
import os.path
import urllib
from cStringIO import StringIO
from threading import Thread
from traceback import print_stack
from datetime import datetime

from httplib2 import ServerNotFoundError

from gettext import gettext as _
#import compiler
            
class VideoListFrame(QWidget):
    def __init__(self, parent, playlist, videoManager):
        QWidget.__init__(self, parent)
        self.playlist = playlist
        playlist.setUpdateListener(self.refresh)
        
        self.refresh()
        self.more = None
        
        # Show progress bar while waiting for playlist to load
        self.setLayout(QGridLayout())
        self.progressWidget = QWidget()
        layout = QVBoxLayout()
        layout.addStretch()
        progress = QProgressBar(self)
        progress.setMinimum(0)
        progress.setMaximum(0)
        layout.addWidget(progress)
        layout.addStretch()
        self.progressWidget.setLayout(layout)
        self.layout().addWidget(self.progressWidget, 0, 0)
                
    def refresh(self) :
        self.frames = []
        self.startRow = 0
        self.row = 0
        self.loader = PlaylistLoader(self, self.playlist)
        self.loader.playlistLoaded.connect(self.loadVideos, Qt.QueuedConnection)
        pass
    
    def addVideo(self, video) :
        frame = VideoFrame(self, self.row, video)
        self.frames.append(frame)
        self.row += 3
        
    def loadVideos(self) :
        if self.more :
            self.more.setVisible(False)
            
        if self.row == 0 :
            self.progressWidget.setVisible(False)
            
        playlistLen = len(self.playlist.result())
        endRow = min(self.startRow + 10, playlistLen)
        for video in self.playlist.result()[self.startRow:self.startRow + 10] :
            self.addVideo(video)
            
        if endRow < playlistLen :
            self.more = QPushButton('Load more')
            self.more.clicked.connect(self.loadVideos)
            self.layout().addWidget(self.more, self.row, 1, 1, 1, Qt.AlignCenter)
            
        self.startRow = endRow
        
'''        
    def contextMenuEvent(self, event) :
        for i in range(0, self.layout().rowCount() - 1, 3) :
            cell = self.layout().cellRect(i, 0) 
            if cell.bottom() > event.pos().y() :
                self.frames[i].contextMenu.popup(event.globalPos())
                break
'''        

class PlaylistLoader(QThread) :
    playlistLoaded = Signal()
    
    def __init__(self, parent, playlist) :
        QThread.__init__(self, parent)
        self.parent = parent
        self.playlist = playlist
        self.start()
        
    def run(self) :
        self.playlist.execute()
        self.playlistLoaded.emit()
    
class ThumbnailLoader(QThread) :
    finished = Signal()
        
    def __init__(self, parent) :
        QThread.__init__(self, parent)
        self.parent = parent
        self.finished.connect(parent.displayThumbnail, Qt.QueuedConnection)
        self.start()
        
    def run(self) :
        self.parent.videoHandler().downloadThumbnail()
        self.finished.emit()
        
class AddToCommand(QObject) :
    def __init__(self, videoFrame, playlist) :
        self.videoFrame = videoFrame
        self.playlist = playlist
        
    def command(self) :
        self.videoFrame.addto(self.playlist)
        
class DownloadProgressMonitor(QObject) :
    updateProgress = Signal(float)
    
    def __init__(self, parent, videoHandler) :
        QObject.__init__(self, parent)
        self.videoHandler = videoHandler
        
class DownloadProgressThread(QThread) :    
    def __init__(self, parent) :
        QThread.__init__(self, parent)
        self.monitors = list()
        self.start()
        
    def cleanup(self) :
        self.finish = True
        self.wait()

    def add(self, videoHandler) :
        monitor = DownloadProgressMonitor(self, videoHandler)
        self.monitors.append(monitor)
        return monitor
        
    def run(self) :
        self.finish = False
        while not self.finish :
            for monitor in self.monitors :
                videoHandler = monitor.videoHandler
                if videoHandler.finishedDownload() :
                    self.monitors.remove(monitor)
                else :
                    info = videoHandler.downloadInfo()
                    if info and 'percent' in info.keys() :
                        monitor.updateProgress.emit(float(info['percent']))
            self.sleep(0.5)
                 
class ClickableLabel(QLabel) :
    clicked = Signal(QMouseEvent)
    
    def __init__(self, item = None) :
        QLabel.__init__(self, item)
        self.primed = False
        
    def mousePressEvent(self, event) :
        self.primed = True
        
    def mouseReleaseEvent(self, event) :
        if self.primed :
            self.primed = False        
            self.clicked.emit(event)
       
    def leaveEvent(self, event) :
        self.primed = False
        
class ToggleLabel(ClickableLabel) :
    toggled = Signal(bool)
    
    def __init__(self, item = None, state = False) :
        ClickableLabel.__init__(self, item)
        self.clicked.connect(self.__toggle)
        self.state = state
        self.pixmaps = dict()
        
    def setStatePixmap(self, pixmap, state) :
        self.pixmaps[state] = pixmap
        self.updatePixmap()
                    
    def setState(self, state) :
        self.state = state
        self.updatePixmap()

    def updatePixmap(self) :
        if self.state in self.pixmaps :
            self.setPixmap(self.pixmaps[self.state])
                       
    def __toggle(self, event) :
        self.setState(not self.state)
        self.toggled.emit(self.state)
    
class VideoFrame(QObject) :
    pixmaps = None

    channelClicked = Signal(VideoHandler)
    
    def __init__(self, parent, row, videoHandler) :
        QObject.__init__(self, parent)
        
        if self.pixmaps == None :
            self.pixmaps = dict()
            self.pixmaps['preloadEnabled'] = QPixmap(IMAGE_DIR + 'preload-enable.png')
            self.pixmaps['preloadDisabled'] = QPixmap(IMAGE_DIR + 'preload-disable.png')
            self.pixmaps['favoritesEnabled'] = QPixmap(IMAGE_DIR + 'favorites-enable.png')
            self.pixmaps['favoritesDisabled'] = QPixmap(IMAGE_DIR + 'favorites-disable.png')
            self.pixmaps['watchlaterEnabled'] = QPixmap(IMAGE_DIR + 'watchLater-enable.png')
            self.pixmaps['watchlaterDisabled'] = QPixmap(IMAGE_DIR + 'watchLater-disable.png')
            
        self.__videoHandler = videoHandler
        settings = Settings("videoview")
        
        layout = parent.layout()
        self.thumbnailCanvas = QLabel()
        self.thumbnailCanvas.setFixedSize(240, 135)
        self.thumbnailCanvas.setScaledContents(True)
        self.thumbnailCanvas.setStyleSheet('margin : 20px')
        layout.addWidget(self.thumbnailCanvas, row, 0, 3, 1, Qt.AlignCenter)
        ThumbnailLoader(self)
        
        infoTop = QHBoxLayout()
        title = ClickableLabel(videoHandler.title().strip())
        title.setStyleSheet(settings.get("title-style", "font-weight : bold; text-align : left"))
        title.setCursor(Qt.PointingHandCursor)
        title.setSizePolicy(QSizePolicy(QSizePolicy.Fixed, QSizePolicy.Fixed))
        title.clicked.connect(self.__play)
        infoTop.addWidget(title)
        
        channel = ClickableLabel('by ' + videoHandler.channel().strip())
        channel.setCursor(Qt.PointingHandCursor)
        channel.setSizePolicy(QSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed))
        channel.clicked.connect(self.emitChannelClicked)
        channel.setStyleSheet(settings.get("channel-style", "text-align : left"))
        infoTop.addWidget(channel)       
        
        parent.layout().addLayout(infoTop, row, 1)
        
        description = "No description"
        if videoHandler.description() :
            description = videoHandler.description()
            
        descriptionText = QLabel(description)
        descriptionText.setAlignment(Qt.AlignTop)
        descriptionText.setWordWrap(True)
        descriptionText.setFixedHeight(100)
        descriptionText.setStyleSheet(settings.get("description-style", ""))
        descriptionText.setSizePolicy(QSizePolicy(QSizePolicy.Fixed, 
                                                  QSizePolicy.Fixed))
        descriptionText.setMinimumWidth(600)
        parent.layout().addWidget(descriptionText, row + 1, 1, 2, 1)
        
        uploadTime = QLabel(self.getTimeSince(videoHandler.uploadTime()))
        uploadTime.setStyleSheet(settings.get("uploadtime-style", "text-align : right; vertical-align : center"))
        layout.addWidget(uploadTime, row, 2)
       
        self.optionsBar = QHBoxLayout()
        
        '''
        self.play = ClickableLabel()
        self.play.setPixmap(QPixmap(IMAGE_DIR + 'play.png'))
        self.play.clicked.connect(self.__play)
        '''
        
        self.preload = ToggleLabel()
        self.preload.setStatePixmap(self.pixmaps['preloadEnabled'], True)
        self.preload.setStatePixmap(self.pixmaps['preloadDisabled'], False)
        self.preload.setState(videoHandler.finishedDownload())
        self.preload.toggled.connect(self.__togglePreload)
        self.optionsBar.addWidget(self.preload)

        self.favourite = ToggleLabel()
        self.favouritePlaylist = videoHandler.service().userPlaylist('favorites')
        self.favourite.setStatePixmap(self.pixmaps['favoritesEnabled'], True)
        self.favourite.setStatePixmap(self.pixmaps['favoritesDisabled'], False)
        self.favourite.setState(self.favouritePlaylist.contains(videoHandler))
        self.favourite.toggled.connect(self.__toggleFavourite)
        self.optionsBar.addWidget(self.favourite)
        
        self.watchlater = ToggleLabel()
        self.watchlaterPlaylist = videoHandler.service().userPlaylist('watchLater')
        self.watchlater.setStatePixmap(self.pixmaps['watchlaterEnabled'], True)
        self.watchlater.setStatePixmap(self.pixmaps['watchlaterDisabled'], False)
        self.watchlater.setState(self.watchlaterPlaylist.contains(videoHandler))
        self.watchlater.toggled.connect(self.__toggleWatchlater)
        self.optionsBar.addWidget(self.watchlater)
        
        layout.addLayout(self.optionsBar, row + 1, 2)
        
        self.progressBar = QProgressBar()
        self.progressBar.setMaximumWidth(150)
        self.progressBar.setVisible(False)
        layout.addWidget(self.progressBar, row + 2, 2)
        
        #self.createContextMenu()
        
    def videoHandler(self) :
        return self.__videoHandler
       
    def createContextMenu(self) :
        #self.setContextMenuPolicy(Qt.ActionsContextMenu)
        self.actions = {'cancel' : QAction(_('Cancel preload'), self)}
        self.actions['cancel'].triggered.connect(self.__cancelPreload)
        
        self.contextMenu = QMenu(self.parent())
        self.actions['play'] = self.contextMenu.addAction(_('Play'))
        self.actions['play'].triggered.connect(self.__play)
        self.actions['preload'] = self.contextMenu.addAction(_('Preload'))
        self.actions['preload'].triggered.connect(self.__preload)
        self.actions['remove'] = self.contextMenu.addAction(_('Forget'))
        self.actions['remove'].triggered.connect(self.__forget)
        
        self.playlistMenu = QMenu(_('Add to'), self.parent())
        self.actions['atFavourites'] = self.playlistMenu.addAction(_('Favourites'))
        self.actions['atFavourites'].triggered.connect(AddToCommand(self, self.videoHandler().service().userPlaylist('favorites')).command)
        self.actions['atWatchLater'] = self.playlistMenu.addAction(_('Watch later')) 
        self.actions['atWatchLater'].triggered.connect(AddToCommand(self, self.videoHandler().service().userPlaylist('watchLater')).command)
        self.contextMenu.addMenu(self.playlistMenu)
        
       
    def emitChannelClicked(self) :
        #self.authorClicked.emit(self.videoHandler)
        frame.channelUploads(self.videoHandler())
            
    def updatePlaylist(self, playlist, include) :
        playlist.update(self.videoHandler(), include)
    
    def __play(self) :
        if not self.videoHandler().startedDownload() :
            self.__togglePreload(True)
            
        try :
            self.updatePlaylist(self.videoHandler().service().userPlaylist('watchHistory'), True)
        except :
            print 'Update of history failed'
            
        OMXPlayer(frame, self.videoHandler())
    
    def __togglePreload(self, state) :
        if state :
            self.videoHandler().startDownload()
            monitor = frame.downloadProgressMonitor.add(self.videoHandler())
            monitor.updateProgress.connect(self.updateProgress, Qt.QueuedConnection)
        else :
            self.videoHandler().stopDownload()
            self.videoHandler().removeFile()
                        
    def __toggleFavourite(self, state) :
        self.updatePlaylist(self.favouritePlaylist, state)
        
    def __toggleWatchlater(self, state) :
        self.updatePlaylist(self.watchlaterPlaylist, state)
    
    def updateProgress(self, progress) :
        if not self.progressBar :
            return
        
        if not self.progressBar.isVisible() :
            self.progressBar.setVisible(True)
            
        self.progressBar.setValue(progress)
        
    def displayThumbnail(self) :
	thumbnail = QPixmap(self.videoHandler().thumbnail())
	painter = QPainter(thumbnail)
	time = self.videoHandler().durationText()
	
	font = painter.font()
        font.setPointSize(16)
        painter.setFont(font)
	painter.setPen(QColor('white'))
	
	rect = painter.boundingRect(10, 150, 0, 0, Qt.AlignLeft, time)
	painter.fillRect(rect, QColor('black'))
	painter.drawText(rect, time) 
	painter.end()
        self.thumbnailCanvas.setPixmap(thumbnail)
            
    def getTimeSince(self, uploadTime) :
        diff = datetime.now() - uploadTime
        
        if diff.days >= 365 :
            return _('Uploaded %d years ago' % (diff//365).days)
        elif diff.days >= 30 :
            return _('Uploaded %d months ago' % (diff//30).days)
        elif diff.days > 0 :
            return _('Uploaded %d days ago' % diff.days)
        elif diff.seconds >= 3600 :
            return _('Uploaded %d hours ago' % (diff//3600).seconds)
        elif diff.seconds >= 60 :
            return _('Uploaded %d minutes ago' % (diff//60).seconds)
        else :
            return _('Uploaded seconds ago')

class PlaylistViewHandler(QObject) :
    def __init__(self, parent, title, name, playlist) :  
        QObject.__init__(self, parent)
        self.parent = parent
        self.title = title
        self.playlist = playlist
        self.name = name
        self.index = -1
        
    def stateChanged(self, state) :
        if state :
            self.parent.showPlaylist(self.title, self.playlist)
        else :
            self.parent.hidePlaylist(self.title)
            

class PiTube(QMainWindow) :
    def __init__(self, parent=None) :
        QMainWindow.__init__(self, parent)
        self.setWindowTitle(APPLICATION_NAME)
        self.setWindowIcon(QIcon(APPLICATION_ICON))
        self.setMinimumSize(1200, 800)
        
        self.createDirectories([SETTINGS_DIR, DATA_DIR])
            
        self.videoManager = VideoManager()
        self.youtubeservice = YouTubeService(self.videoManager)
        self.videoManager.addService('YouTube', self.youtubeservice)
        self.downloadProgressMonitor = DownloadProgressThread(self)
        
        self.tabs = QTabWidget(self)
        self.tabs.setTabsClosable(True)
        self.tabs.tabCloseRequested.connect(self.tabCloseRequested)
        self.setCentralWidget(self.tabs)

        self.viewHandlers = []
        self.viewSettings = Settings('views')
        self.createMenus()
        
        if not self.youtubeservice.isAuthenticated() :
            self.__authenticate()
        
        try :
            self.youtubeservice.postAuthentication()
            self.createViewMenu()
            self.parseArgs()
        except ServerNotFoundError, exp :
            print str(exp)
            QMessageBox.critical(self, _("Authentication error"), _("Unable to authenticate YouTube account"))        
            
        
        app.aboutToQuit.connect(self.cleanup)
             
    def cleanup(self) :
        self.downloadProgressMonitor.cleanup()
        self.videoManager.cleanup()
        self.youtubeservice.cleanup()
        Settings.write()

    def parseArgs(self) :
        index = 0
        if  '-l' in sys.argv :
            index = sys.argv.index('-l') + 1
        elif '--load' in sys.argv :
            index = sys.argv.index('--load') + 1
                
        if index and index <= len(sys.argv) :
            self.load(sys.argv[index])
            
            
    def load(self, url) :
        #pdb.set_trace()
        match = multire(['.*youtube.com/playlist\?list=(.*)', '.*youtube.com/watch\?v=(.*)'])
        index = match.match(url)
        
        if index == 0 :
            id = match.lastmatch.group(1)
            self.addPlaylistMenuItem('playlist', None, self.videoManager.playlist(id), True)
        elif index == 1 :
            id = match.lastmatch.group(1)
            vidid = lambda val : val
            video = self.youtubeservice.fetchVideos([id], vidid, vidid)[id]
            video.startDownload()
            OMXPlayer(self, video)
            
            
    def videoControls(self) :
        return self._videoControls
    
    def createDirectories(self, directories) :
        for directory in directories :
            if not os.path.exists(directory) :
                os.mkdir(directory)

    def createMenus(self) :
        self.actions = dict()        
        self.visibleHandlers = []
        menuBar = QMenuBar(self)
        
        self.settingsMenu = menuBar.addMenu(_("&Settings"))
        #self.actions['authenticate'] = self.settingsMenu.addAction(_('&Authenticate'))
        #self.actions['authenticate'].triggered.connect(self.__authenticate)
        self.actions['settings'] = self.settingsMenu.addAction(_('&Settings...'))
        self.actions['settings'].triggered.connect(self.__settings)
        
        self.helpMenu = menuBar.addMenu(_("&Help"))
        self.actions['about'] = self.helpMenu.addAction(_('&About...'))
        self.actions['about'].triggered.connect(self.__about)
       
        self.setMenuBar(menuBar)
    
    def createViewMenu(self) :
        PlaylistViewHandler.settings = Settings('views')
        viewMenu = self.menuBar().addMenu(_('&View'))
        viewMenu.addAction(self.addSubscriptionPlaylistMenuItem(_('&Subsciptions')))
        viewMenu.addAction(self.addDefaultPlaylistMenuItem(_('&Favourites'), 'favorites', True))
        viewMenu.addAction(self.addDefaultPlaylistMenuItem(_('&Watch Later'), 'watchLater', True))
        viewMenu.addAction(self.addDefaultPlaylistMenuItem(_('&Likes'), 'likes', False))
        viewMenu.addAction(self.addDefaultPlaylistMenuItem(_('&History'), 'watchHistory', False))
        
        self.menuBar().insertMenu(self.helpMenu.menuAction(), viewMenu)
        
    def addSubscriptionPlaylistMenuItem(self, label) :
        state = Settings('views').get('subscriptions', True)
        return self.addPlaylistMenuItem(label, 'subscriptions',
                                        self.videoManager.subscriptionPlaylist(), state)
    
    def addDefaultPlaylistMenuItem(self, label, name, defaultState) :
        state = Settings('views').get(name, defaultState)
        return self.addPlaylistMenuItem(label, name, 
                                        self.videoManager.userPlaylist(name), state)
    
    def addPlaylistMenuItem(self, label, name, playlist, state) :
        action = QAction(label, self)
        viewHandler = PlaylistViewHandler(self, label, name, playlist)
        action.setCheckable(True)
        action.setChecked(state)
        action.name = name
        self.actions[label] = action
        if (state) :
            viewHandler.stateChanged(True)
        
        action.toggled.connect(viewHandler.stateChanged)
        self.viewHandlers += [viewHandler]
        return action
            
    def tabCloseRequested(self, index) :
        label = self.tabs.tabText(index)
        self.actions[label].setChecked(False)
                
    def showPlaylist(self, title, playlist) :
        print 'Showing playlist: ' + title
        frame = VideoListFrame(self, playlist, self.videoManager)
        scrollArea = QScrollArea(self.tabs)
        #scrollArea.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        scrollArea.setWidgetResizable(True)
        scrollArea.setWidget(frame)
        
        if self.actions[title].name :
            self.viewSettings.set(self.actions[title].name, True)
        return self.tabs.addTab(scrollArea, title)

    def hidePlaylist(self, label) :
        index = -1
        
        for i in range(self.tabs.count()) : 
            if self.tabs.tabText(i) == label :
                index = i
                break
            
        if self.actions[title].name :
            self.viewSettings.set(self.actions[label].name, False)
        self.tabs.removeTab(index)
        
    def __authenticate(self) :
        try :
            QMessageBox.question(self, _('Authentication required'), 
                                          _('PiTube will now open a browser window to request access to your YouTube account.'))
            self.youtubeservice.authenticate()
            self.actions['authenticate'].setDisabled(True)
        except (ServerNotFoundError) :
            QMessageBox.critical(self, _("Authentication error"), _("Unable to authenticate YouTube account"))        
        
    def channelUploads(self, video) :
        self.showPlaylist(video.channel(), video.channelUploads().execute())
        
    def __settings(self) :
        settingsDialog = SettingsDialog(self)
        settingsDialog.setVisible(True)
    
    def __about(self) :
        icon = QPixmap(APPLICATION_ICON_LARGE)
        aboutBox = QMessageBox(QMessageBox.NoIcon, _('About PiTube'), ABOUT_TEXT, 
                               QMessageBox.Ok, self)
        aboutBox.setStyleSheet('text-align : center')
        aboutBox.setIconPixmap(icon)
        aboutBox.setVisible(True)
        
      
app = QApplication(sys.argv)
app.setApplicationName(APPLICATION_NAME)
app.setApplicationVersion(APPLICATION_VERSION)
Settings.load(SETTINGS_DIR + 'options.xml')
frame = PiTube()
frame.show()
frame.show()
app.exec_()