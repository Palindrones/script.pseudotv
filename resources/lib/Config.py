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
from contextlib import contextmanager
from Channel import ChannelType
from Migrate import Migrate
from FileAccess import FileAccess
from AdvancedConfig import AdvancedConfig
from ChannelList import ChannelList
from Globals import *
import xbmc
import xbmcgui
import xbmcaddon
import xbmcvfs
import os
import sys

from Playlist import SmartPlaylist
from Rules import RulesList
from Settings import ChannelSettings
from log import Log


ADDON = xbmcaddon.Addon(id='script.pseudotv')
CWD = ADDON.getAddonInfo('path')
RESOURCE = xbmcvfs.translatePath(os.path.join(CWD, 'resources', 'lib').encode("utf-8"))

sys.path.append(RESOURCE)

SkinID = xbmc.getSkinDir()
if SkinID != 'skin.estuary':
    import MyFont
    if MyFont.getSkinRes() == '1080i':
        MyFont.addFont("PseudoTv10", "NotoSans-Regular.ttf", "23")
        MyFont.addFont("PseudoTv12", "NotoSans-Regular.ttf", "25")
        MyFont.addFont("PseudoTv13", "NotoSans-Regular.ttf", "30")
        MyFont.addFont("PseudoTv14", "NotoSans-Regular.ttf", "32")
    else:
        MyFont.addFont("PseudoTv10", "NotoSans-Regular.ttf", "14")
        MyFont.addFont("PseudoTv12", "NotoSans-Regular.ttf", "16")
        MyFont.addFont("PseudoTv13", "NotoSans-Regular.ttf", "20")
        MyFont.addFont("PseudoTv14", "NotoSans-Regular.ttf", "22")


@contextmanager
def busy_dialog():
    xbmc.executebuiltin('ActivateWindow(busydialognocancel)')
    try:
        yield
    finally:
        xbmc.executebuiltin('Dialog.Close(busydialognocancel)')


class ConfigWindow(xbmcgui.WindowXMLDialog, Log):
    __name__ = 'ChannelConfig'

    def __init__(self, *args, **kwargs):
        self.log("__init__")
        xbmcgui.WindowXMLDialog.__init__(self, *args, **kwargs)
        self.madeChanges = 0
        self.showingList = True
        self.channel = 0
        self.settings = ChannelSettings()
        self.savedRules = False

        if CHANNEL_SHARING:
            realloc = ADDON.getSetting('SettingsFolder')
            FileAccess.copy(realloc + '/settings2.xml', SETTINGS_LOC + '/settings2.xml')  # note: keep this for next few version
            FileAccess.copy(realloc + '/settings2.json', SETTINGS_LOC + '/settings2.json')

        ADDON_SETTINGS.loadSettings()
        ADDON_SETTINGS.disableWriteOnSave()
        self.doModal()
        self.log("__init__ return")

    def onInit(self):
        self.log("onInit")

        for i in range(len(ChannelType) - 1):
            try:
                self.getControl(120 + i).setVisible(False)
            except:
                pass

        migratemaster = Migrate()
        migratemaster.migrate()
        with busy_dialog():
            self.prepareConfig()
        self.myRules = AdvancedConfig("script.pseudotv.AdvancedConfig.xml", CWD, "default")
        self.log("onInit return")

    def onFocus(self, controlId):
        pass

    def onAction(self, act):
        action = act.getId()

        if action in ACTION_PREVIOUS_MENU:
            if self.showingList == False:
                self.cancelChan()
                self.hideChanDetails()
            else:
                if self.madeChanges == 1:
                    dlg = xbmcgui.Dialog()

                    if dlg.yesno(xbmc.getLocalizedString(190), LANGUAGE(30032)):
                        ADDON_SETTINGS.writeSettings()

                        if CHANNEL_SHARING:
                            realloc = ADDON.getSetting('SettingsFolder')
                            FileAccess.copy(SETTINGS_LOC + '/settings2.json', realloc + '/settings2.json')
                self.close()
        elif action == CONTEXT_MENU:
            curchan = self.listcontrol.getSelectedPosition() + 1
            AffectChannelOptions = ("Copy Channel", "Swap Channels",
                                    "Insert Channel (and move down)", "Delete Channel (and move up)", "Clear Channel")
            ChannelAction = xbmcgui.Dialog().select("Choose An Action For Channel %d" % curchan, AffectChannelOptions)
            if ChannelAction != -1:
                if ChannelAction == 0:
                    CopyToChannel = int(xbmcgui.Dialog().numeric(0, "Copy To (and overwrite) Channel"))
                    if 1 <= CopyToChannel <= 9999:
                        self.copyChannel(curchan, CopyToChannel)
                elif ChannelAction == 1:
                    SwapToChannel = int(xbmcgui.Dialog().numeric(
                        0, "Swap Channel %d with Channel:" % curchan))
                    if 1 <= SwapToChannel <= 9999:
                        self.swapChannel(curchan, SwapToChannel)
                elif ChannelAction == 2:
                    self.insertChannel(curchan)
                    #xbmc.executebuiltin('Notification(%s,%s)' % (curchan,FirstEmpty))
                elif ChannelAction == 3:
                    self.deleteChannel(curchan)
                elif ChannelAction == 4:
                    self.clearChannel(curchan)
        elif act.getButtonCode() == 61575:      # Delete button
            curchan = self.listcontrol.getSelectedPosition() + 1
            self.clearChannel(curchan)

    def saveSettings(self):
        self.log("saveSettings channel " + str(self.channel))
        chan = int(self.channel)
        settings = ChannelSettings()
        try:
            settings = ADDON_SETTINGS.getChannelSettings(chan)
        except:
            self.log("Unable to get channel type")

        """ labels_1 = {ChannelType.PLAYLIST:(130,getLabel2),ChannelType.NETWORK:(142,getLabel),ChannelType.STUDIO:(152,getLabel),
                    ChannelType.TVSHOW_GENRE:(162,getLabel)} """

        if settings.type == ChannelType.PLAYLIST:
            settings._1 = self.getControl(130).getLabel2()
        elif settings.type == ChannelType.NETWORK:
            settings._1 = self.getControl(142).getLabel()
        elif settings.type == ChannelType.STUDIO:
            settings._1 = self.getControl(152).getLabel()
        elif settings.type == ChannelType.TVSHOW_GENRE:
            settings._1 = self.getControl(162).getLabel()
        elif settings.type == ChannelType.MOVIE_GENRE:
            settings._1 = self.getControl(172).getLabel()
        elif settings.type == ChannelType.MIX_GENRE:
            settings._1 = self.getControl(182).getLabel()
        elif settings.type == ChannelType.TVSHOW:
            settings._1 = self.getControl(192).getLabel()

            if self.getControl(194).isSelected():
                settings._2 = str(MODE_ORDERAIRDATE)
            else:
                settings._2 = '0'
        elif settings.type == ChannelType.DIRECTORY:
            settings._1 = self.getControl(200).getLabel()
        elif settings.type == ChannelType.MUSIC_GENRE:
            settings._1 = self.getControl(212).getLabel()
        elif settings.type == ChannelType.UNKNOWN:
            settings = ChannelSettings()

        if self.savedRules:
            settings.rules = RulesList.saveRules(self.ruleList)

        # Check to see if the user changed anything
        if settings != self.settings or self.savedRules:
            self.madeChanges = 1
            settings.changed = True
            ADDON_SETTINGS.setChannelSettings(chan, settings)

        self.log("saveSettings return")

    def cancelChan(self):
        ADDON_SETTINGS.setChannelSettings(self.channel, self.settings)

    def hideChanDetails(self):
        self.getControl(106).setVisible(False)

        for i in range(len(ChannelType) - 1):
            try:
                self.getControl(120 + i).setVisible(False)
            except:
                pass

        self.setFocusId(102)
        self.getControl(105).setVisible(True)
        self.showingList = True
        self.updateListing(self.channel)
        self.listcontrol.selectItem(self.channel - 1)

    def onClick(self, controlId):
        self.log("onClick " + str(controlId))
        if controlId == 102:        # Channel list entry selected
            self.getControl(105).setVisible(False)
            self.getControl(106).setVisible(True)
            self.channel = self.listcontrol.getSelectedPosition() + 1
            self.changeChanType(self.channel, 0)
            if self.settings.rules:
                self.getControl(114).setLabel('[B]$LOCALIZE[10038] $LOCALIZE[5][/B]*')
            else:
                self.getControl(114).setLabel('[B]$LOCALIZE[10038] $LOCALIZE[5][/B]')
            self.setFocusId(110)
            self.showingList = False
            self.savedRules = False

        elif controlId == 110 or controlId == 111 or controlId == 109:
            ChannelTypeOptions = [self.getChanTypeLabel(chType) for chType in ChannelType]
            channelType = xbmcgui.Dialog().select("Choose A Channel Type", ChannelTypeOptions)
            if channelType == 9:
                channelType = ChannelType.UNKNOWN
            if channelType != -1:
                channelType = ChannelType(channelType)
                self.setChanType(self.channel, channelType)
        elif controlId == 112:      # Ok button
            if self.showingList == False:
                self.saveSettings()
                self.hideChanDetails()
            else:
                if self.madeChanges == 1:
                    ADDON_SETTINGS.writeSettings()
                    if CHANNEL_SHARING:
                        realloc = ADDON.getSetting('SettingsFolder')
                        FileAccess.copy(SETTINGS_LOC + '/settings2.json', realloc + '/settings2.json')
                self.close()
        elif controlId == 113:      # Cancel button
            if self.showingList == False:
                self.cancelChan()
                self.hideChanDetails()
            else:
                self.close()
        elif controlId == 114:      # Rules button
            self.myRules.ruleList = self.ruleList
            self.myRules.doModal()

            if self.myRules.wasSaved == True:
                self.ruleList = self.myRules.ruleList
                self.savedRules = True
        elif controlId == 130:      # Playlist-type channel, playlist button
            dlg = xbmcgui.Dialog()
            retval = dlg.browse(1, "Channel " + str(self.channel) + " Playlist", "files",
                                ".xsp", False, False, "special://videoplaylists/")

            if retval != "special://videoplaylists/":
                self.getControl(130).setLabel(SmartPlaylist.getSmartPlaylistName(retval), label2=retval)
        elif controlId == 140 or controlId == 141:      # Network TV channel
            ListOptions = self.networkList
            ListChoice = xbmcgui.Dialog().select("Choose A Network", ListOptions)
            if ListChoice != -1:
                self.setListData(self.networkList, 142, ListChoice)
        elif controlId == 150 or controlId == 151:      # Movie studio channel
            ListOptions = self.studioList
            ListChoice = xbmcgui.Dialog().select("Choose A Studio", ListOptions)
            if ListChoice != -1:
                self.setListData(self.studioList, 152, ListChoice)
        elif controlId == 160 or controlId == 161:      # TV Genre channel
            ListOptions = self.showGenreList
            ListChoice = xbmcgui.Dialog().select("Choose A Genre", ListOptions)
            if ListChoice != -1:
                self.setListData(self.showGenreList, 162, ListChoice)
        elif controlId == 170 or controlId == 171:      # Movie Genre channel
            ListOptions = self.movieGenreList
            ListChoice = xbmcgui.Dialog().select("Choose A Genre", ListOptions)
            if ListChoice != -1:
                self.setListData(self.movieGenreList, 172, ListChoice)
        elif controlId == 180 or controlId == 181:      # Mixed Genre channel
            ListOptions = self.mixedGenreList
            ListChoice = xbmcgui.Dialog().select("Choose A Genre", ListOptions)
            if ListChoice != -1:
                self.setListData(self.mixedGenreList, 182, ListChoice)
        elif controlId == 210 or controlId == 211:      # Music Genre channel
            ListOptions = self.musicGenreList
            ListChoice = xbmcgui.Dialog().select("Choose A Genre", ListOptions)
            if ListChoice != -1:
                self.setListData(self.musicGenreList, 212, ListChoice)
        elif controlId == 190 or controlId == 191:      # TV Show channel
            ListOptions = self.showList
            ListChoice = xbmcgui.Dialog().select("Choose A Genre", ListOptions)
            if ListChoice != -1:
                self.setListData(self.showList, 192, ListChoice)
        elif controlId == 200:      # Directory channel, select
            dlg = xbmcgui.Dialog()
            retval = dlg.browse(0, "Channel " + str(self.channel) + " Directory", "files")

            if len(retval) > 0:
                self.getControl(200).setLabel(retval)

        self.log("onClick return")

    def copyChannel(self, origchannel: int, newchannel: int):
        self.log("copyChannel channel %d to %d" % (origchannel, newchannel))
        ADDON_SETTINGS.Channels[newchannel] = ADDON_SETTINGS.Channels[origchannel]
        ADDON_SETTINGS.Channels[newchannel].changed = True
        from Rules import RulesList
        self.ruleList = RulesList.loadRules(ADDON_SETTINGS.Channels[newchannel].rules)
        self.madeChanges = 1
        self.updateListing(newchannel)
        self.log("copyChannel return")

    def clearChannel(self, curchan):
        self.log("clearChannel channel " + str(curchan))
        if curchan in ADDON_SETTINGS.Channels:
            ADDON_SETTINGS.Channels.pop(curchan)
            self.updateListing(curchan)
            self.madeChanges = 1
        self.log("clearChannel return")

    def swapChannel(self, curchan, swapChannel):
        self.log("swapChannel channel %d and %d" % (curchan, swapChannel))
        curChannel = ADDON_SETTINGS.Channels[curchan]
        ADDON_SETTINGS.Channels[curchan] = ADDON_SETTINGS.Channels[swapChannel]
        ADDON_SETTINGS.Channels[swapChannel] = curChannel
        self.updateListing(swapChannel)
        self.updateListing(curchan)
        self.log("swapChannel return")

    def insertChannel(self, curchan):
        self.log("insertChannel channel " + str(curchan))
        # note order of dict is based on insertion
        ADDON_SETTINGS.Channels = {k+1 if k >= curchan else k: v for k,
                                   v in sorted(ADDON_SETTINGS.Channels.items())}
        #ADDON_SETTINGS.Channels[curchan] = ChannelSettings()
        self.clearChannel(curchan)
        self.updateListing()
        self.log("insertChannel return")

    def deleteChannel(self, curchan):
        self.log("deleteChannel channel " + str(curchan))
        if curchan == ADDON_SETTINGS.MaxChannel():
            self.clearChannel(curchan)
        else:
            # note order of dict is based on insertion
            ADDON_SETTINGS.Channels = {k-1 if k > curchan else k: v for k,
                                       v in sorted(ADDON_SETTINGS.Channels.items())}
        self.madeChanges = 1
        self.updateListing()
        self.log("deleteChannel return")

    def setListData(self, thelist, controlid, val):
        self.getControl(controlid).setLabel(thelist[val])

    def setChanType(self, channel, chantype: ChannelType):
        self.log("setChanType " + str(channel) + ", " + str(chantype))
        if chantype not in ChannelType:
            chantype = ChannelType.UNKNOWN
        if channel not in ADDON_SETTINGS.Channels:
            ADDON_SETTINGS.Channels[channel] = ChannelSettings()
        ADDON_SETTINGS.Channels[channel].type = chantype
        self._SetChannelTypeControls(chantype)
        self.fillInDetails(channel)
        self.log("setChanType return")

    def changeChanType(self, channel, val):  # todo: refactor method/and usage
        self.log("changeChanType " + str(channel) + ", " + str(val))
        if val != 0:
            return self.setChanType(channel, ChannelType(val))
        else:
            try:
                self.settings = ADDON_SETTINGS.getChannelSettings(channel)
            except:
                self.settings = ChannelSettings()

        self._SetChannelTypeControls(self.settings.type)
        self.fillInDetails(channel)
        self.log("changeChanType return")

    def _SetChannelTypeControls(self, chantype):
        for i in range(len(ChannelType)-1):
            if i == chantype.value:
                self.getControl(120 + i).setVisible(True)
                self.getControl(110).controlDown(self.getControl(120 + ((i + 1) * 10)))

                try:
                    self.getControl(111).controlDown(self.getControl(120 + ((i + 1) * 10 + 1)))
                except:
                    self.getControl(111).controlDown(self.getControl(120 + ((i + 1) * 10)))
            else:
                try:
                    self.getControl(120 + i).setVisible(False)
                except:
                    pass

    def fillInDetails(self, channel):
        self.log("fillInDetails " + str(channel))
        self.getControl(104).setLabel("Channel " + str(channel))
        chansetting = ChannelSettings()

        try:
            chansetting = ADDON_SETTINGS.getChannelSettings(channel)
        except:
            self.log("Unable to get some setting")

        self.getControl(109).setLabel(self.getChanTypeLabel(chansetting.type))

        if chansetting.type == ChannelType.PLAYLIST:
            plname = SmartPlaylist.getSmartPlaylistName(chansetting._1)

            if len(plname) == ChannelType.PLAYLIST:
                chansetting._1 = ''
            self.getControl(130).setLabel(SmartPlaylist.getSmartPlaylistName(
                chansetting._1), label2=chansetting._1)
        elif chansetting.type == ChannelType.NETWORK:
            self.getControl(142).setLabel(self.findItemInList(self.networkList, chansetting._1))
        elif chansetting.type == ChannelType.STUDIO:
            self.getControl(152).setLabel(self.findItemInList(self.studioList, chansetting._1))
        elif chansetting.type == ChannelType.TVSHOW_GENRE:
            self.getControl(162).setLabel(self.findItemInList(self.showGenreList, chansetting._1))
        elif chansetting.type == ChannelType.MOVIE_GENRE:
            self.getControl(172).setLabel(self.findItemInList(self.movieGenreList, chansetting._1))
        elif chansetting.type == ChannelType.MIX_GENRE:
            self.getControl(182).setLabel(self.findItemInList(self.mixedGenreList, chansetting._1))
        elif chansetting.type == ChannelType.MUSIC_GENRE:
            self.getControl(210).setLabel(self.findItemInList(self.musicGenreList, chansetting._1))
        elif chansetting.type == ChannelType.TVSHOW:
            self.getControl(192).setLabel(self.findItemInList(self.showList, chansetting._1))
            self.getControl(194).setSelected(chansetting._2 == str(MODE_ORDERAIRDATE))
        elif chansetting.type == ChannelType.DIRECTORY:
            if (chansetting._1.find('/') > -1) or (chansetting._1.find('\\') > -1):  # todo: review logic
                plname = SmartPlaylist.getSmartPlaylistName(chansetting._1)

                if len(plname) != 0:
                    chansetting._1 = ''
            else:
                chansetting._1 = ''

            self.getControl(200).setLabel(chansetting._1)

        self.ruleList = RulesList.loadRules(chansetting.rules)
        self.log("fillInDetails return")

    def findItemInList(self, thelist, item):
        loitem = item.lower()

        for i in thelist:
            if loitem == i.lower():
                return item

        if len(thelist) > 0:
            return thelist[0]

        return ''

    def getChanTypeLabel(self, chantype):
        if chantype == ChannelType.PLAYLIST:
            return LANGUAGE(30181)
        elif chantype == ChannelType.NETWORK:
            return LANGUAGE(30182)
        elif chantype == ChannelType.STUDIO:
            return LANGUAGE(30183)
        elif chantype == ChannelType.TVSHOW_GENRE:
            return LANGUAGE(30184)
        elif chantype == ChannelType.MOVIE_GENRE:
            return LANGUAGE(30185)
        elif chantype == ChannelType.MIX_GENRE:
            return LANGUAGE(30186)
        elif chantype == ChannelType.TVSHOW:
            return LANGUAGE(30187)
        elif chantype == ChannelType.DIRECTORY:
            return LANGUAGE(30189)
        elif chantype == ChannelType.MUSIC_GENRE:
            return LANGUAGE(30201)
        elif chantype == ChannelType.UNKNOWN:
            return LANGUAGE(30164)

        return ''

    def prepareConfig(self):
        self.log("prepareConfig")
        self.getControl(105).setVisible(False)
        self.getControl(106).setVisible(False)
        chnlst = ChannelList()
        chnlst.fillTVInfo()
        chnlst.fillMovieInfo()
        chnlst.fillMusicInfo()
        self.mixedGenreList = chnlst.makeMixedList(
            chnlst.showGenreList, chnlst.movieGenreList, key=lambda x: x[0].lower())
        self.networkList = [n for n, c in chnlst.networkList]
        self.studioList = [n for n, c in chnlst.studioList]
        self.showGenreList = [n for n, c in chnlst.showGenreList]
        self.movieGenreList = [n for n, c in chnlst.movieGenreList]
        self.showList = [n for n, *c in chnlst.showList]
        self.musicGenreList = [n for n, c in chnlst.musicGenreList]

        self.showList.sort()
        self.listcontrol = self.getControl(102)

        # create channels + 10 controls
        for i in range(1, ADDON_SETTINGS.MaxChannel() + 10):
            theitem = xbmcgui.ListItem()
            theitem.setLabel(str(i))
            self.listcontrol.addItem(theitem)
        self.maxChannelControls = i

        self.updateListing()
        self.getControl(105).setVisible(True)
        self.getControl(106).setVisible(False)
        self.setFocusId(102)
        self.log("prepareConfig return")

    def updateListing(self, channel=None):  # refactor to use channelist method.
        self.log("updateListing")
        start = channel or 1
        end = (channel or self.maxChannelControls) + 1
        for i in range(start, end):
            newlabel = ''

            try:
                chansetting = ADDON_SETTINGS.getChannelSettings(i)
                newlabel = ChannelList.getChannelName(chansetting.type, chansetting._1)
            except:
                pass
            try:
                theitem = self.listcontrol.getListItem(i-1)
                theitem.setLabel2(newlabel)
            except:
                pass
            # if uncommented (replacing the final line), this would put a marker on the main channel list indicating which channels had advanced rules
            #ruleMarker = ''
            # if self.checkRules(str(i+1)) == True:
            #    ruleMarker = "*"

            #theitem.setLabel2(newlabel + ruleMarker)
            # theitem.setLabel2(newlabel)

        self.log("updateListing return")


mydialog = ConfigWindow("script.pseudotv.ChannelConfig.xml", CWD, "default")
del mydialog
