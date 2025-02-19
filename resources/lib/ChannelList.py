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
from FileAccess import FileAccess
from VideoParser import VideoParser
from Channel import Channel, ChannelType
from Globals import *
from Playlist import PlaylistItem, SmartPlaylist
import xbmc
import xbmcgui
import xbmcvfs
import importlib
import os
import traceback
import time
import threading
import sys
import random
import json
from heapq import nlargest
from Rules import RulesList
from Settings import ChannelSettings
from log import Log

importlib.reload(sys)


class ChannelList(Log):
    def __init__(self):
        self.networkList = []
        self.studioList = []
        self.mixedGenreList = []
        self.showGenreList = []
        self.movieGenreList = []
        self.musicGenreList = []
        self.showList = []
        self.channels: dict[int, Channel] = {}
        self.videoParser = VideoParser()
        self.sleepTime = 0
        self.threadPaused = False
        self.runningActionChannel = 0
        self.runningActionId = 0
        self.enteredChannelCount = 0
        self.background = True
        random.seed()

    def readConfig(self):
        self.channelResetSetting = ADDON.getSettingInt("ChannelResetSetting")
        self.log('Channel Reset Setting is ' + str(self.channelResetSetting))
        self.forceReset = ADDON.getSettingBool('ForceChannelReset')
        self.log('Force Reset is ' + str(self.forceReset))
        self.updateDialog = xbmcgui.DialogProgress()
        self.startMode = ADDON.getSettingInt("StartMode")
        self.log('Start Mode is ' + str(self.startMode))
        self.backgroundUpdating = ADDON.getSettingInt("ThreadMode")
        self.mediaLimit = MEDIA_LIMIT[ADDON.getSettingInt("MediaLimit")]
        self.hideYearEpInfo = ADDON.getSettingBool('HideYearEpInfo')
        self.maxChannels = ADDON_SETTINGS.MaxChannel()
        self.enteredChannelCount = ADDON_SETTINGS.ChannelCount()

        if self.forceReset:
            for ch in ADDON_SETTINGS.Channels.values():
                ch.changed = True
            ADDON.setSettingBool('ForceChannelReset', False)
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
            self.updateDialog.update(self.updateDialogProgress, '\n'.join(
                [LANGUAGE(30166) % (str(i)), LANGUAGE(30165)]))

            # If the user pressed cancel, stop everything and exit
            if self.updateDialog.iscanceled():
                self.log('Update channels cancelled')
                self.updateDialog.close()
                return None

            self.setupChannel(i, False, makenewlists, False)
            foundvalid |= self.channels[i].isValid

        if makenewlists is True:
            ADDON.setSettingBool('ForceChannelReset', False)

        if foundvalid is False and makenewlists is False:
            for i in range(1, self.maxChannels + 1):
                self.updateDialogProgress = i * 100 // self.enteredChannelCount
                self.updateDialog.update(self.updateDialogProgress, '\n'.join(
                    [LANGUAGE(30168) % i, LANGUAGE(30165)]))
                self.setupChannel(i, False, True, False)

                if self.channels[i].isValid:
                    foundvalid = True
                    break

        self.updateDialog.update(100, LANGUAGE(30170))
        self.updateDialog.close()

        return self.channels

    def setupChannel(self, channelNumber: int, background=False, makenewlist=False, append=False):
        self.log('setupChannel ' + str(channelNumber))
        returnval = False
        createlist = makenewlist
        chSettings = ChannelSettings()
        needsreset = False
        self.background = background
        self.settingChannel = channelNumber
        channelBaseName = 'Channel_' + str(channelNumber)
        channelFilepath = CHANNELS_LOC + channelBaseName + '.m3u'

        try:
            chSettings = ADDON_SETTINGS.getChannelSettings(channelNumber)
        except:
            pass

        curChannel: Channel = self.channels.get(channelNumber, Channel())
        if not channelNumber in self.channels:
            self.channels[channelNumber] = curChannel
            curChannel.settings = chSettings

        if chSettings.type == ChannelType.UNKNOWN:
            curChannel.isValid = False
            return False

        curChannel.isSetup = True
        curChannel.ruleList = RulesList.loadRules(curChannel.settings.rules)
        self.runActions(RULES_ACTION_START, channelNumber, curChannel)

        try:
            needsreset = chSettings.changed

            if needsreset:
                curChannel.isSetup = False
        except:
            pass

        # If possible, use an existing playlist
        # Don't do this if we're appending an existing channel
        # Don't load if we need to reset anyway
        if FileAccess.exists(channelFilepath) and append == False and needsreset == False:
            try:
                curChannel.totalTimePlayed = chSettings.time
                createlist = True

                if not self.background:
                    self.updateDialog.update(self.updateDialogProgress, '\n'.join(
                        [LANGUAGE(30166) % (str(channelNumber)), LANGUAGE(30171)]))

                if curChannel.setPlaylist(channelFilepath):
                    curChannel.isValid = True
                    curChannel.fileName = channelFilepath
                    returnval = True

                    # If this channel has been watched for longer than it lasts, reset the channel
                    if self.channelResetSetting == 0 and curChannel.totalTimePlayed < curChannel.getTotalDuration():
                        createlist = False

                    if self.channelResetSetting > 0 and self.channelResetSetting < 4:
                        timedif = time.time() - self.lastResetTime  # timedif  in seconds:float

                        if self.channelResetSetting == 1 and timedif < (60 * 60 * 24):  # 1 day
                            createlist = False

                        if self.channelResetSetting == 2 and timedif < (60 * 60 * 24 * 7):  # 1 week
                            createlist = False

                        if self.channelResetSetting == 3 and timedif < (60 * 60 * 24 * 30):  # 1~ month
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
                    os.remove(channelFilepath)
                except:
                    pass

                append = False

                if createlist:
                    ADDON_SETTINGS.setSetting('LastResetTime', int(time.time()))

        if append is False:
            if chSettings.type == ChannelType.TVSHOW and chSettings._2 == str(MODE_ORDERAIRDATE):
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
                self.updateDialog.update(self.updateDialogProgress, '\n'.join(
                    [LANGUAGE(30168) % channelNumber, LANGUAGE(30172)]))

            if self.makeChannelList(channelNumber, chSettings.type, chSettings._1, chSettings._2, append):
                if curChannel.setPlaylist(channelFilepath):
                    returnval = True
                    curChannel.fileName = channelFilepath
                    curChannel.isValid = True
                    log("Channel %i set to valid" % channelNumber, xbmc.LOGINFO)

                    # Don't reset variables on an appending channel
                    if append is False:
                        curChannel.totalTimePlayed = 0
                        chSettings.time = 0

                        if needsreset:
                            chSettings.changed = False
                            curChannel.isSetup = True
                        ADDON_SETTINGS.setChannelSettings(channelNumber, chSettings)
                else:
                    log("failed to setPlaylist for Channel %i" % channelNumber, xbmc.LOGINFO)

        self.runActions(RULES_ACTION_BEFORE_CLEAR, channelNumber, curChannel)

        # Don't clear history when appending channels
        if not self.background and not append and self.myOverlay.isMaster:
            self.updateDialogProgress = (channelNumber) * 100 // self.enteredChannelCount
            self.updateDialog.update(self.updateDialogProgress, '\n'.join(
                [LANGUAGE(30166) % (str(channelNumber)), LANGUAGE(30173)]))
            self.clearPlaylistHistory(channelNumber)

        if not append:
            self.runActions(RULES_ACTION_BEFORE_TIME, channelNumber, curChannel)

            if curChannel.mode & MODE_ALWAYSPAUSE > 0:
                curChannel.isPaused = True

            if curChannel.mode & MODE_RANDOM > 0:
                curChannel.showTimeOffset = random.randint(0, curChannel.getTotalDuration())

            if curChannel.mode & MODE_REALTIME > 0:
                timedif = int(self.myOverlay.timeStarted) - self.lastExitTime  # time diff in seconds
                curChannel.totalTimePlayed += timedif  # secs

            if curChannel.mode & MODE_RESUME > 0:
                curChannel.showTimeOffset = curChannel.totalTimePlayed
                curChannel.totalTimePlayed = 0  # secs

            while curChannel.showTimeOffset > curChannel.getCurrentDuration():
                curChannel.showTimeOffset -= curChannel.getCurrentDuration()
                curChannel.addShowPosition(1)

        curChannel.name = self.getChannelName(chSettings.type, chSettings._1)

        if ((createlist or needsreset) and makenewlist) and returnval:
            self.runActions(RULES_ACTION_FINAL_MADE, channelNumber, curChannel)
        else:
            self.runActions(RULES_ACTION_FINAL_LOADED, channelNumber, curChannel)

        return returnval

        """ Trim playlist items if total timed played is greater than 2 days
        remove the 1st entries before timedPlayed - 12hrs.
        Keep last unplayed entries and the last 12hrs played """

    def clearPlaylistHistory(self, channelNumber):
        self.log("clearPlaylistHistory")
        channelBaseName = 'Channel_' + str(channelNumber)
        currentChannel = self.channels[channelNumber]
        if currentChannel.isValid is False:
            self.log("channel not valid, ignoring")
            return

        # if we actually need to clear anything
        timeLimit = (60 * 60 * 24 * 2)
        cutofftime = currentChannel.totalTimePlayed - (60 * 60 * 12)
        if currentChannel.totalTimePlayed > timeLimit and currentChannel.Playlist.totalDuration > cutofftime:  # secs ~ 2days

            tottime = 0
            myGenerator = ((item[0], tottime + item[1].duration)
                           for item in enumerate(currentChannel.Playlist.itemlist))
            while tottime <= cutofftime:
                cutoffindex, tottime = next(myGenerator)

            currentChannel.Playlist.itemlist = currentChannel.Playlist.itemlist[cutoffindex:]
            currentChannel.Playlist.save(currentChannel.Playlist.filename)

            if tottime:
                if currentChannel.setPlaylist(currentChannel.Playlist.filename) is False:
                    currentChannel.isValid = False
                else:
                    currentChannel.totalTimePlayed -= tottime
                    # Write this now so anything sharing the playlists will get the proper info
                    ADDON_SETTINGS.Channels[channelNumber].time = currentChannel.totalTimePlayed
                    self.log('Removed first %d items from channel %s playlist' %
                             (cutoffindex, currentChannel.name))

    @staticmethod
    def getChannelName(chtype, setting1) -> str:
        log('ChannelList: ' + 'getChannelName ' + str(chtype))

        if len(setting1) == 0:
            return ''

        if chtype == ChannelType.PLAYLIST:
            return SmartPlaylist.getSmartPlaylistName(setting1)
        elif chtype in [ChannelType.NETWORK, ChannelType.STUDIO, ChannelType.MIX_GENRE, ChannelType.TVSHOW]:
            return setting1
        elif chtype == ChannelType.TVSHOW_GENRE:
            return setting1 + " TV"
        elif chtype == ChannelType.MOVIE_GENRE:
            return setting1 + " Movies"
        elif chtype == ChannelType.MUSIC_GENRE:
            return setting1 + " Music"
        elif chtype == ChannelType.DIRECTORY:
            if setting1[-1] == '/' or setting1[-1] == '\\':
                return os.path.split(setting1[:-1])[1]
            else:
                return os.path.basename(setting1)
        return ''

    # Based on a smart playlist, create a normal playlist that can actually be used by us
    def makeChannelList(self, channelNumber, chtype, setting1, setting2, append=False) -> bool:
        self.log('makeChannelList ' + str(channelNumber))
        israndom = True
        fileList: list[PlaylistItem] = []

        if self.channels[channelNumber].isSkipped == True:
            self.log("channel set to skip, ignoring")
            return False

        if chtype == ChannelType.DIRECTORY:
            fileList = self.createDirectoryPlaylist(setting1)
            israndom = True
        else:
            # load or create smartplaylist
            if chtype == ChannelType.PLAYLIST:
                smartPlaylistPath = MADE_CHAN_LOC + os.path.basename(setting1)
                if FileAccess.copy(setting1, smartPlaylistPath) == False:
                    if FileAccess.exists(smartPlaylistPath) == False:
                        self.log("Unable to copy or find playlist " + setting1)
                        return False
                try:
                    smartPlaylist = SmartPlaylist(smartPlaylistPath)
                    if not smartPlaylist.validatePlaylistFileRule(setting1, smartPlaylistPath):
                        return False
                except:
                    self.log("makeChannelList Unable to validate the SmartPlaylist " +
                             smartPlaylist, xbmc.LOGERROR)
                    return False
            else:  # note: always overwrites
                # todo check for existing file else make spl
                smartPlaylist = self.makeTypePlaylist(chtype, setting1, setting2)

            if not smartPlaylist:
                self.log('Unable to locate the SmartPlaylist for channel ' + str(channelNumber), xbmc.LOGERROR)
                return False

            if smartPlaylist.type == 'mixed':
                fileList = self.buildMixedFileList(smartPlaylist, channelNumber)
            else:
                fileList = self.buildFileList(smartPlaylist.filePath, channelNumber)
            # load smartPlaylist settings
            israndom = smartPlaylist.order.lower() == 'random'

        if israndom:  # todo: review/unnessary, entries are built random if applies
            random.shuffle(fileList)

        fileList = self.runActions(RULES_ACTION_LIST, channelNumber, fileList)
        self.channels[channelNumber].isRandom = israndom
        if append:
            self.channels[channelNumber].Playlist.itemlist.extend(fileList)
        else:
            self.channels[channelNumber].Playlist.itemlist = fileList
        # trim if needed
        self.channels[channelNumber].Playlist.itemlist = self.channels[channelNumber].Playlist.itemlist[:16384]

        # store to file
        channelplaylistPath = CHANNELS_LOC + "channel_" + str(channelNumber) + ".m3u"
        self.channels[channelNumber].Playlist.save(channelplaylistPath)

        self.log('makeChannelList return')
        return True

    def makeTypePlaylist(self, chtype, setting1, setting2):
        try:
            if (not self.networkList or not self.showGenreList or not self.showList) and chtype in [ChannelType.NETWORK, ChannelType.TVSHOW_GENRE, ChannelType.MIX_GENRE, ChannelType.TVSHOW]:
                self.log('%s: About to fill the tv info because the network/showlist/genre list size is 0' % chtype)
                self.fillTVInfo()
            if (not self.studioList or not self.movieGenreList) and chtype in [ChannelType.STUDIO, ChannelType.MOVIE_GENRE, ChannelType.MIX_GENRE]:
                self.log('%s: About to fill the movies info because the studio/genre list size is 0' % chtype)
                self.fillMovieInfo()
            if not self.musicGenreList and chtype in [ChannelType.MUSIC_GENRE]:
                self.log('%s: About to fill the music info because the genre list size is 0' % chtype)
                self.fillMusicInfo()

            channelName = self.getChannelName(chtype, setting1)
            if chtype == ChannelType.NETWORK:
                return SmartPlaylist.createNetworkPlaylist(setting1, channelName)
            elif chtype == ChannelType.STUDIO:
                return SmartPlaylist.createStudioPlaylist(setting1, channelName)
            elif chtype == ChannelType.TVSHOW_GENRE:
                return SmartPlaylist.createGenrePlaylist('episodes', setting1, channelName)
            elif chtype == ChannelType.MOVIE_GENRE:
                return SmartPlaylist.createGenrePlaylist('movies', setting1, channelName)
            elif chtype == ChannelType.MIX_GENRE:
                if not self.mixedGenreList:
                    self.mixedGenreList = self.makeMixedList(
                        self.showGenreList, self.movieGenreList, key=lambda x: x[0].lower())
                return SmartPlaylist.createGenreMixedPlaylist(setting1, channelName)
            elif chtype == ChannelType.MUSIC_GENRE:
                return SmartPlaylist.createGenrePlaylist('songs', setting1, channelName)
            elif chtype == ChannelType.TVSHOW:
                return SmartPlaylist.createShowPlaylist(setting1, setting2, channelName)

            self.log('makeTypePlaylists invalid channel type: ' + chtype)

        except Exception as ex:
            self.log("Failed to create SmartPlaylist - %s: %s" % (channelName or '', str(ex)))
        return None

    def createDirectoryPlaylist(self, setting1):
        self.log("createDirectoryPlaylist " + setting1)
        fileList: list[PlaylistItem] = []

        if not self.background:
            self.updateDialog.update(self.updateDialogProgress, '\n'.join(
                [LANGUAGE(30168) % self.settingChannel, LANGUAGE(30172), LANGUAGE(30174)]))

        file_detail = []
        subdirectories = [setting1]
        myGen = ((dir, *FileAccess.listdir(dir)) for dir in subdirectories if dir[0] != '.')
        for cd, dirs, files in myGen:
            file_detail.extend([os.path.join(cd, fs) for fs in files])
            subdirectories.extend([os.path.join(cd, dir) for dir in dirs])

        for file in file_detail:
            if self.threadPause() == False:
                del fileList[:]
                break
            try:
                duration = self.videoParser.getVideoLength(file)
            except:
                duration = 0
                self.log('Failed to load duration for "%s"' % file, xbmc.LOGINFO)
                self.log("directoryChannel except:" + traceback.format_exc(), xbmc.LOGERROR)

            if duration:
                if not self.background:
                    lastMessage = LANGUAGE(30176) % (len(fileList) + 1) if fileList else LANGUAGE(30175) % 1
                    self.updateDialog.update(self.updateDialogProgress, '\n'.join(
                        [LANGUAGE(30168) % self.settingChannel, LANGUAGE(30172), lastMessage]))

                afile, _ = os.path.splitext(os.path.basename(file))
                description = LANGUAGE(30049) + (' "{}"'.format(setting1)).replace('//', '')
                plItem = PlaylistItem(duration, afile, description, 0, file)
                fileList.append(plItem)

        if not fileList:
            self.log('Unable to access Videos files in ' + setting1, xbmc.LOGINFO)

        # todo: add medialimit and random logic/otherwise will alway used the 1st entries
        return fileList

    def fillTVInfo(self, sortbycount=False):
        self.log("fillTVInfo")  # todo : refactor VideoLibrary.GetGenres
        json_query = '{"jsonrpc": "2.0", "method": "VideoLibrary.GetTVShows", "params": {"properties":["studio", "genre","runtime"]}, "id": 1}'

        if not self.background:
            self.updateDialog.update(self.updateDialogProgress, '\n'.join(
                [LANGUAGE(30168) % self.settingChannel, LANGUAGE(30172), LANGUAGE(30177)]))

        json_folder_detail = xbmc.executeJSONRPC(json_query)
        jsonObject = json.loads(json_folder_detail)

        for f in jsonObject["result"]["tvshows"]:
            try:
                if self.threadPause() == False:
                    self.log("fillTVInfo. thread Pause is false, returning")
                    del self.networkList[:]
                    del self.showList[:]
                    del self.showGenreList[:]
                    return

                network = f["studio"]
                genres = f["genre"]
                duration = f["runtime"]
                show = f["label"]

                # networks
                self.log('network: ' + str(network) + ' | genres: ' + str(genres) + ' | duration: ' +
                         str(duration) + ' | show: ' + str(show))

                network = network[0] if network else None
                networkinList = next((x for x in self.networkList if x[0] == network), None)

                if networkinList:
                    # increase Count by one self.networkList[item][1] += 1
                    networkinList[1] += 1
                elif network:
                    # add to list (include the count/ doesnt affect if the sortbycount is on or off)
                    self.networkList.append([network, 1])
                else:
                    network = 'NA'

                # tvshows
                self.showList.append([show, network, duration])

                # genres
                for genre in genres:
                    curgenre = genre.replace(" ", "-")
                    genrekinList = next((x for x in self.showGenreList if x[0] == curgenre), None)

                    if genrekinList != None:
                        # increase Count by one self.networkList[item][1] += 1
                        genrekinList[1] += 1
                    else:
                        # add to list (include the count/ doesnt affect if the sortbycount is on or off)
                        self.showGenreList.append([curgenre, 1])
            except Exception as e:
                self.log("json Internal.except:" + traceback.format_exc())

        if sortbycount:
            self.networkList.sort(key=lambda x: x[1], reverse=True)
            self.showGenreList.sort(key=lambda x: x[1], reverse=True)
        else:
            self.networkList.sort(key=lambda x: x[0].lower())
            self.showGenreList.sort(key=lambda x: x[0].lower())

        if (len(self.showList) == 0) and (len(self.showGenreList) == 0) and (len(self.networkList) == 0):
            self.log(json_folder_detail)

    def fillMovieInfo(self, sortbycount=False):
        self.log("fillMovieInfo")
        studioList = []
        # todo : refactor VideoLibrary.GetGenres
        json_query = '{"jsonrpc": "2.0", "method": "VideoLibrary.GetMovies", "params": {"properties":["studio", "genre"]}, "id": 1}'
        json_folder_detail = xbmc.executeJSONRPC(json_query)
        jsonObject = json.loads(json_folder_detail)
        if not self.background:
            self.updateDialog.update(self.updateDialogProgress, '\n'.join(
                [LANGUAGE(30168) % self.settingChannel, LANGUAGE(30172), LANGUAGE(30178)]))

        for f in jsonObject["result"]["movies"]:
            try:
                if self.threadPause() == False:
                    del self.movieGenreList[:]
                    del self.studioList[:]
                    del studioList[:]
                    break

                studios = f["studio"]
                genres = f["genre"]

                # studios
                for studio in studios:
                    curstudio = studio.replace(" ", "-")
                    studiokinList = next((x for x in studioList if x[0] == curstudio), None)
                    #self.log("current studio: " + curstudio)

                    if studiokinList != None:
                        studiokinList[1] += 1                   # increase Count by one
                    else:
                        # add to list (include the count/ doesnt affect if the sortbycount is on or off)
                        studioList.append([curstudio, 1])

                # genres
                for genre in genres:
                    curgenre = genre.replace(" ", "-")
                    genrekinList = next((x for x in self.movieGenreList if x[0] == curgenre), None)

                    if genrekinList != None:
                        genrekinList[1] += 1                      # increase Count by one
                    else:
                        # add to list (include the count/ doesnt affect if the sortbycount is on or off)
                        self.movieGenreList.append([curgenre, 1])
            except Exception as e:
                self.log("json Internal.except:" + traceback.format_exc())

        self.log("studioList size before updates: " + str(len(studioList)))
        # sorting studio
        if studioList:
            maxcount = max(studioList, key=lambda item: item[1], default=['None', 0])[1]
            studioList = nlargest(int(maxcount / 3), studioList, key=lambda e: e[1])
            # trim to  all the lowest equal count items
            #self.log("studioList size after nLargest: " + str(len(studioList)) + " | maxCount value: " + str(maxcount))

            bestmatch = studioList[int(maxcount / 4)][1]
            self.studioList = [x for x in studioList if x[1] >= bestmatch]

        if sortbycount:
            # studioList.sort(key=lambda x: x[1], reverse=True)              #already sorted by nlargest module
            self.movieGenreList.sort(key=lambda x: x[1], reverse=True)
        else:
            self.studioList.sort(key=lambda x: x[0].lower())
            self.movieGenreList.sort(key=lambda x: x[0].lower())

        if (len(self.movieGenreList) == 0) and (len(self.studioList) == 0):
            self.log(json_folder_detail)

        #self.log("found genres " + str(self.movieGenreList))
        #self.log("fillMovieInfo return " + str(self.studioList))

        return

    def fillMusicInfo(self, sortbycount=False):
        self.log("fillMusicInfo")
        # get genres
        json_query = '{"jsonrpc": "2.0", "method": "AudioLibrary.GetGenres","id": 1}'
        json_folder_detail = xbmc.executeJSONRPC(json_query)
        jsonObject = json.loads(json_folder_detail)
        genres = [[igenre['label'], 1] for igenre in jsonObject["result"]["genres"]]

        # clean up genre list
        lBadEntries = ['Unknown', 'Other']
        genres = [ig for ig in genres if not any((True for ibg in lBadEntries if ibg in ig))]

        # get count from albums
        json_query = '{"jsonrpc": "2.0", "method": "AudioLibrary.GetAlbums","params": {"properties":["genre"]},"id": 1}'
        json_folder_detail = xbmc.executeJSONRPC(json_query)
        jsonObject = json.loads(json_folder_detail)

        for genreEntry in genres:
            genreEntry[1] = sum([True for al in jsonObject["result"]
                                ["albums"] if genreEntry[0] in al['genre']])

        if not self.background:
            self.updateDialog.update(self.updateDialogProgress, '\n'.join(
                [LANGUAGE(30168) % self.settingChannel, LANGUAGE(30202), LANGUAGE(30203)]))

        self.musicGenreList = genres
        self.log("musicGenreList size: " + str(len(genres)))
        self.log("musicGenreList genres: " + str(genres))

    def makeMixedList(self, list1, list2, keepCounts: bool = False, key=None, reverse: bool = False, limit: int = -1):
        self.log("makeMixedList")
        newlist = [[*i1, *i2[1:]] for i1 in list1 for i2 in list2 if i2[0]
                   == i1[0] or i2[0].lower() == i1[0].lower()]  # refactor unions
        if key:
            newlist.sort(key=key, reverse=reverse)
        if not keepCounts:
            newlist = [i[0] for i in newlist]
        if limit > 0:
            newlist = newlist[:limit]
        self.log("makeMixedList return " + str(newlist))
        return newlist

    def buildFileList(self, dir_name, channel):
        self.log("buildFileList - %s" % dir_name)
        fileList: list[PlaylistItem] = []
        seasoneplist = []
        filecount = 0
        json_query = '{"jsonrpc": "2.0", "method": "Files.GetDirectory", "params": {"directory": "%s", "media": "video", "properties":["duration","runtime","showtitle","plot","plotoutline","season","episode","year","albumartist","album","track","lastplayed","playcount","resume"]}, "id": 1}' % (
            self.escapeDirJSON(dir_name))
        #self.log("buildFileList - jQuery : '%s'" % json_query)

        if not self.background:
            self.updateDialog.update(self.updateDialogProgress, '\n'.join(
                [LANGUAGE(30168) % self.settingChannel, LANGUAGE(30172), LANGUAGE(30179)]))

        json_folder_detail = xbmc.executeJSONRPC(json_query)
        jsonResult = json_folder_detail

        jsonObject = json.loads(jsonResult)
        try:
            for fileInfo in jsonObject["result"]["files"]:
                if self.threadPause() == False:
                    del fileList[:]
                    break

                if fileInfo["file"]:
                    # if file entry is directory make recursive call and append result
                    if (fileInfo["file"].endswith("/") or fileInfo["file"].endswith("\\")):
                        fileList.extend(self.buildFileList(fileInfo["file"], channel))
                    else:
                        fileInfo = self.runActions(RULES_ACTION_JSON, channel, fileInfo)
                        if not fileInfo:
                            continue

                        try:
                            dur = fileInfo["duration"] if 'duration' in fileInfo != None and fileInfo["duration"] > 0 else fileInfo["runtime"]
                            title = fileInfo["label"]
                            year = fileInfo["year"]
                            mediaType = fileInfo['type']  # ['episode', 'movie','song']
                            filename = fileInfo["file"].replace("\\\\", "\\")
                            id = fileInfo["id"]
                            # values needed to reset watched status should be captured whether or not the setting is enabled, in case user changes setting later
                            playcount = fileInfo["playcount"]
                            lastplayed = fileInfo["lastplayed"]
                            resumePosition = fileInfo["resume"]["position"] if 'resume' in fileInfo else 0

                            description = ''
                            secondTitle = ''
                            # tv show/movies info
                            if mediaType in ['episode', 'movie']:
                                showtitle = fileInfo["showtitle"]
                                plot = fileInfo["plot"]
                                plotoutline = fileInfo["plotoutline"]
                                season = fileInfo["season"]
                                episode = fileInfo["episode"]
                                description = plotoutline or plot or LANGUAGE(30023)
                                description = description.replace('//', '').replace("\n", "")

                                if dur == 0:  # use duration value from tvshow profile
                                    try:
                                        if mediaType == 'episode':
                                            dur = next(x for x in self.showList if x[0] == showtitle)[
                                                2]  # todo: refactor? showlist logic
                                            # dur = int(dur * .80 )                                            #reduce to account for commercial gaps
                                            self.log("Duration value from TVShow profile")
                                        else:
                                            dur = self.videoParser.getVideoLength(filename)
                                            self.log("Duration value from Video file", xbmc.LOGINFO)
                                    except Exception as e:
                                        self.log(str(e))
                                        continue

                                swtitle = None
                                if mediaType == 'episode':
                                    # todo: review removing () on shows with (year) on title
                                    sxexx = '' if self.hideYearEpInfo else " (%dx%02d)" % (season, episode)
                                    swtitle = '"%s"%s' % (title.split(". ", 1)[-1], sxexx)
                                    title = showtitle
                                secondTitle = swtitle or str(year) or ''

                            elif mediaType == 'song':
                                album = fileInfo['album']
                                artist = fileInfo['albumartist'][0]
                                track = fileInfo['track']
                                description = "%s - %s - %02d.%s" % (artist, album, track, title)
                                secondTitle = artist
                            else:
                                self.log("Unexpected mediaType -" + mediaType)

                            if dur:
                                # udpate status dialog           #todo: add music wording logic
                                if not self.background:
                                    lastMessage = LANGUAGE(30176) % (
                                        len(fileList) + 1) if fileList else LANGUAGE(30175) % 1
                                    self.updateDialog.update(self.updateDialogProgress, '\n'.join(
                                        [LANGUAGE(30168) % self.settingChannel, LANGUAGE(30172), lastMessage]))

                                plItem = PlaylistItem(dur, title, description, id, filename, secondTitle,
                                                      playcount, resumePosition, lastplayed)
                                if mediaType == 'episode' and self.channels[channel].mode & MODE_ORDERAIRDATE:
                                    plItem.episode = episode
                                    plItem.season = season
                                    seasoneplist.append([str(season), str(episode), plItem])
                                else:
                                    fileList.append(plItem)

                        except Exception as e:
                            self.log("json Internal.except:" + traceback.format_exc())
        except Exception as e:
            self.log("json Object Exception:" + traceback.format_exc())

        """ if self.channels[channel].mode & MODE_ORDERAIRDATE > 0:
            seasoneplist.sort(key=lambda seep: seep[1])
            seasoneplist.sort(key=lambda seep: seep[0])     #review/ might not be neccessary

            for seepitem in seasoneplist:
                fileList.append(seepitem[2]) """

        seasoneplist.sort()  # this should be default logic/needed?
        for seepitem in seasoneplist:
            fileList.append(seepitem[2])

        self.log("buildFileList return")
        return fileList

    def buildMixedFileList(self, smartPlaylist: SmartPlaylist, channel):
        '''creates a mixed(movies and TV) filelist by executing each smartplaylist type idependently and
        combining the result. (Workaround for Kodi SmartPlayList, it does not implement a mixed mode)'''
        fileList = []
        self.log('buildMixedFileList')

        for rule in smartPlaylist.rules:
            rulename = rule['value']

            if FileAccess.exists(xbmcvfs.translatePath('special://profile/playlists/video/') + rulename):
                FileAccess.copy(xbmcvfs.translatePath('special://profile/playlists/video/') +
                                rulename, MADE_CHAN_LOC + rulename)  # why copy to addon local dirs
                fileList.extend(self.buildFileList(MADE_CHAN_LOC + rulename, channel))
            else:
                # whats the diff between this path and aboved one
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
                    self.updateDialog.update(self.updateDialogProgress, '\n'.join(
                        [LANGUAGE(30168) % self.settingChannel, LANGUAGE(30180) % (index + 1)]))

                parameter = rule.runAction(action, self, parameter)

            index += 1

        self.runningActionChannel = 0
        self.runningActionId = 0
        return parameter

    def threadPause(self):
        if threading.active_count() > 1:
            while self.threadPaused == True and self.myOverlay.isExiting == False:
                xbmc.Monitor().waitForAbort(self.sleepTime)

            # This will fail when using config.py
            try:
                if self.myOverlay.isExiting == True:
                    self.log("IsExiting")
                    return False
            except:
                pass

        return True

    def escapeDirJSON(self, dir_name):  # todo: refactor/deprecate
        mydir = uni(dir_name)

        if mydir.find(":"):
            mydir = mydir.replace("\\", "\\\\")

        return mydir
