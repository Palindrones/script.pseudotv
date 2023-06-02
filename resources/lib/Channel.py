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

from Playlist import Playlist, PlaylistItem
from Globals import *
from log import Log

class Channel(Log):
    def __init__(self):
        self.Playlist:Playlist = Playlist()
        self.name = ''
        self.playlistPosition = 0
        self.showTimeOffset = 0
        self.lastAccessTime = 0
        self.totalTimePlayed = 0    #mins
        self.fileName = ''
        self.isPaused = False
        self.isValid = False
        self.isRandom = False
        self.mode = 0
        self.ruleList = []
        self.channelNumber = 0
        self.isSetup = False
        self.isSkipped = False
        

    def setPlaylist(self, filename) -> bool:
        return self.Playlist.load(filename)


    def loadRules(self, channel):           #todo: review method duplicates  config.py
        from Rules import RulesList, BaseRule

        del self.ruleList[:]
        listrules = RulesList()
        self.channelNumber = channel

        try:
            rulecount = int(ADDON_SETTINGS.getChannelSetting(channel, 'rulecount'))

            for i in range(rulecount):
                ruleid = int(ADDON_SETTINGS.getChannelSetting(channel, 'rule_' + str(i + 1) + '_id'))
                rule = listrules.getRuleById(ruleid)
                if rule:
                    self.ruleList.append(rule.copy())
                    for x in range(rule.getOptionCount()):
                        self.ruleList[-1].optionValues[x] = ADDON_SETTINGS.getChannelSetting(channel, 'rule_' + str(i + 1) + '_opt_' + str(x + 1))

                    self.log("Added rule - " + self.ruleList[-1].getTitle())
        except:
            self.ruleList = []


    def setPaused(self, paused):
        self.isPaused = paused


    def setShowTime(self, thetime):
        self.showTimeOffset = thetime // 1


    def setShowPosition(self, show):
        show = int(show)
        self.playlistPosition = self.fixPlaylistIndex(show)


    def setAccessTime(self, thetime):
        self.lastAccessTime = thetime // 1


    def getCurrentDuration(self):
        return self.getItemDuration(self.playlistPosition)


    def getItem(self, index) -> PlaylistItem:
        index = self.fixPlaylistIndex(index)
        return self.Playlist[index]

    def getItemDuration(self, index):   #todo: review logic             
        return  self.Playlist.getduration(self.fixPlaylistIndex(index))#self.getItem(index).duration#

    def getTotalDuration(self):
        return self.Playlist.totalDuration

    def getCurrentDescription(self):
        return self.getItemDescription(self.playlistPosition)

    def getItemDescription(self, index):
        return self.getItem(index).description#self.Playlist.getdescription(self.fixPlaylistIndex(index))

    def getCurrentEpisodeTitle(self):
        return self.getItemEpisodeTitle(self.playlistPosition)

    def getItemPlaycount(self, index):
        return self.getItem(index).playcount #self.Playlist.getplaycount(self.fixPlaylistIndex(index))

    def getItemEpisodeTitle(self, index):
        return self.getItem(index).episodetitle#self.Playlist.getepisodetitle(self.fixPlaylistIndex(index))


    def getCurrentTitle(self):
        return self.getItem(self.playlistPosition).episodetitle#self.getItemTitle(self.playlistPosition)


    def getItemTitle(self, index):
        return self.getItem(index).title#self.Playlist.getTitle(self.fixPlaylistIndex(index))


    def getCurrentFilename(self):
        return self.getItem(self.playlistPosition).filename#self.getItemFilename(self.playlistPosition)


    def getItemFilename(self, index):
        return self.getItem(index).filename#self.Playlist.getfilename(self.fixPlaylistIndex(index))


    def fixPlaylistIndex(self, index):
        if self.Playlist.size() == 0:
            return index

        while index >= self.Playlist.size():
            index -= self.Playlist.size()

        while index < 0:
            index += self.Playlist.size()

        return index


    def addShowPosition(self, addition):
        self.setShowPosition(self.playlistPosition + addition)
