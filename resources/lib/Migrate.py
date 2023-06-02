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

import os
import xbmcaddon, xbmc, xbmcgui
import Globals
import ChannelList
from log import Log, LogInfo


class Migrate(LogInfo):
    def migrate(self):
        self.log("migration")
        curver = "0.0.0"

        try:
            curver = Globals.ADDON_SETTINGS.getSetting("Version")

            if len(curver) == 0:
                curver = "0.0.0"
        except:
            curver = "0.0.0"

        if curver == Globals.VERSION:
            return True

        Globals.ADDON_SETTINGS.setSetting("Version", Globals.VERSION)
        self.log("version is " + curver)

        if curver == "0.0.0":
            if self.initializeChannels():
                return True

        return True

    def initializeChannels(self):
        chanlist = ChannelList.ChannelList()
        chanlist.background = True
        chanlist.fillTVInfo(True)
        chanlist.fillMovieInfo(True)
        # Now create TV networks, followed by mixed genres, followed by TV genres, and finally movie genres
        mixedlist = chanlist.makeMixedList(chanlist.showGenreList, chanlist.movieGenreList, key=lambda x: x[1] + x[2], reverse=True, keepCounts=True)
        if mixedlist: 
            mixedlist = list(filter( lambda x: x[1]>2, mixedlist))    #keep only genres with 3+ thshows
            mixedlist = [ [ig[0], ig[1]+ ig[2]] for ig in mixedlist]  #2nd index sum of counts
                #remove used genre from their corresponding lists
            mmgenre = [ig[0] for ig in mixedlist]
            chanlist.showGenreList = [iG for iG in chanlist.showGenreList if iG[0] not in mmgenre]
            chanlist.movieGenreList = [iG for iG in chanlist.movieGenreList if iG[0] not in mmgenre]
                                    
        currentchan = 1
        currentchan = self.initialAddChannels(chanlist.networkList, 1, currentchan)
        currentchan = self.initialAddChannels(mixedlist, 5, currentchan)
        currentchan = self.initialAddChannels(chanlist.showGenreList, 3, currentchan)
        currentchan = self.initialAddChannels(chanlist.movieGenreList, 4, currentchan)
        if Globals.ADDON_SETTINGS.getSetting("AudioChannels") == "true":
            chanlist.fillMusicInfo(True)
            currentchan = self.initialAddChannels(chanlist.musicGenreList, 8, currentchan)
            
        if currentchan > 1:
            return True

        return False
    
    '''creates channels settings from thelist array that meet the lowerlimit  upto 11 channels
    thelist: 2d array with count# on index 1 decending ordered'''
    def initialAddChannels(self, thelist, chantype, currentchan):
        lowerlimit = 1
        if thelist and thelist[0][1] > lowerlimit:
            thelist = sorted(thelist[:11])         #trim and then sort to alphabetical(keep sort?)
            for item in  thelist:
                Globals.ADDON_SETTINGS.setChannelSetting(currentchan, "type", str(chantype))
                Globals.ADDON_SETTINGS.setChannelSetting(currentchan, "1", item[0])
                currentchan += 1                                
        return currentchan