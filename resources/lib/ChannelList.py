#   Copyright (C) 2011 Jason Anderson
#
#
# This file is part of PseudoTV.
#
# PseudoTV is free software: you can redistribute it and/or modify
# it under the terms of the GNU General Public License as published by
# the Free Software Foundation, either version 3 of the License, or
# (at your option) any later version.
#
# PseudoTV is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
# GNU General Public License for more details.
#
# You should have received a copy of the GNU General Public License
# along with PseudoTV.  If not, see <http://www.gnu.org/licenses/>.

from __future__ import annotations
import xbmc, xbmcgui, xbmcaddon, xbmcvfs
import importlib
import subprocess, os, traceback
import time, threading
import datetime
import sys, re
import random
import json
from heapq import nlargest

importlib.reload(sys)
#sys.setdefaultencoding('utf-8')

from xml.dom.minidom import parse, parseString

from Playlist import Playlist
from Globals import *
from Channel import Channel
from VideoParser import VideoParser
from FileAccess import FileLock, FileAccess

class ChannelList:
    def __init__(self):
        self.networkList = []
        self.studioList = []
        self.mixedGenreList = []
        self.showGenreList = []
        self.movieGenreList = []
        self.showList = []
        self.channels: dict[int,Channel] = {}
        self.videoParser = VideoParser()
        self.sleepTime = 0
        self.threadPaused = False
        self.runningActionChannel = 0
        self.runningActionId = 0
        self.enteredChannelCount = 0
        self.background = True
        random.seed()

    def readConfig(self):
        self.channelResetSetting = int(ADDON.getSetting("ChannelResetSetting"))
        self.log('Channel Reset Setting is ' + str(self.channelResetSetting))
        self.forceReset = ADDON.getSetting('ForceChannelReset') == "true"
        self.log('Force Reset is ' + str(self.forceReset))
        self.updateDialog = xbmcgui.DialogProgress()
        self.startMode = int(ADDON.getSetting("StartMode"))
        self.log('Start Mode is ' + str(self.startMode))
        self.backgroundUpdating = int(ADDON.getSetting("ThreadMode"))
        self.mediaLimit = MEDIA_LIMIT[int(ADDON.getSetting("MediaLimit"))]
        self.YearEpInfo = ADDON.getSetting('HideYearEpInfo')
        self.findMaxChannels()

        if self.forceReset:
            ADDON.setSetting('ForceChannelReset', "False")
            self.forceReset = False

        try:
            self.lastResetTime = int(ADDON_SETTINGS.getSetting("LastResetTime"))
        except:
            self.lastResetTime = 0

        try:
            self.lastExitTime = int(ADDON_SETTINGS.getSetting("LastExitTime"))
        except:
            self.lastExitTime = int(time.time())

    def setupList(self) -> dict[int, Channel]:
        self.readConfig()
        self.updateDialog.create(ADDON_NAME, LANGUAGE(30167))
        self.updateDialog.update(0, LANGUAGE(30167))
        self.updateDialogProgress = 0
        foundvalid = False
        makenewlists = False
        self.background = False

        if self.backgroundUpdating > 0 and self.myOverlay.isMaster is True:
            makenewlists = True

        # Go through all channels, create their lists, and setup the new playlist
        for i in range(1, self.maxChannels + 1):
            self.updateDialogProgress = i * 100 // self.enteredChannelCount
            self.updateDialog.update(self.updateDialogProgress, '\n'.join([LANGUAGE(30166) % (str(i)), LANGUAGE(30165)]))

            # If the user pressed cancel, stop everything and exit
            if self.updateDialog.iscanceled():
                self.log('Update channels cancelled')
                self.updateDialog.close()
                return None

            self.setupChannel(i, False, makenewlists, False)
            foundvalid |= self.channels[i].isValid

        if makenewlists is True:
            ADDON.setSetting('ForceChannelReset', 'false')

        if foundvalid is False and makenewlists is False:
            for i in  range(1, self.maxChannels + 1):
                self.updateDialogProgress = i * 100 // self.enteredChannelCount
                self.updateDialog.update(self.updateDialogProgress, '\n'.join([LANGUAGE(30168) % (str(i)), LANGUAGE(30165)]))
                self.setupChannel(i, False, True, False)

                if self.channels[i].isValid:
                    foundvalid = True
                    break

        self.updateDialog.update(100, LANGUAGE(30170))
        self.updateDialog.close()

        return self.channels

    def log(self, msg, level = xbmc.LOGDEBUG):
        log('ChannelList: ' + msg, level)

    # Determine the maximum number of channels by reading max channel in Settings file
    def findMaxChannels(self):
        self.log('findMaxChannels')
        self.maxChannels = 0
        self.enteredChannelCount = 0

        # recreate use settings-channels instead
        try:
            settingChannels = [channel for channel in ADDON_SETTINGS.currentSettings.items() if '_type' in channel[0] ]
            for settingName, settingValue in settingChannels:
                iChannel = int(settingName.replace("Channel_", "").replace("_type", ""))
                chtype = int(settingValue)
                if iChannel > self.maxChannels:
                    self.maxChannels = iChannel

                if self.forceReset and (chtype != 9999):
                    ADDON_SETTINGS.setSetting(settingName.replace("_type", "_changed"), "True")

                self.enteredChannelCount += 1
        except Exception as e:
            raise Exception("findMaxChannels exception:", str(e),  str(ADDON_SETTINGS.currentSettings))

        self.log('findMaxChannels return ' + str(self.maxChannels))

    def setupChannel(self, channelNumber: int, background = False, makenewlist = False, append = False):
        self.log('setupChannel ' + str(channelNumber))
        returnval = False
        createlist = makenewlist
        chtype = 9999
        chsetting1 = ''
        chsetting2 = ''
        needsreset = False
        self.background = background
        self.settingChannel = channelNumber
        channelBaseName = 'Channel_' + str(channelNumber)

        try:
            chtype = int(ADDON_SETTINGS.getSetting(channelBaseName + '_type'))
            chsetting1 = ADDON_SETTINGS.getSetting(channelBaseName + '_1')
            chsetting2 = ADDON_SETTINGS.getSetting(channelBaseName + '_2')
        except:
            pass

        curChannel = self.channels.get(channelNumber, Channel())
        if not channelNumber in self.channels:
            self.channels[channelNumber] = curChannel

        if chtype == 9999:
            curChannel.isValid = False
            return False

        curChannel.isSetup = True
        curChannel.loadRules(channelNumber)
        self.runActions(RULES_ACTION_START, channelNumber, curChannel)

        try:
            needsreset = ADDON_SETTINGS.getSetting(channelBaseName + '_changed') == 'True'

            if needsreset:
                curChannel.isSetup = False
        except:
            pass

        # If possible, use an existing playlist
        # Don't do this if we're appending an existing channel
        # Don't load if we need to reset anyway
        if FileAccess.exists(CHANNELS_LOC + channelBaseName + '.m3u') and append == False and needsreset == False:
            try:
                #self.channelsDic[channel].totalTimePlayed = int(ADDON_SETTINGS.getSetting(channelBaseName + '_time', True))
                curChannel.totalTimePlayed = int(ADDON_SETTINGS.getSetting(channelBaseName + '_time', False))
                createlist = True

                if not self.background:
                    self.updateDialog.update(self.updateDialogProgress, '\n'.join([LANGUAGE(30166) % (str(channelNumber)), LANGUAGE(30171)]))

                if curChannel.setPlaylist(CHANNELS_LOC + channelBaseName + '.m3u') is True:			####
                    curChannel.isValid = True
                    curChannel.fileName = CHANNELS_LOC + channelBaseName + '.m3u'
                    returnval = True

                    # If this channel has been watched for longer than it lasts, reset the channel
                    if self.channelResetSetting == 0 and curChannel.totalTimePlayed < curChannel.getTotalDuration():
                        createlist = False

                    if self.channelResetSetting > 0 and self.channelResetSetting < 4:
                        timedif = time.time() - self.lastResetTime

                        if self.channelResetSetting == 1 and timedif < (60 * 60 * 24):
                            createlist = False

                        if self.channelResetSetting == 2 and timedif < (60 * 60 * 24 * 7):
                            createlist = False

                        if self.channelResetSetting == 3 and timedif < (60 * 60 * 24 * 30):
                            createlist = False

                        if timedif < 0:
                            createlist = False

                    if self.channelResetSetting == 4:
                        createlist = False
            except:
                pass

        if createlist or needsreset:
            curChannel.isValid = False

            if makenewlist:
                try:
                    os.remove(CHANNELS_LOC + channelBaseName + '.m3u')
                except:
                    pass

                append = False

                if createlist:
                    ADDON_SETTINGS.setSetting('LastResetTime', str(int(time.time())))

        if append is False:
            if chtype == 6 and chsetting2 == str(MODE_ORDERAIRDATE):
                curChannel.mode = MODE_ORDERAIRDATE

            # if there is no start mode in the channel mode flags, set it to the default
            if curChannel.mode & MODE_STARTMODES == 0:
                if self.startMode == 0:
                    curChannel.mode |= MODE_RESUME
                elif self.startMode == 1:
                    curChannel.mode |= MODE_REALTIME
                elif self.startMode == 2:
                    curChannel.mode |= MODE_RANDOM

        if ((createlist or needsreset) and makenewlist) or append:
            if not self.background:
                self.updateDialogProgress = (channelNumber) * 100 // self.enteredChannelCount
                self.updateDialog.update(self.updateDialogProgress, '\n'.join([LANGUAGE(30168) % (str(channelNumber)), LANGUAGE(30172)]))

            if self.makeChannelList(channelNumber, chtype, chsetting1, chsetting2, append):
                if curChannel.setPlaylist(CHANNELS_LOC + channelBaseName + '.m3u'):
                    returnval = True
                    curChannel.fileName = CHANNELS_LOC + channelBaseName + '.m3u'
                    curChannel.isValid = True

                    # Don't reset variables on an appending channel
                    if append is False:
                        curChannel.totalTimePlayed = 0
                        ADDON_SETTINGS.setSetting(channelBaseName + '_time', '0')

                        if needsreset:
                            ADDON_SETTINGS.setSetting(channelBaseName + '_changed', 'False')
                            curChannel.isSetup = True

        self.runActions(RULES_ACTION_BEFORE_CLEAR, channelNumber, curChannel)

        # Don't clear history when appending channels
        if not self.background and not append and self.myOverlay.isMaster:
            self.updateDialogProgress = (channelNumber) * 100 // self.enteredChannelCount
            self.updateDialog.update(self.updateDialogProgress, '\n'.join([LANGUAGE(30166) % (str(channelNumber)), LANGUAGE(30173)]))
            self.clearPlaylistHistory(channelNumber)

        if not append:
            self.runActions(RULES_ACTION_BEFORE_TIME, channelNumber, curChannel)

            if curChannel.mode & MODE_ALWAYSPAUSE > 0:
                curChannel.isPaused = True

            if curChannel.mode & MODE_RANDOM > 0:
                curChannel.showTimeOffset = random.randint(0, curChannel.getTotalDuration())

            if curChannel.mode & MODE_REALTIME > 0:
                timedif = int(self.myOverlay.timeStarted) - self.lastExitTime
                curChannel.totalTimePlayed += timedif

            if curChannel.mode & MODE_RESUME > 0:
                curChannel.showTimeOffset = curChannel.totalTimePlayed
                curChannel.totalTimePlayed = 0

            while curChannel.showTimeOffset > curChannel.getCurrentDuration():
                curChannel.showTimeOffset -= curChannel.getCurrentDuration()
                curChannel.addShowPosition(1)

        curChannel.name = self.getChannelName(chtype, chsetting1)

        if ((createlist or needsreset) and makenewlist) and returnval:
            self.runActions(RULES_ACTION_FINAL_MADE, channelNumber, curChannel)
        else:
            self.runActions(RULES_ACTION_FINAL_LOADED, channelNumber, curChannel)

        return returnval

    def clearPlaylistHistory(self, channelNumber):
        self.log("clearPlaylistHistory")
        currentChannel = self.channels[channelNumber]
        if currentChannel.isValid == False:
            self.log("channel not valid, ignoring")
            return

        # if we actually need to clear anything
        if currentChannel.totalTimePlayed > (60 * 60 * 24 * 2):
            try:
                fle = FileAccess.open(CHANNELS_LOC + 'channel_' + str(channelNumber) + '.m3u', 'w')
            except:
                self.log("clearPlaylistHistory Unable to open the smart playlist", xbmc.LOGERROR)
                return

            flewrite = uni("#EXTM3U\n")
            tottime = 0
            timeremoved = 0

            for i in range(currentChannel.Playlist.size()):
                tottime += currentChannel.getItemDuration(i)

                if tottime > (currentChannel.totalTimePlayed - (60 * 60 * 12)):            #todo: refactor using playlistitem class
                    tmpstr = str(currentChannel.getItemDuration(i)) + ','
                    tmpstr += currentChannel.getItemTitle(i) + "//" + currentChannel.getItemEpisodeTitle(i) + "//" + currentChannel.getItemDescription(i)
                    tmpstr = uni(tmpstr[:2036])
                    tmpstr = tmpstr.replace("\\n", " ").replace("\\r", " ").replace("\\\"", "\"")
                    tmpstr = uni(tmpstr) + uni('\n') + uni(currentChannel.getItemFilename(i))
                    flewrite += uni("#EXTINF:") + uni(tmpstr) + uni("\n")
                else:
                    timeremoved = tottime

            fle.write(flewrite)
            fle.close()

            if timeremoved > 0:
                if currentChannel.setPlaylist(CHANNELS_LOC + 'channel_' + str(channelNumber) + '.m3u') is False:
                    currentChannel.isValid = False
                else:
                    currentChannel.totalTimePlayed -= timeremoved
                    # Write this now so anything sharing the playlists will get the proper info
                    ADDON_SETTINGS.setSetting('Channel_' + str(channelNumber) + '_time', str(currentChannel.totalTimePlayed))

    def getChannelName(self, chtype, setting1):
        self.log('getChannelName ' + str(chtype))

        if len(setting1) == 0:
            return ''

        if chtype == 0:
            return self.getSmartPlaylistName(setting1)
        elif chtype == 1 or chtype == 2 or chtype == 5 or chtype == 6:
            return setting1
        elif chtype == 3:
            return setting1 + " TV"
        elif chtype == 4:
            return setting1 + " Movies"
        elif chtype == 7:
            if setting1[-1] == '/' or setting1[-1] == '\\':
                return os.path.split(setting1[:-1])[1]
            else:
                return os.path.basename(setting1)

        return ''

    # Open the smart playlist and read the name out of it...this is the channel name
    def getSmartPlaylistName(self, fle):
        self.log('getSmartPlaylistName')
        fle = xbmcvfs.translatePath(fle)

        try:
            xml = FileAccess.open(fle, "r")
        except:
            self.log("getSmartPlaylistName Unable to open the smart playlist " + fle, xbmc.LOGERROR)
            return ''

        try:
            dom = parse(xml)
        except:
            self.log('getSmartPlaylistName Problem parsing playlist ' + fle, xbmc.LOGERROR)
            xml.close()
            return ''

        xml.close()

        try:
            plname = dom.getElementsByTagName('name')
            self.log('getSmartPlaylistName return ' + plname[0].childNodes[0].nodeValue)
            return plname[0].childNodes[0].nodeValue
        except:
            self.log("Unable to get the playlist name.", xbmc.LOGERROR)
            return ''

    def validatePlaylistFileRule(self, dom, setting1, dir_name):
        self.log('validatePlaylistFileRule')

        try:
            rules = dom.getElementsByTagName('rule')
        except:
            self.log('validatePlaylistFileRule Problem parsing playlist ' + setting1, xbmc.LOGERROR)
            return

        try:
            updateLocalFile = False
            for rule in (rule for rule in rules if 'playlist' == rule.getAttribute("field")):

                playlistName = rule.firstChild.nodeValue

                if FileAccess.exists(playlistName):  #playlistName is full filepath
                    FileAccess.copy(playlistName, xbmcvfs.translatePath('special://profile/playlists/video/') + os.path.basename(playlistName))
                    rule.firstChild.nodeValue = os.path.basename(playlistName)
                    updateLocalFile = True

                elif FileAccess.exists(os.path.join(os.path.dirname(setting1), playlistName)): #check relative path of (parent) channel playlist
                    FileAccess.copy(os.path.join(os.path.dirname(setting1), playlistName), xbmcvfs.translatePath('special://profile/playlists/video/') + playlistName)

                elif FileAccess.exists(xbmcvfs.translatePath('special://profile/playlists/video/') + playlistName): #check local directory
                    pass

                else:
                    self.log("validatePlaylistFileRule Problems locating playlist rule file " + playlistName )

            if updateLocalFile : #update playlist value to local name (modify the curernt playlist(local copy))
                try:
                    fs = FileAccess.open(dir_name, "w")
                    fs.write( dom.toxml() )
                    fs.close()
                except Exception as e:
                    self.log('validatePlaylistFileRule Problem updating local Playlist File ' + dir_name + '\n exception:' + str(e), xbmc.LOGERROR)

        except Exception as e:
            self.log('validatePlaylistFileRule Problem looping rules ' + setting1 + '\n exception:' + str(e), xbmc.LOGERROR)

        self.log("validatePlaylistFileRule returning")
        return

    # Based on a smart playlist, create a normal playlist that can actually be used by us
    def makeChannelList(self, channelNumber, chtype, setting1, setting2, append = False) -> bool:
        self.log('makeChannelList ' + str(channelNumber))
        israndom = True
        fileList = []
        channelplaylistPath = CHANNELS_LOC + "channel_" + str(channelNumber) + ".m3u"

        if self.channels[channelNumber].isSkipped == True:
            self.log("channel set to skip, ignoring")
            return False

        if chtype == 7:
            fileList = self.createDirectoryPlaylist(setting1)
            israndom = True
        else:
            if chtype == 0:
                if FileAccess.copy(setting1, MADE_CHAN_LOC + os.path.basename(setting1)) == False:
                    if FileAccess.exists(MADE_CHAN_LOC + os.path.basename(setting1)) == False:
                        self.log("Unable to copy or find playlist " + setting1)
                        return False

                fle = MADE_CHAN_LOC + os.path.basename(setting1)
            else:
                fle = self.makeTypePlaylist(chtype, setting1, setting2)

            fle = uni(fle)

            if len(fle) == 0:
                self.log('Unable to locate the playlist for channel ' + str(channelNumber), xbmc.LOGERROR)
                return False

            try:
                xml = FileAccess.open(fle, "r")
            except:
                self.log("makeChannelList Unable to open the smart playlist " + fle, xbmc.LOGERROR)
                return False

            try:
                dom = parse(xml)
            except:
                self.log('makeChannelList Problem parsing playlist ' + fle, xbmc.LOGERROR)
                xml.close()
                return False

            xml.close()

            #playlist rule prep/validate
            if chtype == 0:
                self.validatePlaylistFileRule(dom,setting1, fle)

            if self.getSmartPlaylistType(dom) == 'mixed':
                fileList = self.buildMixedFileList(dom, channelNumber)
            else:
                fileList = self.buildFileList(fle, channelNumber)

            try:
                order = dom.getElementsByTagName('order')

                if order[0].childNodes[0].nodeValue.lower() == 'random':
                    israndom = True
            except:
                pass

        try:
            if append is True:
                channelplaylist = FileAccess.open(channelplaylistPath, "r")
                channelplaylist.seek(0, 2)
                channelplaylist.close()
            else:
                channelplaylist = FileAccess.open(channelplaylistPath, "w")
        except:
            self.log('Unable to open the cache file ' + channelplaylistPath , xbmc.LOGERROR)
            return False

        if append is False:
            channelplaylist.write(uni("#EXTM3U\n"))

        if israndom:
            random.shuffle(fileList)

        if len(fileList) > 16384:
            fileList = fileList[:16384]

        fileList = self.runActions(RULES_ACTION_LIST, channelNumber, fileList)
        self.channels[channelNumber].isRandom = israndom

        if append:
            if len(fileList) + self.channels[channelNumber].Playlist.size() > 16384:
                fileList = fileList[:(16384 - self.channels[channelNumber].Playlist.size())]
        else:
            if len(fileList) > 16384:
                fileList = fileList[:16384]

        # Write each entry into the new playlist
        for string in fileList:
            channelplaylist.write(uni("#EXTINF:") + uni(string) + uni("\n"))

        channelplaylist.close()
        self.log('makeChannelList return')
        return True

    def makeTypePlaylist(self, chtype, setting1, setting2):
        if chtype == 1:
            if len(self.networkList) == 0:
                self.log('chtype = 1: About to fill the tv info because the network list size is 0')
                self.fillTVInfo()

            return self.createNetworkPlaylist(setting1)
        elif chtype == 2:
            if len(self.studioList) == 0:
                self.fillMovieInfo()

            return self.createStudioPlaylist(setting1)
        elif chtype == 3:
            if len(self.showGenreList) == 0:
                self.log('Chtype = 3: About to fill the tv info because the genre list size is 0')
                self.fillTVInfo()

            return self.createGenrePlaylist('episodes', chtype, setting1)
        elif chtype == 4:
            if len(self.movieGenreList) == 0:
                self.fillMovieInfo()

            return self.createGenrePlaylist('movies', chtype, setting1)
        elif chtype == 5:
            if len(self.mixedGenreList) == 0:
                if len(self.showGenreList) == 0:
                    self.log('chtype 5, mixedGenreList len 0, genreList is 0: About to fill the tv info')
                    self.fillTVInfo()

                if len(self.movieGenreList) == 0:
                    self.fillMovieInfo()

                self.mixedGenreList = self.makeMixedList(self.showGenreList, self.movieGenreList)
                self.mixedGenreList.sort(key=lambda x: x.lower())

            return self.createGenreMixedPlaylist(setting1)
        elif chtype == 6:
            if len(self.showList) == 0:
                self.log('chtype 6: About to fill the tv info because the show list size is 0')
                self.fillTVInfo()

            return self.createShowPlaylist(setting1, setting2)

        self.log('makeTypePlaylists invalid channel type: ' + str(chtype))
        return ''


    def createNetworkPlaylist(self, network):
        flename = xbmcvfs.makeLegalFilename(GEN_CHAN_LOC + 'Network_' + network + '.xsp')
        network =  self.cleanString(network)

        try:
            self.log('createNetworkPlaylist: about to open filename ' + flename)
            fle = FileAccess.open(flename, "w")
        except:
            self.log(LANGUAGE(30034) + ' ' + flename, xbmc.LOGERROR)
            return ''

        self.writeXSPHeader(fle, "episodes", self.getChannelName(1, network))
        self.writeXSPRule(fle, "Studio", "is", network)
        self.writeXSPFooter(fle, 0, "random")
        fle.close()

        return flename


    def createShowPlaylist(self, show, setting2):
        order = 'random'

        try:
            setting = int(setting2)

            if setting & MODE_ORDERAIRDATE > 0:
                order = 'episode'
        except:
            pass

        flename = xbmcvfs.makeLegalFilename(GEN_CHAN_LOC + 'Show_' + uni(show) + '_' + order + '.xsp')
        show = self.cleanString(show)

        try:
            fle = FileAccess.open(flename, "w")
        except:
            self.log(LANGUAGE(30034) + ' ' + flename, xbmc.LOGERROR)
            return ''

        self.writeXSPHeader(fle, 'episodes', self.getChannelName(6, show))
        self.writeXSPRule(fle, "tvshow", "is", uni(show))
        self.writeXSPFooter(fle, 0, order)
        fle.close()
        return flename


    def createGenreMixedPlaylist(self, genre):
        flename = xbmcvfs.makeLegalFilename(GEN_CHAN_LOC + 'Mixed_' + genre + '.xsp')

        try:
            fle = FileAccess.open(flename, "w")
        except:
            self.log(LANGUAGE(30034) + ' ' + flename, xbmc.LOGERROR)
            return ''

        epname = os.path.basename(self.createGenrePlaylist('episodes', 3, genre))
        moname = os.path.basename(self.createGenrePlaylist('movies', 4, genre))

        self.writeXSPHeader(fle, 'mixed', self.getChannelName(5, genre))
        self.writeXSPRule(fle, "playlist", "is", epname)
        self.writeXSPRule(fle, "playlist", "is", moname)
        self.writeXSPFooter(fle, 0, "random")
        fle.close()
        return flename


    def createGenrePlaylist(self, pltype, chtype, genre):
        flename = xbmcvfs.makeLegalFilename(GEN_CHAN_LOC + pltype + '_' + genre + '.xsp')

        try:
            fle = FileAccess.open(flename, "w")
        except:
            self.log(LANGUAGE(30034) + ' ' + flename, xbmc.LOGERROR)
            return ''

        self.writeXSPHeader(fle, pltype, self.getChannelName(chtype, genre))
        genre = self.cleanString(genre)
        self.writeXSPRule(fle, "genre", "is", genre)

        if '-' in genre:
            genre = genre.replace("-"," ")
            self.writeXSPRule(fle, "genre", "is", genre)

        self.writeXSPFooter(fle, 0, "random")
        fle.close()
        return flename


    def createStudioPlaylist(self, studio):
        flename = xbmcvfs.makeLegalFilename(GEN_CHAN_LOC + 'Studio_' + studio + '.xsp')

        try:
            fle = FileAccess.open(flename, "w")
        except:
            self.log(LANGUAGE(30034) + ' ' + flename, xbmc.LOGERROR)
            return ''

        self.writeXSPHeader(fle, "movies", self.getChannelName(2, studio))
        studio = self.cleanString(studio)
        self.writeXSPRule(fle, "Studio", "is", studio)
        self.writeXSPFooter(fle, 0, "random")
        fle.close()
        return flename


    def createDirectoryPlaylist(self, setting1):
        self.log("createDirectoryPlaylist " + setting1)
        fileList = []
        filecount = 0

        def listdir_fullpath(dir):
            return [uni(os.path.join(dir, f)) for f in xbmcvfs.listdir(dir)[1]]

        if not self.background:
            self.updateDialog.update(self.updateDialogProgress, '\n'.join([LANGUAGE(30168) % (str(self.settingChannel)), LANGUAGE(30172), LANGUAGE(30174)]))
        
        subdirectories, file_detail = FileAccess.listdir(setting1)
        file_detail = [uni(os.path.join(setting1, f)) for f in file_detail]
        subdirectories = [uni(os.path.join(setting1, dir)) for dir in subdirectories]

        for subdir in subdirectories:
            self.log('directoryChannel - subdirectory "%s"' % str(subdir) , xbmc.LOGINFO)
            subdir2, subfiles = FileAccess.listdir(subdir)
            subfiles = [uni(os.path.join(subdir, f)) for f in subfiles]
            subdir2 = [uni(os.path.join(subdir, dir)) for dir in subdir2]
            if subfiles:
                file_detail.extend(subfiles)
            if subdir2:
                subdirectories.extend(subdir2)

        for f in file_detail:
            if self.threadPause() == False:
                del fileList[:]
                break
            try:
                duration = self.videoParser.getVideoLength(f)
            except:
                duration = 0
                self.log('Failed to load duration for "%s"' % f , xbmc.LOGINFO)
                self.log("directoryChannel except:" + traceback.format_exc(), xbmc.LOGERROR)

            if duration > 0:
                filecount += 1

                if not self.background:
                    if filecount == 1:
                        self.updateDialog.update(self.updateDialogProgress, '\n'.join([LANGUAGE(30168) % (str(self.settingChannel)), LANGUAGE(30172), (LANGUAGE(30175)) % (str(filecount))]))
                    else:
                        self.updateDialog.update(self.updateDialogProgress, '\n'.join([LANGUAGE(30168) % (str(self.settingChannel)), LANGUAGE(30172), (LANGUAGE(30176)) % (str(filecount))]))

                afile = os.path.basename(f)
                afile, ext = os.path.splitext(afile)
                tmpstr = str(duration) + ','
                tmpstr += afile + "//" + "//" + LANGUAGE(30049) + (' "{}"'.format(setting1)) + "\n"
                tmpstr += f #setting1 + os.path.basename(f)
                tmpstr = uni(tmpstr[:2036])
                fileList.append(tmpstr)

        if filecount == 0:
            self.log('Unable to access Videos files in ' + setting1, xbmc.LOGINFO)

        return fileList


    def writeXSPHeader(self, fle, pltype, plname):
        fle.write('<?xml version="1.0" encoding="UTF-8" standalone="yes" ?>\n')
        fle.write('<smartplaylist type="' + pltype + '">\n')
        plname = self.cleanString(plname)
        fle.write('    <name>' + plname + '</name>\n')
        fle.write('    <match>one</match>\n')

    def writeXSPRule(self, fle, field, operator, value):
        fle.write('    <rule field="%s" operator="%s">%s</rule>\n' % (field, operator, value))

    def writeXSPFooter(self, fle, limit, order):
        if self.mediaLimit > 0:
            fle.write('    <limit>' + str(self.mediaLimit) + '</limit>\n')

        fle.write('    <order direction="ascending">' + order + '</order>\n')
        fle.write('</smartplaylist>\n')

    def cleanString(self, string):
        newstr = uni(string)
        newstr = newstr.replace('&', '&amp;')
        newstr = newstr.replace('>', '&gt;')
        newstr = newstr.replace('<', '&lt;')
        return uni(newstr)

    def fillTVInfo(self, sortbycount=False):
        self.log("fillTVInfo")
        json_query = '{"jsonrpc": "2.0", "method": "VideoLibrary.GetTVShows", "params": {"properties":["studio", "genre","runtime"]}, "id": 1}'

        if not self.background:
            self.updateDialog.update(self.updateDialogProgress, '\n'.join([LANGUAGE(30168) % (str(self.settingChannel)), LANGUAGE(30172), LANGUAGE(30177)]))

        json_folder_detail = xbmc.executeJSONRPC(json_query)
        self.log("fillTVInfo: json_folder_detail" + json_folder_detail)
        jsonObject = json.loads(json_folder_detail)

        for f in jsonObject["result"]["tvshows"]:
            try:
                self.log("fillTVInfo. first line of try")
                if self.threadPause() == False:
                    self.log("fillTVInfo. thread Pause is false, returning")
                    del self.networkList[:]
                    del self.showList[:]
                    del self.showGenreList[:]
                    return

                network     = f["studio"]
                genres      = f["genre"]
                duration    = f["runtime"]
                show        = f["label"]

                #networks
                self.log('network: ' + str(network) + ' | genres: ' + str(genres) + ' | duration: ' +
                         str(duration) + ' | show: ' + str(show))
                
                network = network[0] if network else None                                    
                networkinList = next((x for x in self.networkList if x[0] == network), None)

                if networkinList:
                    networkinList[1] += 1                  # increase Count by one self.networkList[item][1] += 1
                elif network:
                    self.networkList.append([network, 1]) # add to list (include the count/ doesnt affect if the sortbycount is on or off)
                else:
                    network = 'NA'

                #tvshows
                self.showList.append([show, network, duration])

                #genres
                for genre in genres:
                    curgenre = genre.replace(" ", "-")
                    genrekinList = next((x for x in self.showGenreList if x[0] == curgenre ),None)

                    if genrekinList != None:
                        genrekinList[1] += 1                      # increase Count by one self.networkList[item][1] += 1
                    else:
                        self.showGenreList.append([curgenre, 1]) # add to list (include the count/ doesnt affect if the sortbycount is on or off)
            except Exception as e:
                self.log("json Internal.except:" + traceback.format_exc())

        if sortbycount:
            self.networkList.sort(key=lambda x: x[1], reverse = True)
            self.showGenreList.sort(key=lambda x: x[1], reverse = True)
        else:
            self.networkList.sort(key=lambda x: x[0].lower())
            self.showGenreList.sort(key=lambda x: x[0].lower())

        if (len(self.showList) == 0) and (len(self.showGenreList) == 0) and (len(self.networkList) == 0):
            self.log(json_folder_detail)

        self.log("found shows " + str(self.showList))
        self.log("found genres " + str(self.showGenreList))
        self.log("fillTVInfo return " + str(self.networkList))

    def fillMovieInfo(self, sortbycount = False):
        self.log("fillMovieInfo")
        studioList = []
        json_query = '{"jsonrpc": "2.0", "method": "VideoLibrary.GetMovies", "params": {"properties":["studio", "genre"]}, "id": 1}'
        json_folder_detail = xbmc.executeJSONRPC(json_query)
        jsonObject = json.loads(json_folder_detail)
        if not self.background:
            self.updateDialog.update(self.updateDialogProgress, '\n'.join([LANGUAGE(30168) % (str(self.settingChannel)), LANGUAGE(30172), LANGUAGE(30178)]))

        for f in jsonObject["result"]["movies"]:
            try:
                if self.threadPause() == False:
                    del self.movieGenreList[:]
                    del self.studioList[:]
                    del studioList[:]
                    break

                studios     = f["studio"]
                genres      = f["genre"]

                #studios
                for studio in studios:
                    curstudio = studio.replace(" ", "-")
                    studiokinList = next((x for x in studioList if x[0] == curstudio ),None)
                    self.log("current studio: " + curstudio)

                    if studiokinList != None:
                        studiokinList[1] += 1                   # increase Count by one
                    else:
                        studioList.append([curstudio, 1]) # add to list (include the count/ doesnt affect if the sortbycount is on or off)

                #genres
                for genre in genres:
                    curgenre = genre.replace(" ", "-")
                    genrekinList = next((x for x in self.movieGenreList if x[0] == curgenre ),None)

                    if genrekinList != None:
                        genrekinList[1]+= 1                      # increase Count by one
                    else:
                        self.movieGenreList.append([curgenre, 1])# add to list (include the count/ doesnt affect if the sortbycount is on or off)
            except Exception as e:
                self.log("json Internal.except:" + traceback.format_exc())

        self.log("studioList size before updates: " + str(len(studioList)))
        #sorting studio
        maxcount = max(studioList, key=lambda item: item[1], default=0)[1]
        studioList = nlargest(int(maxcount / 3), studioList, key=lambda e:e[1])
            #trim to  all the lowest equal count items
        self.log("studioList size after nLargest: " + str(len(studioList)) + " | maxCount value: " + str(maxcount))

        bestmatch = studioList[int(maxcount / 4)][1]
        self.studioList = [x for x in studioList if  x[1] >= bestmatch]

        if sortbycount:
            #studioList.sort(key=lambda x: x[1], reverse=True)              #already sorted by nlargest module
            self.movieGenreList.sort(key=lambda x: x[1], reverse=True)
        else:
            self.studioList.sort(key=lambda x: x[0].lower())
            self.movieGenreList.sort(key=lambda x: x[0].lower())


        if (len(self.movieGenreList) == 0) and (len(self.studioList) == 0):
            self.log(json_folder_detail)

        self.log("found genres " + str(self.movieGenreList))
        self.log("fillMovieInfo return " + str(self.studioList))

        return


    def makeMixedList(self, list1, list2):
        self.log("makeMixedList")
        newlist = []

        newlist = [i1[0] for i1 in list1 for i2 in list2 if i2[0] == i1[0] or i2[0].lower() == i1[0].lower() ]

        self.log("makeMixedList return " + str(newlist))
        return newlist


    def buildFileList(self, dir_name, channel):
        self.log("buildFileList")
        fileList = []
        seasoneplist = []
        filecount = 0
        json_query = '{"jsonrpc": "2.0", "method": "Files.GetDirectory", "params": {"directory": "%s", "media": "video", "properties":["duration","runtime","showtitle","plot","plotoutline","season","episode","year","lastplayed","playcount","resume"]}, "id": 1}' % (self.escapeDirJSON(dir_name))

        if not self.background:
            self.updateDialog.update(self.updateDialogProgress, '\n'.join([LANGUAGE(30168) % (str(self.settingChannel)), LANGUAGE(30172), LANGUAGE(30179)]))

        json_folder_detail = xbmc.executeJSONRPC(json_query)
        jsonResult = json_folder_detail

        jsonObject = json.loads(jsonResult)
        try:
            for f in jsonObject["result"]["files"]:
                if self.threadPause() == False:
                    del fileList[:]
                    break

                if f["file"] != None:
                    if(f["file"].endswith("/") or f["file"].endswith("\\")):   #if file entry is directory make recursive call and append result
                        fileList.extend(self.buildFileList(f["file"], channel))
                    else:
                        try:
                            dur         = f["duration"] if 'duration' in f != None and f["duration"] > 0 else f["runtime"]
                            title       = f["label"]
                            showtitle   = f["showtitle"]
                            plot        = f["plot"]
                            plotoutline = f["plotoutline"]
                            #values needed to reset watched status should be captured whether or not the setting is enabled, in case user changes setting later
                            playcount   = f["playcount"]
                            lastplayed  = f["lastplayed"]
                            resumePosition = f["resume"]["position"]
                            id = f["id"]
                            #tv show info
                            season = f["season"]
                            episode = f["episode"]
                            #movie info
                            year = f["year"]

                            if dur == 0:
                                try:
                                    dur = next(x for x in self.showList if x[0] == showtitle )[2]
                                    # dur = int(dur * .80 )
                                    self.log("Duration value from TVShow profile")
                                except Exception as e:
                                    try:
                                        self.log(str(e))
                                        self.log( json.dumps(f))
                                        dur = self.videoParser.getVideoLength(uni(f["file"]).replace("\\\\", "\\"))
                                        self.log("Duration value from Video file",xbmc.LOGINFO)
                                    except Exception as ie:
                                        self.log(str(ie))
                                        continue

                            if dur > 0:
                                filecount += 1
                                #udpate status dialog
                                if not self.background:
                                    if filecount == 1:
                                        self.updateDialog.update(self.updateDialogProgress, '\n'.join([LANGUAGE(30168) % (str(self.settingChannel)), LANGUAGE(30172), ''.join(LANGUAGE(30175)) % (str(filecount))]))
                                    else:
                                        self.updateDialog.update(self.updateDialogProgress, '\n'.join([LANGUAGE(30168) % (str(self.settingChannel)), LANGUAGE(30172), ''.join(LANGUAGE(30176)) % (str(filecount))]))

                                theplot = plotoutline if len(plotoutline) > 0 else ( plot if len(plot) > 0 else LANGUAGE(30023))
                                theplot = theplot.replace('//','')

                                tmpstr = str(dur) + ','                         #todo: refactor using playlistitem class

                                # This is a TV show
                                if showtitle != None and len(showtitle) > 0:
                                    sxexx = (' ({})'.format(str(season) + 'x' + str(episode)))

                                    if "." in title:
                                        param, title = title.split(". ", 1)
                                    swtitle = ('"{}"'.format(title))

                                    if episode != None and episode > 0 and self.YearEpInfo == 'false':
                                        swtitle = swtitle + sxexx
                                    tmpstr += showtitle + "//" + swtitle + "//" + theplot
                                else:
                                    # This is a movie
                                    if showtitle == None or len(showtitle) == 0:
                                        tmpstr += title

                                        if year != None and self.YearEpInfo == 'false':
                                            tmpstr += "//" + str(year) + "//" + theplot
                                        else:
                                            tmpstr += "//" + "//" + theplot

                                #tmpstr = tmpstr[:2036]
                                tmpstr = uni(tmpstr[:1990])
                                #^^^stealing some characters from plot for reset values
                                #then adding those values
                                tmpstr += "//" + str(playcount)
                                tmpstr += "//" + str(resumePosition)
                                tmpstr += "//" + str(lastplayed)
                                tmpstr += "//" + str(id)

                                tmpstr = tmpstr.replace("\n", " ").replace("\r", " ").replace('\"', '"')
                                tmpstr = tmpstr + '\n' + f["file"].replace("\\\\", "\\")

                                if self.channels[channel].mode & MODE_ORDERAIRDATE > 0:
                                    seasoneplist.append([str(season), str(episode), tmpstr])
                                else:
                                    fileList.append(tmpstr)
                                #print(tmpstr)

                        except Exception as e:
                            self.log("json Internal.except:" + traceback.format_exc())

                else:
                    continue
        except Exception as e:
            self.log("json Object Exception:" + traceback.format_exc())

        if self.channels[channel].mode & MODE_ORDERAIRDATE > 0:
            seasoneplist.sort(key=lambda seep: seep[1])
            seasoneplist.sort(key=lambda seep: seep[0])

            for seepitem in seasoneplist:
                fileList.append(seepitem[2])

        if filecount == 0:
            self.log(json_folder_detail)

        self.log("buildFileList return")
        return fileList


    def buildMixedFileList(self, dom1, channel):
        fileList = []
        self.log('buildMixedFileList')

        try:
            rules = dom1.getElementsByTagName('rule')
            order = dom1.getElementsByTagName('order')
        except:
            return fileList

        for rule in rules:
            rulename = rule.childNodes[0].nodeValue

            if FileAccess.exists(xbmcvfs.translatePath('special://profile/playlists/video/') + rulename):
                FileAccess.copy(xbmcvfs.translatePath('special://profile/playlists/video/') + rulename, MADE_CHAN_LOC + rulename)
                fileList.extend(self.buildFileList(MADE_CHAN_LOC + rulename, channel))
            else:
                fileList.extend(self.buildFileList(GEN_CHAN_LOC + rulename, channel))

        self.log("buildMixedFileList returning")
        return fileList

    # Run rules for a channel
    def runActions(self, action, channelNumber, parameter):
        self.log("runActions " + str(action) + " on channel " + str(channelNumber))
        if not channelNumber in self.channels:
            return

        self.runningActionChannel = channelNumber
        index = 0

        for rule in self.channels[channelNumber].ruleList:
            if rule.actions & action > 0:
                self.runningActionId = index

                if not self.background:
                    self.updateDialog.update(self.updateDialogProgress, '\n'.join([LANGUAGE(30168) % (str(self.settingChannel)), ''.join(LANGUAGE(30180)) % (str(index + 1))]))

                parameter = rule.runAction(action, self, parameter)

            index += 1

        self.runningActionChannel = 0
        self.runningActionId = 0
        return parameter

    def threadPause(self):
        if threading.active_count() > 1:
            while self.threadPaused == True and self.myOverlay.isExiting == False:
                time.sleep(self.sleepTime)

            # This will fail when using config.py
            try:
                if self.myOverlay.isExiting == True:
                    self.log("IsExiting")
                    return False
            except:
                pass

        return True

    def escapeDirJSON(self, dir_name):
        mydir = uni(dir_name)

        if mydir.find(":"):
            mydir = mydir.replace("\\", "\\\\")

        return mydir

    def getSmartPlaylistType(self, dom):
        self.log('getSmartPlaylistType')

        try:
            pltype = dom.getElementsByTagName('smartplaylist')
            return pltype[0].attributes['type'].value
        except:
            self.log("Unable to get the playlist type.", xbmc.LOGERROR)
            return ''
