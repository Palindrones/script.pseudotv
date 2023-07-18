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

from enum import IntEnum
from Playlist import Playlist, PlaylistItem
#from Globals import *
from log import Log


class ChannelType(IntEnum):
    PLAYLIST = 0
    NETWORK = 1
    STUDIO = 2
    TVSHOW_GENRE = 3
    MOVIE_GENRE = 4
    MIX_GENRE = 5
    TVSHOW = 6
    DIRECTORY = 7
    MUSIC_GENRE = 8
    UNKNOWN = 9999


class Channel(Log):
    def __init__(self):
        from Settings import ChannelSettings
        self.Playlist: Playlist = Playlist()
        self.name = ''
        self.type = ChannelType.UNKNOWN
        self.playlistPosition = 0
        self.showTimeOffset = 0
        self.lastAccessTime = 0
        self.totalTimePlayed = 0  # mins
        self.fileName = ''
        self.isPaused = False
        self.isValid = False
        self.isRandom = False
        self.mode = 0
        self.ruleList = []
        self.channelNumber = 0
        self.isSetup = False
        self.isSkipped = False
        self.settings: ChannelSettings = ChannelSettings()

    def setPlaylist(self, filename) -> bool:
        return self.Playlist.load(filename)

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

    def getItemDuration(self, index):  # todo: review logic
        return self.Playlist.getduration(self.fixPlaylistIndex(index))

    def getTotalDuration(self):
        return self.Playlist.totalDuration

    def getCurrentDescription(self):
        return self.getItemDescription(self.playlistPosition)

    def getItemDescription(self, index):
        return self.getItem(index).description

    def getCurrentEpisodeTitle(self):
        return self.getItemEpisodeTitle(self.playlistPosition)

    def getItemPlaycount(self, index):
        return self.getItem(index).playcount

    def getItemEpisodeTitle(self, index):
        return self.getItem(index).episodetitle

    def getCurrentTitle(self):
        return self.getItem(self.playlistPosition).episodetitle

    def getItemTitle(self, index):
        return self.getItem(index).title

    def getCurrentFilename(self):
        return self.getItem(self.playlistPosition).filename

    def getItemFilename(self, index):
        return self.getItem(index).filename

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
