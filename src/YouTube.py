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

import httplib2
import urllib2
import sys
import os
import re
from datetime import *
import cPickle

from apiclient.discovery import build
from oauth2client.file import Storage
from oauth2client.client import AccessTokenRefreshError
from oauth2client.client import OAuth2WebServerFlow
from oauth2client.tools import *
from oauth2client.client import flow_from_clientsecrets

import argparse
import xml.etree.ElementTree as ET

from constants import *
from VideoManager import *

import pdb

class NotAuthenticatedError(Exception) :
    pass

class tzoffset(tzinfo):
    """Fixed offset in minutes east from UTC."""

    def __init__(self, offset) :
        self.__offset = timedelta(hours = offset)

    def utcoffset(self, dt):
        return self.__offset

    def tzname(self, dt):
        return ''

    def dst(self, dt):
        return ZERO

class YouTubeVideoHandler(VideoHandler) :
    YOUTUBE_VIDEO_URL = "http://www.youtube.com/watch?v=%s"
    DURATION_REGEX = re.compile('PT(\d{0,2}(?=H))?H?(\d{0,2}(?=M))?M?(\d{0,2}(?=S))?S?')
    DATETIME_REGEX = re.compile('(\d\d\d\d)-(\d\d)-(\d\d)T(\d\d):(\d\d):(\d\d).(\d\d\d)([-+]\d\d)?:?(\d\d)?')
    
    def __init__(self, parent, entry) :
        #self.entry = entry
        self.parent = parent

        details = dict()
        details['id'] = entry['id']
        details['url'] = self.YOUTUBE_VIDEO_URL % entry['id']
        details['title'] = entry['snippet']['title']
        details['description'] = entry['snippet']['description']
        details['duration'] = self.parseDuration(entry['contentDetails']['duration'])
        details['durationText'] = self.parseDuration(entry['contentDetails']['duration'], True)
        details['uploadTime'] = self.parseTimestamp(entry['snippet']['publishedAt'])
        details['channel'] = entry['snippet']['channelTitle']
        details['channelId'] = entry['snippet']['channelId']
        details['thumbnail'] = entry['snippet']['thumbnails']['medium']['url']
        
        VideoHandler.__init__(self, parent, details)
                            
    def id(self) :
        return self.details['id']
    
    def __getstate__(self) :
        return self.details
    
    def __setstate__(self, state) :
        self.details = state
        
    def channelUploads() :
        self.service().channelUploads(self.details['channelId'])
        
    @staticmethod
    def parseDuration(duration, text=False) :
        match = YouTubeVideoHandler.DURATION_REGEX.match(duration)
        
        if match :
            values = list(match.groups())
            duration = time(*[int(value) if value != None else 0 for value in values])
            if text :      
                return YouTubeVideoHandler.toCompactTime(duration)
            else :
                return duration.hour * 3600 + duration.minute * 60 + duration.second

        raise ValueError

    @staticmethod
    def toCompactTime(duration) :
        if duration.hour == 0 :
            return '{t.minute}:{t.second:02}'.format(t=duration)
        else :
            return '{t.hour}:{t.minute:02}:{t.second:02}'.format(t=duration)
        
    @staticmethod
    def parseTimestamp(dtstring) :
        match = YouTubeVideoHandler.DATETIME_REGEX.match(dtstring)

        if match :
            values = match.groups()
            dt = datetime(*[int(value) for value in values if value])
            if values[7] :
                 dt.tzinfo = tzoffset(int(values[7]))
                 
            return dt

        raise ValueError

class YouTubeVideoPlaylist(VideoPlaylist) :
    def __init__(self, parent, playlistId, maxResults) :
        details = dict()
        details['id'] = playlistId
        details['maxResults'] = maxResults
        VideoPlaylist.__init__(self, parent, details)
        
    def execute(self) :
        self.details['items'] = self.service().executePlaylistRequest(self.details['id'], min(50, self.details['maxResults']))
        self.details['videos'] = self.details['items'].values()
        return self.details['videos']
    
    def playlistId(self, videoId) :
        for id in self.details['items'].keys() :
            if self.details['items'][id].id() == videoId :
                return id
            
        return ''
    
    def id(self) :
        return self.details['id']
    
    def executed(self) :
        return 'videos' in self.details.keys()
    
    def result(self) :
        return self.details['videos'] if self.executed() else []
    
    def __getstate__(self) :
        return self.details
    
    def __setstate__(self, state) :
        self.details = state
    
class SubscriptionLoader(Thread) :
    def __init__(self, parent, playlist) :
        Thread.__init__(self)
        self.parent = parent
        self.playlist = playlist
        
    def run(self) :
        videos = self.playlist.execute()
        self.parent.videoLock.acquire(True)
        self.parent.videos += videos
        self.parent.threadCount -= 1
        self.parent.videoLock.release()
        
        
class YouTubeSubscriptionPlaylist(VideoPlaylist) :
    def __init__(self, parent, user=None) :
        VideoPlaylist.__init__(self, parent, {})
        self.parent = parent
        self.user = user
        self.videoLock = Lock()
        self.threadCount = 0
        
    def execute(self) :
        channelId = lambda sub : sub['snippet']['resourceId']['channelId']
        subscriptions = self.parent.subscriptions(self.user)
        channelIds = [channelId(sub) for sub in subscriptions]
        
        self.parent.fetchChannelDetails(','.join(channelIds))
        self.videos = []
        
        newCount = lambda sub : sub['contentDetails']['newItemCount']
        for sub in subscriptions :
            if  newCount(sub):
                playlist = self.parent.channelUploads(channelId(sub), newCount(sub))
                SubscriptionLoader(self, playlist).start()
                self.threadCount += 1
                
        while self.threadCount :
            time.sleep(0.1)
            
                                            
        self.videos = sorted(self.videos, lambda x,y: int((y.uploadTime() - 
                                                 x.uploadTime()).total_seconds()))     
        return self.videos
    
class YouTubeSubscriptionPlaylistV2(VideoPlaylist) :
    SUBSCRIPTIONS_URL = 'http://gdata.youtube.com/feeds/api/users/%s/newsubscriptionvideos'
    ENTRY_TAG = '{http://www.w3.org/2005/Atom}entry'
    ID_TAG = '{http://www.w3.org/2005/Atom}id'
    
    def __init__(self, parent, user) :
        VideoPlaylist.__init__(self, parent,  {})
        self.parent = parent
        self.user = user if user != None else parent.userDetails['id']
           
    def execute(self) :
        handle = urllib2.urlopen(self.SUBSCRIPTIONS_URL % self.user)
        tree = ET.parse(handle)
        ids = []
        
        videoId = lambda entry : entry.find(self.ID_TAG).text[-11:]
        self.videos = self.parent.fetchVideos(tree.getroot().findall(self.ENTRY_TAG), 
                                              videoId, videoId)
        handle.close()
        return self.videos.values()
    
    def result(self) :
        return self.videos.values()
        
class YouTubeService(VideoService) :
    CACHE_PATH = SETTINGS_DIR + 'youtube-cache.dat'
    CREDENTIALS_FILE = 'credentials.dat'
    SCOPE = 'https://www.googleapis.com/auth/youtube'
    REDIRECT_URLS = ['urn:ietf:wg:oauth:2.0:oob', 'http://localhost']
    
    def __init__(self, manager) :
        self.__manager = manager
        self.__authenticated = False
        
        self.videoDetails = dict()
        self.channelDetails = dict()
        self.userDetails = None
        self.userPlaylists = None
        self.settings = Settings('youtube')
        
        try :
            cache = open(self.CACHE_PATH, 'rb')
            self.videos = cPickle.load(cache)
            for video in self.videos.values() :
                video.init(self)
                
            self.channels = cPickle.load(cache)
            self.playlists = cPickle.load(cache)
            for playlist in self.playlists.values() :
                playlist.setService(self)
                
            cache.close()
        except (IOError, EOFError, cPickle.PickleError) :
            self.videos = dict()
            self.channels = dict()
            self.playlists = dict()
        
        self.storage = Storage(SETTINGS_DIR + self.CREDENTIALS_FILE)
        self.credentials = self.storage.get()
        
    def cleanup(self) :
        cache = open(self.CACHE_PATH, 'wb')
        cPickle.dump(self.videos, cache, -1)
        cPickle.dump(self.channels, cache, -1)
        cPickle.dump(self.playlists, cache, -1)
        print "Writing cache file to " + self.CACHE_PATH
        cache.close()
    
    def url(self) :
        return 'youtube.com'
    
    def postAuthentication(self) :
        self.userDetails = self.fetchChannelDetails()[0]
        self.userPlaylists = self.userDetails['contentDetails']['relatedPlaylists']
                
    def manager(self) :
        return self.__manager
    
    def authenticate(self) :      
        flow = flow_from_clientsecrets('client_secrets.json', self.SCOPE, self.REDIRECT_URLS)
        flags = argparser.parse_args("")
        self.credentials = run_flow(flow, self.storage, flags)
                
    def isAuthenticated(self) :
        return self.credentials and not self.credentials.invalid

    def unauthenticate(self) :
        os.remove('credentials.dat')
        self.__authenticated = False

    def serviceInstance(self) :
        if self.isAuthenticated() :
            http = httplib2.Http()
            http.disable_ssl_certificate_validation = True
            http = self.credentials.authorize(http)
        
            service = build('youtube', 'v3', http=http)
            
            return service
        
        raise NotAuthenticatedError

    def executePlaylistRequest(self, playlistId, maxResults) :
        options = { 'part' : 'snippet, contentDetails',  'maxResults' : maxResults, 
                   'playlistId' : playlistId,
                   'fields' : 'items/id, items/snippet/resourceId/videoId'}
        playlist = self._executeListRequest(self.serviceInstance().playlistItems(), 
                                               options, maxResults == 50)
        videoId = lambda val : val['snippet']['resourceId']['videoId']
        playlistId = lambda val : val['id']
        
        return self.fetchVideos(playlist, videoId, playlistId)
        
    def fetchVideos(self, playlist, videoId, playlistId) :
        offset = 0
        
        #Get video details that are not already cached
        while offset < len(playlist) :
            count = min(50, len(playlist) - offset) + offset
            ids = [videoId(item) for item in playlist[offset:count]
                    if not videoId(item) in self.videos.keys()]
            
            if len(ids) > 0 :
                options = {'part' : 'snippet, contentDetails', 
                           'maxResults' : 50, 'id' : ','.join(ids)}
                videolist = self._executeListRequest(self.serviceInstance().videos(), options)
                
                #Cache the new items into self.videoDetails
                for item in videolist :
                    self.videos[item['id']] = YouTubeVideoHandler(self, item)
            
            offset += 50
            
        
        return {playlistId(item) : self.videos[videoId(item)] for item in playlist}
    
    def _executeListRequest(self, requestObj, options, multipage = True) : 
        if not self.isAuthenticated() :
            raise NotAuthenticatedError
        
        request = requestObj.list(**options)
        items = []
                    
        while request :
            response = request.execute()
            
            if 'error' in response :
                print response
                break
            
            items += response['items']
            
            if multipage :
                request = requestObj.list_next(request, response)
            else :
                request = None
                
        return items
    
    def _executeInsertRequest(self, requestObj, options) :
        request = requestObj.insert(**options)
        return request.execute()
    
    def _executeDeleteRequest(self, requestObj, options) :
        request = requestObj.delete(**options)
        return request.execute()
   
 
    def fetchChannelDetails(self, id=None) :
        options = { 'part' : 'snippet, contentDetails, id' }
        
        if id :
            options['id'] =  id
        else :
            options['mine'] = True
            
        result = self._executeListRequest(self.serviceInstance().channels(), options) 
        
        for item in result :
            self.channelDetails[item['id']] = item
            
        return result

    def channelUploads(self, id, maxResults = 50) :
        if not id in self.channelDetails :
            self.fetchChannelDetails(id)
            
        details = self.channelDetails[id]
        print "Getting %d videos for %s" % (maxResults , details['snippet']['title'])
        
        return self.playlist(details['contentDetails']['relatedPlaylists']['uploads'], maxResults)
            
    def subscriptions(self, user=None) :
        request = None
        options = { 'part' : 'snippet, contentDetails' }
        
        if user :
            options['channelId'] = user            
        else :
            options['mine'] = True
                    
        return self._executeListRequest(self.serviceInstance().subscriptions(), options)
    
    def subscriptionPlaylist(self, user=None) :
        if self.settings.get('quicksubscriptions', True) :
            return  YouTubeSubscriptionPlaylistV2(self, user)
        else :
            return YouTubeSubscriptionPlaylist(self, user)
    
    def playlist(self, id, maxResults = 50) :
        if not id in self.playlists.keys() :
            self.playlists[id] = YouTubeVideoPlaylist(self, id, maxResults)
            
        return self.playlists[id]
        
    def userPlaylistNames(self) :
        return ['favorites', 'watchLater', 'watchHistory', 'likes']

    def userPlaylist(self, name) :
        return self.playlist(self.userPlaylists[name])
    

    def addToPlaylist(self, video, playlist) :
        videoid = video if not hasattr(video, 'id') else video.id()
        playlistId = playlist if not hasattr(playlist, 'id') else playlist.id()
        snippet = { 'playlistId' : playlistId, 'resourceId' : { 'videoId' : videoid, 'kind' : 'youtube#video' } }
        options = { 'part' : 'snippet', 'body' : { 'snippet' : snippet } }
        self._executeInsertRequest(self.serviceInstance().playlistItems(), options)
               
    def removeFromPlaylist(self, video, playlist) :
        videoid = video if not hasattr(video, 'id') else video.id()
        playlistId = playlist.playlistId(videoid)
        options = { 'id' : playlistId }
        self._executeDeleteRequest(self.serviceInstance().playlistItems(), options)
        
