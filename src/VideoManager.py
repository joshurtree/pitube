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

from threading import *
import thread
import re
from cStringIO import StringIO
import urllib
from constants import *
import subprocess
from Settings import Settings
from datetime import datetime
from multire import multire
import os
import pdb

class PlaylistNotFoundError(Exception) :
    pass

class VideoHandler :
    YOUTUBE_DL_CMD = 'youtube-dl'
    YOUTUBE_DL_ARGS = '--no-part --newline -no-mtime -o %s %s'
    DECIMAL_MATCH = '\d*?\.?\d*?'
    DOWNLOAD_INFO_FIELDS = ['percent', 'size', 'sizeUnit', 'dataRate', 'dataRateUnit', 'eta' ]
    COMPLETION_INFO_FIELDS = ['size', 'time']
    
    YOUTUBE_DL_REGEX = [
       re.compile('.*?({dec})%\sof\s({dec})(\w\w\w)\sat\s({dec})(\w\w\w/s)\sETA\s(\d\d:\d\d).*'.format(dec=DECIMAL_MATCH)),
       re.compile('.*?{dec}%\sof\s({dec})\sin\s(\d\d:\d\d)'),
       re.compile('.*has already been downloaded'),
    ]
    YOUTUBE_MATCHES = multire(YOUTUBE_DL_REGEX)
    YOUTUBE_DL_FIELDS = [DOWNLOAD_INFO_FIELDS, COMPLETION_INFO_FIELDS, []]
    DEFAULT_DL_INFO = { 'percent' : 0.0 }
    
    def __init__(self, service, details) :
        self.details = details
        self.details['downloadInfo'] = self.DEFAULT_DL_INFO
        self.init(service)
        
    def init(self, service) :
        self.__service = service
        self.__service = service
        self.manager = service.manager()
        self.__thumbnail = None
        self.manager.addVideo(self)
        self.downloadProcess = None
        
    def downloadThumbnail(self) :
        filename = self.manager.thumbnailDir() + self.thumbnailUrl().replace('/', '_')
        
        if not os.path.exists(filename) :
            thumbnailFile = open(filename, 'wb')
            thumbnailFile.write(urllib.urlopen(self.thumbnailUrl()).read())
            thumbnailFile.close()
            
        self.__thumbnail = filename
        
    def thumbnailUrl(self) :
        return self.details['thumbnail']
         
    def url(self) :
        return self.details['url']
    
    def title(self) :
        return self.details['title']
    
    def description(self) :
        return self.details['description']
    
    def durationText(self) :
        return self.details['durationText']
    
    def duration(self) :
        return self.details['duration']
    
    def uploadTime(self) :
        return self.details['uploadTime']

    def channel(self) :
        return self.details['channel']
    
    def channelId(self) :
        return self.details['channelId']
    
    def service(self) :
        return self.__service
    
    def thumbnail(self) :
        return self.__thumbnail
    
    def startDownload(self) :
        if not self.downloadProcess :
            args = self.YOUTUBE_DL_ARGS % (self.filename(), self.url())
            self.downloadProcess = subprocess.Popen([self.YOUTUBE_DL_CMD] +
                                                 args.split(), 0, None, subprocess.PIPE, subprocess.PIPE)
            Timer(0.5, self.__updateDownloadInfo, ()).start()
            
	    
    def stopDownload(self) :
        if self.downloadProcess :
            self.downloadProcess.terminate()
    
    def removeFile(self) :
        try :
            if os.path.exists(self.filename()) :
                os.remove(self.filename())
                
            self.details['downloadInfo'] = self.DEFAULT_DL_INFO
        except Exception, e :
            print e
            
    def filename(self) :
        return self.manager.videoDir() + self.url().replace('/', '_')
    
    def __updateDownloadInfo(self) :
        if self.downloadProcess == None :
            return

        try :
            line = self.downloadProcess.stdout.readline()
            index = self.YOUTUBE_MATCHES.match(line)
            
            if index in (0, 1) :
                self.details['downloadInfo'] = dict(zip(self.YOUTUBE_DL_FIELDS[index], self.YOUTUBE_MATCHES.lastmatch.groups()))
            
            if index >= 1 :
                self.details['downloadInfo']['percent'] = 100.0
                return
        except EOFError :
            return
                        
        
    # Produces an dict object with download info
    def downloadInfo(self) :   
        self.__updateDownloadInfo()
        return self.details['downloadInfo'] if 'downloadInfo' in self.details.keys() else self.DEFAULT_DL_INFO
    
    def durationDownloaded(self) :
        if not self.startedDownload() :
            return 0.0
        
        if self.finishedDownload() :
            return self.duration()
        
        downloadInfo = self.downloadInfo()
        
        if not downloadInfo :
            return 0.0  
        
        downloaded = float(self.duration())*(float(self.downloadInfo()['percent'])/100.0)
        #print "Downloaded %s%% of %d giving %d seconds" % (self.downloadInfo()['percent'], self.duration(), downloaded)
        return float(self.duration())*(float(self.downloadInfo()['percent'])/100.0)
    
    def startedDownload(self) :
        return self.downloadProcess <> None
    
    def finishedDownload(self) :
        return self.downloadInfo()['percent'] == 100.0 if 'percent' in self.downloadInfo().keys() else False
        
    def __str__(self) :
        value = 'URL: ' + self.url() + '\n'
        value += 'Title: ' + self.title() + '\n'
        value += 'Channel: ' + self.channel() + '\n'
        value += 'Duration: ' + str(self.duration()) + '\n'
        value += 'Date uploaded: ' + str(self.uploadTime()) + '\n'
        value += 'Thumbnail URL: ' + self.thumbnailUrl() + '\n'
        return value
        
class VideoManager :
    def __init__(self) :
        self.videos = dict()
        self.services = dict()
        self.locSettings = Settings('location')
        self.storageSettings = Settings('storage')
        
        if not os.path.exists(self.thumbnailDir()) :
            os.mkdir(self.thumbnailDir())
            
        if not os.path.exists(self.videoDir()) :
            os.mkdir(self.videoDir())
    
    def cleanup(self) :
        videotimelimit = self.storageSettings.get('videotimelimit', 7)
        for video in self.videos.values() :
            filepath = video.filename()
            
            if os.path.exists(filepath) :
                modifydate = datetime.fromtimestamp(os.stat(filepath).st_mtime)
                timeSinceModify = datetime.now() - modifydate
                
                if timeSinceModify.days >=  videotimelimit :
                    os.remove(filepath)
                
            thumbnailpath = video.thumbnail()
            
            if thumbnailpath and os.path.exists(thumbnailpath) :
                accessdate = datetime.fromtimestamp(os.stat(thumbnailpath).st_atime)
                timeSinceAccess = datetime.now() - accessdate
                
                if timeSinceAccess.days >= 7 :
                    os.remove(thumbnailpath)
        
    def addService(self, name, service) :
        self.services[name] = service
        
    def thumbnailDir(self) :
        return DATA_DIR + 'thumbnails/' 

    def videoDir(self) :
        return self.locSettings.get('videos', DATA_DIR + 'videos/')
    
    def addVideo(self, video) :
        self.videos[video.url()] = video
        
    def userPlaylist(self, name) :
        playlist = CompositeVideoPlaylist()
        
        for service in self.services.values() :
            playlist.addPlaylist(service.userPlaylist(name))
            
        return playlist
    
    def subscriptionPlaylist(self) :
        playlist = CompositeVideoPlaylist()
        
        for service in self.services.values() :
            playlist.addPlaylist(service.subscriptionPlaylist())
            
        return playlist
                
    def playlist(self, id) :
        return self.services.values()[0].playlist(id)
    
          
class VideoPlaylist :
    def __init__(self, service, details) :
        self.__service = service
        self.details = details
        
    def add(self, video) :
        self.service().addToPlaylist(video, self)
        
    def remove(self, video) :
        self.service().removeFromPlaylist(video, self)
        
    def update(self, video, include) :
        if include :
            self.service().addToPlaylist(video, self)
        else :
            self.service().removeFromPlaylist(video, self)
        
        self.listener()
            
    def setUpdateListener(self, listener) :
        self.listener = listener
            
    def contains(self, video) :
        return video in self.result()
    
    def setService(self, service) :
        self.__service = service
        
    def service(self) :
        return self.__service
    
    def execute(self) :
        raise NotImplementedError
    
    def result(self) :
        raise NotImplementedError
    
    
class CompositeVideoPlaylist :
    def __init__(self) :
        self.playlists = []
    
    def addPlaylist(self, playlist) :
        self.playlists += [playlist]
        
    def execute(self) :
        videos = []
        for playlist in self.playlists :
            videos += playlist.execute()
        
        self.videos = videos
        return videos
    
    def result(self) :
        return self.videos
    
    def setUpdateListener(self, listener) :
        for playlist in self.playlists :
            playlist.listener = listener
 
class VideoService :
    def url(self) :
        raise NotImplementedError
    
    def manager(self) :
        raise NotImplementedError
    
    def subscriptionPlaylist(self) :
        raise NotImplementedError
    
    def userPlaylist(self, name) :
        raise NotImplementedError
    
    def playlist(id, maxResults) :
        raise NotImplementedError
    
    def channelUploads(id) :
        raise NotImplementedError
    
    
        