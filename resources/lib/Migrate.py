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

import Channel
import Globals
import ChannelList
from Settings import ChannelSettings
from log import Log


class Migrate(Log):
    def migrate(self):
        self.log("migration")
        curver = "0.0.0"

        try:
            curver = Globals.ADDON_SETTINGS.getSetting("Version")
            forceChannelRebuild = Globals.ADDON.getSettingBool('ForceChannelRebuild')

            if len(curver) == 0:
                curver = "0.0.0"
        except:
            curver = "0.0.0"
            forceChannelRebuild = False

        if curver == Globals.VERSION and not forceChannelRebuild:
            return True

        Globals.ADDON_SETTINGS.setSetting("Version", Globals.VERSION)
        self.log("version is " + curver)

        if curver == "0.0.0" or forceChannelRebuild:
            if self.initializeChannels():
                Globals.ADDON.setSettingBool('ForceChannelRebuild', False)
                Globals.ADDON.setSettingBool('ForceChannelReset', True)

        return True

    def initializeChannels(self):
        self.log('initializeChannels')
        chanlist = ChannelList.ChannelList()
        chanlist.background = True
        chanlist.fillTVInfo(True)
        chanlist.fillMovieInfo(True)
        # id and collect special channels
        customChannels = self.collectCustomChannels()

        # Now create TV networks, followed by mixed genres, followed by TV genres, and finally movie genres
        def mixSort(x): return x[1] + x[2]
        mixedlist = chanlist.makeMixedList(
            chanlist.showGenreList, chanlist.movieGenreList, key=mixSort, reverse=True, keepCounts=True)
        if mixedlist:
            mixedlist = list(filter(lambda x: x[1] > 2, mixedlist))  # keep only genres with 3+ thshows
            mixedlist = [[ig[0], ig[1] + ig[2]] for ig in mixedlist]  # 2nd index = sum of counts
            # remove used genre from their corresponding lists
            mmgenre = [ig[0] for ig in mixedlist]
            chanlist.showGenreList = [iG for iG in chanlist.showGenreList if iG[0] not in mmgenre]
            chanlist.movieGenreList = [iG for iG in chanlist.movieGenreList if iG[0] not in mmgenre]

         # clear current channel settings
        Globals.ADDON_SETTINGS.Channels.clear()
        # add new channels
        currentchan = 1
        currentchan = self.initialAddChannels(chanlist.networkList, Channel.ChannelType.NETWORK, currentchan)
        currentchan = self.initialAddChannels(mixedlist,  Channel.ChannelType.MIX_GENRE, currentchan)
        currentchan = self.initialAddChannels(
            chanlist.showGenreList,  Channel.ChannelType.TVSHOW_GENRE, currentchan)
        currentchan = self.initialAddChannels(
            chanlist.movieGenreList,  Channel.ChannelType.MOVIE_GENRE, currentchan)
        if Globals.ADDON.getSettingBool("AudioChannels"):
            chanlist.fillMusicInfo(True)
            currentchan = self.initialAddChannels(
                chanlist.musicGenreList, Channel.ChannelType.MUSIC_GENRE, currentchan)

        # add custom Channels to end of list
        currentchan += 5  # add 5 channel gap
        for ch, settings in customChannels:
            Globals.ADDON_SETTINGS.setChannelSettings(currentchan, settings)
            currentchan += 1

        return currentchan > 1

    '''creates channels settings from thelist array that meet the lowerlimit  upto 11 channels
    thelist: 2d array with count# on index 1 decending ordered'''
    def initialAddChannels(self, thelist, chantype, currentchan):
        lowerlimit = 1
        if thelist and thelist[0][1] > lowerlimit:
            thelist = sorted(thelist[:11])  # trim and then sort to alphabetical(keep sort?)
            for item in thelist:
                settings = ChannelSettings()
                settings.type = chantype
                settings._1 = item[0]
                Globals.ADDON_SETTINGS.setChannelSettings(currentchan, settings)
                currentchan += 1
        return currentchan

    def collectCustomChannels(self):
        from Channel import ChannelType
        stdChTypes = [ChannelType.MOVIE_GENRE, ChannelType.MIX_GENRE, ChannelType.TVSHOW_GENRE,
                      ChannelType.NETWORK, ChannelType.MUSIC_GENRE, ChannelType.UNKNOWN]
        customChannels = [(ch, setting) for ch, setting in Globals.ADDON_SETTINGS.Channels.items()
                          if setting.type not in stdChTypes]
        self.log('Custom Channels found - %d' % len(customChannels))
        return customChannels
