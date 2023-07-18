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

import xbmc, xbmcgui
import xbmcvfs
import os
import time, threading
import traceback

from ResetWatched import ResetWatched

from Globals import *
from Channel import Channel
from ChannelList import ChannelList
from ChannelListThread import ChannelListThread
from FileAccess import FileAccess
from Migrate import Migrate
from log import Log

try:
    from PIL import Image, ImageEnhance
except:
    pass


class MyPlayer(xbmc.Player, Log):
    __name__ = 'Player'

    def __init__(self):
        xbmc.Player.__init__(self, xbmc.Player())
        self.stopped = False
        self.ignoreNextStop = False


    def onPlayBackStopped(self):
        if self.stopped == False:
            self.log('Playback stopped')
            self.log(''.join(traceback.format_stack()))
            self.log('onPlayBackStopped: ignoreNextStop - %s' % self.ignoreNextStop)	####
            
            if self.ignoreNextStop is False:                
                if self.overlay.sleepTimeValue == 0:
                    self.overlay.sleepTimer = threading.Timer(3, self.overlay.sleepAction)

                self.overlay.sleepTimeValue = 3
                self.overlay.startSleepTimer()
                self.stopped = True
            else:
                self.ignoreNextStop = False

    def onPlayBackError(self) -> None:		####
        self.log('onPlayBackError')
        return super().onPlayBackError()



# overlay window to catch events and change channels
class TVOverlay(xbmcgui.WindowXMLDialog, Log):
    def __init__(self, *args, **kwargs):
        xbmcgui.WindowXMLDialog.__init__(self, *args, **kwargs)
        self.log('__init__')
        # initialize all variables
        self.channels: dict[int,Channel] = {}
        self.Player = MyPlayer()
        self.Player.overlay = self
        self.inputChannel = -1
        self.channelLabel = []
        self.lastActionTime = 0 #time in seconds:float
        self.actionSemaphore = threading.BoundedSemaphore()
        self.channelThread = ChannelListThread(self)
        self.timeStarted = 0    #time in seconds:float
        self.infoOnChange = False
        self.infoDuration = 10
        self.infoOffset = 0
        self.invalidatedChannelCount = 0
        self.showingInfo = False
        self.showChannelBug = False
        self.channelBugPosition = 0
        self.notificationLastChannel = 0
        self.notificationLastShow = 0
        self.notificationShowedNotif = False
        self.isExiting = False
        self.maxChannels = 0            #todo: review usage/deprecate
        self.notPlayingCount = 0
        self.ignoreInfoAction = False
        self.shortItemLength = 120
        self.seekForward = 30
        self.seekBackward = -30
        self.runningActionChannel = 0
        self.channelDelay = 500
        self.numberColor = '0xFF00FF00'
        self.sleepTimeValue = 0     #time in seconds:int

        for i in range(3):
            self.numberColor = NUM_COLOUR[ADDON.getSettingInt("NumberColour")]
            self.channelLabel.append(
                xbmcgui.ControlImage(90 + (35 * i), 90, 50, 50, IMAGES_LOC, colorDiffuse=self.numberColor))
            self.addControl(self.channelLabel[i])
            self.channelLabel[i].setVisible(False)

        self.doModal()
        self.log('__init__ return')

    def resetChannelTimes(self):
        for ch in self.channels.values():
            ch.setAccessTime(self.timeStarted - ch.totalTimePlayed)

    def onFocus(self, controlId):
        pass

    # override the doModal function so we can setup everything first
    def onInit(self):
        self.log('onInit')

        # Don't allow any actions during initialization
        self.actionSemaphore.acquire()
        self.timeStarted = time.time()

        if FileAccess.exists(GEN_CHAN_LOC) is False:
            try:
                FileAccess.makedirs(GEN_CHAN_LOC)
            except:
                self.Error(LANGUAGE(30035))
                return

        if FileAccess.exists(MADE_CHAN_LOC) is False:
            try:
                FileAccess.makedirs(MADE_CHAN_LOC)
            except:
                self.Error(LANGUAGE(30036))
                return

        if FileAccess.exists(CHANNELBUG_LOC) is False:
            try:
                FileAccess.makedirs(CHANNELBUG_LOC)
            except:
                self.Error(LANGUAGE(30036))
                return

        try:
            self.getControl(102).setVisible(False)
            self.backupFiles()
            ADDON_SETTINGS.loadSettings()

            if CHANNEL_SHARING:
                updateDialog = xbmcgui.DialogProgressBG()
                updateDialog.create(ADDON_NAME, '')
                updateDialog.update(1, message='Initializing Channel Sharing')
                FileAccess.makedirs(LOCK_LOC)
                updateDialog.update(50, message='Initializing Channel Sharing')
                self.isMaster = GlobalFileLock.lockFile("MasterLock", False)
                updateDialog.update(100, message='Initializing Channel Sharing')
                xbmc.sleep(200)
                updateDialog.close()
            else:
                self.isMaster = True

            if self.isMaster:
                migratemaster = Migrate()
                migratemaster.migrate()

            self.channelLabelTimer = threading.Timer(3.0, self.hideChannelLabel)
            self.playerTimer = threading.Timer(2.0, self.playerTimerAction)
            self.playerTimer.name = "PlayerTimer"
            self.infoTimer = threading.Timer(5.0, self.hideInfo)

            from EPGWindow import EPGWindow
            self.myEPG = EPGWindow("script.pseudotv.EPG.xml", CWD, "default")
            self.myEPG.MyOverlayWindow = self

            if self.readConfig() is False:
                return

            self.myEPG.channelLogos = self.channelLogos
            self.maxChannels = ADDON_SETTINGS.MaxChannel()
            self.log("maxChannels - " +  str(self.maxChannels))                 ####
            if not self.channels:
                self.Error(LANGUAGE(30037))
                return
        except Exception as e:
            self.Error(LANGUAGE(30038), traceback.format_exc())
            return

        found = any(ch.isValid for ch in self.channels.values())
        if found is False:
            self.Error(LANGUAGE(30038), "No valid channel found")
            return

        if self.sleepTimeValue > 0:
            self.sleepTimer = threading.Timer(self.sleepTimeValue, self.sleepAction)

        self.notificationTimer = threading.Timer(NOTIFICATION_CHECK_TIME, self.notificationAction)

        try:
            if self.forceReset is False:
                self.currentChannel = self.fixChannel(int(ADDON.getSetting('CurrentChannel')))
            else:
                self.currentChannel = self.fixChannel(1)
        except:
            self.currentChannel = self.fixChannel(1)

        self.resetChannelTimes()
        self.setChannel(self.currentChannel)
        self.startSleepTimer()
        self.startNotificationTimer()
        self.playerTimer.start()

        if self.backgroundUpdating < 2 or self.isMaster == False:
            self.channelThread.name = "ChannelThread"
            self.channelThread.start()

        self.actionSemaphore.release()
        self.log('onInit return')

    # setup all basic configuration parameters, including creating the playlists that
    # will be used to actually run this thing
    def readConfig(self):
        self.log('readConfig')
        # Sleep setting is in 30 minute incriments...so multiply by 30, and then 60 (min to sec)
        self.sleepTimeValue = ADDON.getSettingInt('AutoOff') * 1800
        self.log('Auto off is ' + str(self.sleepTimeValue))
        self.infoOnChange = ADDON.getSettingBool("InfoOnChange")
        self.infoDuration = INFO_DUR[ADDON.getSettingInt("InfoLength")]
        self.log('Show info label on channel change is ' + str(self.infoOnChange))
        self.showChannelBug = ADDON.getSettingBool("ShowChannelBug")
        self.channelBugPosition = CHANNELBUG_POS[ADDON.getSettingInt("ChannelBugPosition")]
        self.log('Show channel bug - ' + str(self.showChannelBug))
        self.forceReset = ADDON.getSettingBool('ForceChannelReset')
        self.channelResetSetting = ADDON.getSetting('ChannelResetSetting')
        self.log("Channel reset setting - " + str(self.channelResetSetting))
        self.channelLogos = xbmcvfs.translatePath(ADDON.getSetting('ChannelLogoFolder'))
        self.backgroundUpdating = ADDON.getSettingInt("ThreadMode")
        self.log("Background updating - " + str(self.backgroundUpdating))
        self.showNextItem = ADDON.getSettingBool("EnableComingUp")
        self.log("Show Next Item - " + str(self.showNextItem))
        self.hideShortItems = ADDON.getSettingBool("HideClips")
        self.log("Hide Short Items - " + str(self.hideShortItems))
        self.shortItemLength = SHORT_CLIP_ENUM[ADDON.getSettingInt("ClipLength")]
        self.seekForward = SEEK_FORWARD[ADDON.getSettingInt("SeekForward")]
        self.seekBackward = SEEK_BACKWARD[ADDON.getSettingInt("SeekBackward")]
        self.log("Short item length - " + str(self.shortItemLength))

        if FileAccess.exists(self.channelLogos) is False:
            self.channelLogos = LOGOS_LOC

        self.log('Channel logo folder - ' + self.channelLogos)
        self.channelList = ChannelList()
        self.channelList.myOverlay = self
        self.channels = self.channelList.setupList()

        if not self.channels:
            self.log('readConfig No channel list returned')
            self.end()
            return False

        self.Player.stop()
        self.log('readConfig return')
        return True

    # handle fatal errors: log it, show the dialog, and exit
    def Error(self, *lines):
        self.log('FATAL ERROR: ' + " ".join(lines), xbmc.LOGFATAL)
        dlg = xbmcgui.Dialog()
        dlg.ok(xbmc.getLocalizedString(257), " ".join(lines))
        del dlg
        self.end()

    def channelDown(self):
        self.log('channelDown')

        if self.maxChannels == 1:
            return

        channel = self.fixChannel(self.currentChannel - 1, False)
        self.setChannel(channel)
        self.log('channelDown return')

    def backupFiles(self):
        self.log('backupFiles')

        if not CHANNEL_SHARING:
            return

        realloc = ADDON.getSetting('SettingsFolder')
        FileAccess.copy(realloc + '/settings2.xml', SETTINGS_LOC + '/settings2.xml')   ##note: legacy, keep this for next few version
        FileAccess.copy(realloc + '/settings2.json', SETTINGS_LOC + '/settings2.json')
        realloc = xbmcvfs.translatePath(os.path.join(realloc, 'cache')) + '/'

        # copy all the channels from remote location
        exts = ('.m3u','M3U')
        file_detail = [f for f in xbmcvfs.listdir(realloc)[1] if f.endswith(exts)]
        for f in file_detail:
            FileAccess.copy(os.path.join(realloc, f),os.path.join( CHANNELS_LOC, f))

    def storeFiles(self):
        self.log('storeFiles')

        if not CHANNEL_SHARING:
            return

        realloc = ADDON.getSetting('SettingsFolder')
        FileAccess.copy(SETTINGS_LOC + '/settings2.json', realloc + '/settings2.json')
        realloc = xbmcvfs.translatePath(os.path.join(realloc, 'cache')) + '/'

        for iChannel in self.channels:
            FileAccess.copy(CHANNELS_LOC + 'channel_' + str(iChannel) + '.m3u', realloc + 'channel_' + str(iChannel) + '.m3u')

    def channelUp(self):
        self.log('channelUp')

        if self.maxChannels == 1:
            return

        channel = self.fixChannel(self.currentChannel + 1)
        self.setChannel(channel)
        self.log('channelUp return')

    def message(self, data):
        self.log('Dialog message: ' + data)
        dlg = xbmcgui.Dialog()
        dlg.ok(xbmc.getLocalizedString(19033), data)
        del dlg

    # set the channel, the proper show offset, and time offset
    def setChannel(self, channelNumber):
        self.log('setChannel ' + str(channelNumber))
        self.runActions(RULES_ACTION_OVERLAY_SET_CHANNEL, channelNumber, self.channels[channelNumber])

        if self.Player.stopped:
            self.log('setChannel player already stopped', xbmc.LOGERROR)
            return

        if not channelNumber in self.channels:
            self.log('setChannel invalid channel ' + str(channelNumber), xbmc.LOGERROR)
            return

        if self.channels[channelNumber].isValid is False:
            self.log('setChannel channel not valid ' + str(channelNumber), xbmc.LOGERROR)
            return

        self.lastActionTime = 0
        timedif = 0
        self.getControl(102).setVisible(False)
        self.getControl(103).setImage('')
        self.showingInfo = False

        # first of all, save playing state, time, and playlist offset for
        # the currently playing channel
        if self.Player.isPlaying() and channelNumber != self.currentChannel:
            curChannel = self.channels[self.currentChannel]
            curChannel.setPaused(xbmc.getCondVisibility('Player.Paused'))

            # Automatically pause in serial mode
            if curChannel.mode & MODE_ALWAYSPAUSE > 0:
                curChannel.setPaused(True)

            curChannel.setShowTime(self.Player.getTime())
            curChannel.setShowPosition(xbmc.PlayList(xbmc.PLAYLIST_MUSIC).getposition())
            curChannel.setAccessTime(time.time())

        self.currentChannel = channelNumber
        curChannel = self.channels[self.currentChannel]
        # now load the proper channel playlist
        self.Player.ignoreNextStop = True
        #xbmc.PlayList(xbmc.PLAYLIST_MUSIC).clear()
        self.log("about to load")

        if xbmc.PlayList(xbmc.PLAYLIST_MUSIC).load(curChannel.fileName) is False:
            self.log("Error loading playlist", xbmc.LOGERROR)
            self.InvalidateChannel(channelNumber)
            return

        # Disable auto playlist shuffling if it's on
        if xbmc.getInfoLabel('Playlist.Random').lower() == 'random':
            self.log('Random on.  Disabling.')
            xbmc.PlayList(xbmc.PLAYLIST_MUSIC).unshuffle()

        self.log("repeat all")
        xbmc.executebuiltin("PlayerControl(RepeatAll)")
        curtime = time.time()
        timedif = (curtime - curChannel.lastAccessTime)

        if curChannel.isPaused is False:
            # adjust the show and time offsets to properly position inside the playlist
            while curChannel.showTimeOffset + timedif > curChannel.getCurrentDuration():
                timedif -= curChannel.getCurrentDuration() - curChannel.showTimeOffset
                curChannel.addShowPosition(1)
                curChannel.setShowTime(0)

        xbmc.sleep(self.channelDelay)
        # set the show offset
        self.Player.playselected(curChannel.playlistPosition)
        self.log("playing selected file")
        # set the time offset
        curChannel.setAccessTime(curtime)

        if curChannel.isPaused:
            curChannel.setPaused(False)

            try:
                self.Player.seekTime(curChannel.showTimeOffset)

                if curChannel.mode & MODE_ALWAYSPAUSE == 0:
                    self.Player.pause()

                    if self.waitForVideoPaused() is False:
                        return
            except:
                self.log('Exception during seek on paused channel', xbmc.LOGERROR)
        else:
            seektime = curChannel.showTimeOffset + timedif + int((time.time() - curtime))

            try:
                self.waitForMediaPlaying(10000)
                self.log("Seeking to " + str(seektime))
                self.Player.seekTime(seektime)
                #xbmc.executebuiltin("Seek(%d)" % int(seektime))
            except:
                self.log("Unable to set proper seek time, trying different value")

                try:
                    seektime = curChannel.showTimeOffset + timedif
                    self.Player.seekTime(seektime)
                    #xbmc.executebuiltin("Seek(%d)" % int(seektime))
                except:
                    self.log('Exception during seek', xbmc.LOGERROR)

        self.showChannelLabel(self.currentChannel)
        self.lastActionTime = time.time()
        self.runActions(RULES_ACTION_OVERLAY_SET_CHANNEL_END, channelNumber, curChannel)
        self.log('setChannel return')

    def InvalidateChannel(self, channelNumber):
        self.log("InvalidateChannel" + str(channelNumber))

        if not channelNumber in self.channels:
            self.log("InvalidateChannel invalid channel " + str(channelNumber))
            return

        self.channels[channelNumber].isValid = False
        self.invalidatedChannelCount += 1

        if self.invalidatedChannelCount > 3:
            self.Error(LANGUAGE(30039))
            return

        remaining = sum(ch.isValid for ch in self.channels.values())
        if remaining == 0:
            self.Error(LANGUAGE(30040))
            return

        self.setChannel(self.fixChannel(channelNumber))

    def waitForVideoPaused(self):
        self.log('waitForVideoPaused')
        sleeptime = 0

        while sleeptime < TIMEOUT:
            xbmc.sleep(100)

            if self.Player.isPlaying():
                if xbmc.getCondVisibility('Player.Paused'):
                    break

            sleeptime += 100
        else:
            self.log('Timeout waiting for pause', xbmc.LOGERROR)
            return False

        self.log('waitForVideoPaused return')
        return True
    
    def waitForMediaPlaying(self, timeout = 1000):
        self.log('waitForMediaPlaying')
        sleeptime = 0

        while sleeptime < TIMEOUT:
            if self.Player.isPlaying() and xbmc.getCondVisibility('Player.Playing'):
                    break
            sleeptime += 100
            xbmc.sleep(100)
        else:
            self.log('Timeout waiting for media playing', xbmc.LOGERROR)
            return False

        self.log('waitForMediaPlaying return')
        return True

    def setShowInfo(self):
        self.log('setShowInfo')

        curChannel = self.channels[self.currentChannel]
        if self.infoOffset > 0:
            self.getControl(502).setLabel(LANGUAGE(30041))
        elif self.infoOffset < 0:
            self.getControl(502).setLabel(LANGUAGE(30042))
        elif self.infoOffset == 0:
            self.getControl(502).setLabel(LANGUAGE(30043))

        if self.hideShortItems and self.infoOffset != 0:
            position = xbmc.PlayList(xbmc.PLAYLIST_MUSIC).getposition()
            curoffset = 0
            modifier = 1

            if self.infoOffset < 0:
                modifier = -1

            while curoffset != abs(self.infoOffset):
                position = curChannel.fixPlaylistIndex(position + modifier)

                if curChannel.getItemDuration(position) >= self.shortItemLength:
                    curoffset += 1
        else:
            position = xbmc.PlayList(xbmc.PLAYLIST_MUSIC).getposition() + self.infoOffset

        self.getControl(503).setLabel(curChannel.getItemTitle(position))
        self.getControl(504).setLabel(curChannel.getItemEpisodeTitle(position))
        self.getControl(505).setText(curChannel.getItemDescription(position))
        self.getControl(506).setImage(self.channelLogos + ascii(curChannel.name) + '.png')
        if not FileAccess.exists(self.channelLogos + ascii(curChannel.name) + '.png'):
            self.getControl(506).setImage(IMAGES_LOC + 'Default.png')

        self.log('setShowInfo return')

    # Display the current channel based on self.currentChannel.
    # Start the timer to hide it.
    def showChannelLabel(self, channelNumber):
        self.log('showChannelLabel ' + str(channelNumber))

        if self.channelLabelTimer.is_alive():
            self.channelLabelTimer.cancel()

        tmp = self.inputChannel
        self.hideChannelLabel()
        self.inputChannel = tmp
        curlabel = 0

        if channelNumber > 99:
            self.channelLabel[curlabel].setImage(IMAGES_LOC + 'label_' + str(channelNumber // 100) + '.png')
            self.channelLabel[curlabel].setVisible(True)
            curlabel += 1

        if channelNumber > 9:
            self.channelLabel[curlabel].setImage(IMAGES_LOC + 'label_' + str((channelNumber % 100) // 10) + '.png')
            self.channelLabel[curlabel].setVisible(True)
            curlabel += 1

        self.channelLabel[curlabel].setImage(IMAGES_LOC + 'label_' + str(channelNumber % 10) + '.png')
        self.channelLabel[curlabel].setVisible(True)

        if self.inputChannel == -1 and self.infoOnChange is True:
            self.infoOffset = 0
            xbmc.sleep(self.channelDelay)
            self.showInfo(self.infoDuration)

        self.setChannelBug()

        if xbmc.getCondVisibility('Player.ShowInfo'):
            json_query = '{"jsonrpc": "2.0", "method": "Input.Info", "id": 1}'
            self.ignoreInfoAction = True
            xbmc.executeJSONRPC(json_query)
            
        #start hide channel timmer
        self.channelLabelTimer = threading.Timer(3.0, self.hideChannelLabel)
        self.channelLabelTimer.name = "ChannelLabel"
        self.channelLabelTimer.start()
        self.startNotificationTimer()
        self.log('showChannelLabel return')

    def setChannelBug(self):
        posx = self.channelBugPosition[0]
        posy = self.channelBugPosition[1]
        curChannel = self.channels[self.currentChannel]
        if self.showChannelBug:
            try:
                if not FileAccess.exists(self.channelLogos + ascii(curChannel.name) + '.png'):
                    self.getControl(103).setImage(IMAGES_LOC + 'Default2.png')
                    self.getControl(103).setPosition(posx, posy)
                original = Image.open(self.channelLogos + ascii(curChannel.name) + '.png')
                converted_img = original.convert('LA')
                img_bright = ImageEnhance.Brightness(converted_img)
                converted_img = img_bright.enhance(2.0)
                if not FileAccess.exists(CHANNELBUG_LOC + ascii(curChannel.name) + '.png'):
                    converted_img.save(CHANNELBUG_LOC + ascii(curChannel.name) + '.png')
                self.getControl(103).setImage(CHANNELBUG_LOC + ascii(curChannel.name) + '.png')
                self.getControl(103).setPosition(posx, posy)

            except:
                self.getControl(103).setImage(IMAGES_LOC + 'Default2.png')
                self.getControl(103).setPosition(posx, posy)
        else:
            self.getControl(103).setImage('')

    # Called from the timer to hide the channel label.
    def hideChannelLabel(self):
        self.log('hideChannelLabel')
        """ if self.channelLabelTimer.is_alive():		####
            self.channelLabelTimer.cancel()
            #self.channelLabelTimer.join()
        self.channelLabelTimer = threading.Timer(3.0, self.hideChannelLabel)    #todo: review cancel and join of timer thread before reassign """
        try:
            for i in range(3):
                self.channelLabel[i].setVisible(False)
        except:
            self.Error(traceback.format_exc())

        self.inputChannel = -1
        self.log('hideChannelLabel return')

    def hideInfo(self):
        self.getControl(102).setVisible(False)
        self.getControl(103).setVisible(True)
        self.infoOffset = 0
        self.showingInfo = False

        if self.infoTimer.is_alive():
            self.infoTimer.cancel()

        self.infoTimer = threading.Timer(5.0, self.hideInfo)

    def showInfo(self, timer):
        if self.hideShortItems:
            position = xbmc.PlayList(xbmc.PLAYLIST_MUSIC).getposition() + self.infoOffset

            if self.channels[self.currentChannel].getItemDuration(
                    xbmc.PlayList(xbmc.PLAYLIST_MUSIC).getposition()) < self.shortItemLength:
                return

        self.getControl(103).setVisible(False)
        self.getControl(102).setVisible(True)
        self.showingInfo = True
        self.setShowInfo()

        if self.infoTimer.is_alive():
            self.infoTimer.cancel()

        self.infoTimer = threading.Timer(timer, self.hideInfo)
        self.infoTimer.name = "InfoTimer"

        if xbmc.getCondVisibility('Player.ShowInfo'):
            json_query = '{"jsonrpc": "2.0", "method": "Input.Info", "id": 1}'
            self.ignoreInfoAction = True
            xbmc.executeJSONRPC(json_query)

        self.infoTimer.start()

    # return a valid channel in the proper range
    def fixChannel(self, channelNumber, increasing=True):       
        if increasing:
            direction = 1
        else:
            direction = -1
            
        while (not channelNumber in self.channels) or (self.channels[channelNumber].isValid is False):
            channelNumber = (channelNumber + direction) % (self.maxChannels + 1)
        return channelNumber
        ##            
        #myGenerator = (num  for num in self.channels.keys()[channelNumber::direction] if self.channels[num].isValid)
        #return next(myGenerator, channelNumber)
        
    # Handle all input while videos are playing
    def onAction(self, act):
        action = act.getId()
        self.log('onAction ' + str(action))

        if self.Player.stopped:
            return

        # Since onAction isnt always called from the same thread (weird),
        # ignore all actions if we're in the middle of processing one
        if self.actionSemaphore.acquire(False) is False:
            self.log('Unable to get semaphore')
            return

        lastaction = time.time() - self.lastActionTime

        # during certain times we just want to discard all input
        if lastaction < 2:
            self.log('Not allowing actions')
            action = ACTION_INVALID

        self.startSleepTimer()

        self.log('ACTION: ' + str(action))
        if action == ACTION_SELECT_ITEM:
            # If we're manually typing the channel, set it now
            if self.inputChannel > 0:
                if self.inputChannel != self.currentChannel and self.inputChannel in self.channels:
                    self.setChannel(self.inputChannel)
                    if self.infoOnChange is True:
                        self.infoOffset = 0
                        xbmc.sleep(self.channelDelay)
                        self.showInfo(self.infoDuration)
                self.inputChannel = -1
            else:
                # Otherwise, show the EPG
                if self.channelThread.is_alive():
                    self.channelThread.pause()

                if self.notificationTimer.is_alive():
                    self.notificationTimer.cancel()
                    self.notificationTimer = threading.Timer(NOTIFICATION_CHECK_TIME, self.notificationAction)

                if self.sleepTimeValue > 0:
                    if self.sleepTimer.is_alive():
                        self.sleepTimer.cancel()
                        self.sleepTimer = threading.Timer(self.sleepTimeValue, self.sleepAction)

                self.hideInfo()
                self.getControl(103).setVisible(False)
                self.newChannel = 0
                self.myEPG.doModal()
                self.getControl(103).setVisible(True)

                if self.channelThread.is_alive():
                    self.channelThread.unpause()

                self.startNotificationTimer()

                self.log('Current new channel value: ' + str(self.newChannel))
                if self.newChannel != 0:
                    self.setChannel(self.newChannel)

        elif action == ACTION_MOVE_UP or action == ACTION_PAGEUP:
            self.channelUp()
        elif action == ACTION_MOVE_DOWN or action == ACTION_PAGEDOWN:
            self.channelDown()
        elif action == ACTION_MOVE_LEFT:
            if self.showingInfo:
                self.infoOffset -= 1
                self.showInfo(10)
            else:
                xbmc.executebuiltin("Seek(" + str(self.seekBackward) + ")")

        elif action == ACTION_MOVE_RIGHT:
            if self.showingInfo:
                self.infoOffset += 1
                self.showInfo(10)
            else:
                xbmc.executebuiltin("Seek(" + str(self.seekForward) + ")")

        elif action in ACTION_PREVIOUS_MENU:
            if self.showingInfo:
                self.hideInfo()
            else:
                dlg = xbmcgui.Dialog()

                if self.sleepTimeValue > 0:
                    if self.sleepTimer.is_alive():
                        self.sleepTimer.cancel()
                        self.sleepTimer = threading.Timer(self.sleepTimeValue, self.sleepAction)

                if dlg.yesno(xbmc.getLocalizedString(13012), LANGUAGE(30031)):
                    self.end()
                    return  # Don't release the semaphore
                else:
                    self.startSleepTimer()

        elif action == ACTION_SHOW_INFO:
            if self.ignoreInfoAction:
                self.ignoreInfoAction = False
            else:
                if self.showingInfo:
                    self.hideInfo()

                    if xbmc.getCondVisibility('Player.ShowInfo'):
                        json_query = '{"jsonrpc": "2.0", "method": "Input.Info", "id": 1}'
                        self.ignoreInfoAction = True
                        xbmc.executeJSONRPC(json_query)

                else:
                    self.showInfo(10)
        elif action >= ACTION_NUMBER_0 and action <= ACTION_NUMBER_9:
            if self.inputChannel < 0:
                self.inputChannel = action - ACTION_NUMBER_0
            else:
                if self.inputChannel < 100:
                    self.inputChannel = self.inputChannel * 10 + action - ACTION_NUMBER_0

            self.showChannelLabel(self.inputChannel)
        elif action == ACTION_OSD:
            xbmc.executebuiltin("ActivateWindow(videoosd)")

        self.actionSemaphore.release()
        self.log('onAction return')

    # Reset the sleep timer
    def startSleepTimer(self):
        if self.sleepTimeValue == 0:
            return

        # Cancel the timer if it is still running
        if self.sleepTimer.is_alive():
            self.sleepTimer.cancel()
            self.sleepTimer = threading.Timer(self.sleepTimeValue, self.sleepAction)

        if self.Player.stopped is False:
            self.sleepTimer.name = "SleepTimer"
            self.sleepTimer.start()

    def startNotificationTimer(self, timertime=NOTIFICATION_CHECK_TIME):
        self.log("startNotificationTimer")

        if self.notificationTimer.is_alive():
            self.notificationTimer.cancel()

        self.notificationTimer = threading.Timer(timertime, self.notificationAction)

        if self.Player.stopped == False:
            self.notificationTimer.name = "NotificationTimer"
            self.notificationTimer.start()

    # This is called when the sleep timer expires
    def sleepAction(self):
        self.log("sleepAction")
        self.actionSemaphore.acquire()
        self.end()

    # Run rules for a channel       #todo: review usage of channelist method/ dupicate?
    def runActions(self, action, channelNumber, parameter):
        self.log("runActions " + str(action) + " on channel " + str(channelNumber))

        if channelNumber < 1:
            return

        self.runningActionChannel = channelNumber
        index = 0

        for rule in self.channels[channelNumber].ruleList:
            if rule.actions & action > 0:
                self.runningActionId = index
                parameter = rule.runAction(action, self, parameter)

            index += 1

        self.runningActionChannel = 0
        self.runningActionId = 0
        return parameter

    def notificationAction(self):
        self.log("notificationAction")
        docheck = False

        if self.showNextItem is False:
            return

        if self.Player.isPlaying():
            if self.notificationLastChannel != self.currentChannel:
                docheck = True
            else:
                if self.notificationLastShow != xbmc.PlayList(xbmc.PLAYLIST_MUSIC).getposition():
                    docheck = True
                else:
                    if self.notificationShowedNotif is False:
                        docheck = True

            if docheck is True:
                self.notificationLastChannel = self.currentChannel
                self.notificationLastShow = xbmc.PlayList(xbmc.PLAYLIST_MUSIC).getposition()
                self.notificationShowedNotif = False

                curChannel = self.channels[self.currentChannel]
                if self.hideShortItems:
                    # Don't show any notification if the current show is < 60 seconds
                    if curChannel.getItemDuration(self.notificationLastShow) < self.shortItemLength:
                        self.notificationShowedNotif = True

                timedif = curChannel.getItemDuration(self.notificationLastShow) - self.Player.getTime()

                if self.notificationShowedNotif is False and timedif < NOTIFICATION_TIME_BEFORE_END and timedif > NOTIFICATION_DISPLAY_TIME:
                    nextshow = curChannel.fixPlaylistIndex(self.notificationLastShow + 1)

                    if self.hideShortItems:                                 #todo: review for refactoring/ next block instead?
                        # Find the next show that is >= 60 seconds long
                        while nextshow != self.notificationLastShow:
                            if curChannel.getItemDuration(nextshow) >= self.shortItemLength:
                                break

                            nextshow = curChannel.fixPlaylistIndex(nextshow + 1)

                    xbmc.executebuiltin('Notification(%s, %s, %d, %s)' % (
                        LANGUAGE(30005), 
                        curChannel.getItemTitle(nextshow).replace(',', ''),
                        NOTIFICATION_DISPLAY_TIME * 1000,
                        ICON))
                    self.notificationShowedNotif = True

        self.startNotificationTimer()

    def playerTimerAction(self):
        self.playerTimer = threading.Timer(2.0, self.playerTimerAction)

        if self.Player.isPlaying():
            self.lastPlayTime = int(self.Player.getTime())
            self.lastPlaylistPosition = xbmc.PlayList(xbmc.PLAYLIST_MUSIC).getposition()
            self.notPlayingCount = 0
        else:
            self.notPlayingCount += 1
            self.log("Adding to notPlayingCount")

        if self.notPlayingCount >= 3:
            self.end()
            return

        if self.Player.stopped is False:
            self.playerTimer.name = "PlayerTimer"
            self.playerTimer.start()

    #todo: cleanup and end
    def end(self):
        self.log('end')
        # Prevent the player from setting the sleep timer
        self.Player.stopped = True
        curtime = time.time()
        self.isExiting = True
        updateDialog = xbmcgui.DialogProgressBG()
        updateDialog.create(ADDON_NAME, '')

        if self.isMaster and CHANNEL_SHARING:
            updateDialog.update(1, message='Exiting - Removing File Locks')
            GlobalFileLock.unlockFile('MasterLock')

        GlobalFileLock.close()

        #todo: refactor threads joining logic into one block of code
        try:
            if self.playerTimer is not None and self.playerTimer.is_alive():
                self.playerTimer.cancel()
                self.playerTimer.join()
        except:
            pass

        try:
            if self.Player is not None and self.Player.isPlaying():
                self.lastPlayTime = self.Player.getTime()
                self.lastPlaylistPosition = xbmc.PlayList(xbmc.PLAYLIST_MUSIC).getposition()
                self.Player.stop()
        except:
            pass

        updateDialog.update(2, message='Exiting - Stopping Threads')

        try:
            if self.channelLabelTimer is not None and self.channelLabelTimer.is_alive():
                self.channelLabelTimer.cancel()
                self.channelLabelTimer.join()
        except:
            pass

        updateDialog.update(3, message='Exiting - Stopping Threads')

        try:
            if self.notificationTimer.is_alive():
                self.notificationTimer.cancel()
                self.notificationTimer.join()
        except:
            pass

        updateDialog.update(4, message='Exiting - Stopping Threads')

        try:
            if self.infoTimer.is_alive():
                self.infoTimer.cancel()
                self.infoTimer.join()
        except:
            pass

        updateDialog.update(5, message='Exiting - Stopping Threads')

        try:
            if self.sleepTimeValue > 0:
                if self.sleepTimer.is_alive():
                    self.sleepTimer.cancel()
        except:
            pass

        updateDialog.update(6, message='Exiting - Stopping Threads')

        if self.channelThread.is_alive():
            for i in range(30):
                try:
                    self.channelThread.join(1.0)
                except:
                    pass

                if self.channelThread.is_alive() == False:
                    break

                updateDialog.update(6 + i, message='Exiting - Stopping Threads')

            if self.channelThread.is_alive():
                self.log("Problem joining channel thread", xbmc.LOGERROR)

        if self.isMaster:
            try:
                ADDON.setSetting('CurrentChannel', str(self.currentChannel))
            except:
                pass

            ADDON_SETTINGS.setSetting('LastExitTime', int(curtime))

        if self.timeStarted > 0 and self.isMaster:                      #todo: refactor this whole block, validcount and processing valid channels logic
            updateDialog.update(35, message='Exiting - Saving Settings')
            validChannels = {key:channel for key,channel in self.channels.items() if channel.isValid}

            if validChannels:
                progress = 1
                for i, curChannel in validChannels.items():
                    updateDialog.update(progress // len(validChannels) * 100)

                    if curChannel.mode & MODE_RESUME == 0:
                        timeValue = int(curtime - self.timeStarted + curChannel.totalTimePlayed)
                        ADDON_SETTINGS.Channels[i].time = timeValue
                    else:
                        tottime = 0
                        if i == self.currentChannel:
                            # Determine pltime...the time it at the current playlist position                            
                            self.log("position for current playlist is " + str(self.lastPlaylistPosition))
                            tottime =  sum(curChannel.getItemDuration(pos) for pos in range(self.lastPlaylistPosition)) + self.lastPlayTime
                        else:
                            tottime = sum(curChannel.getItemDuration(pos) for pos in range(curChannel.playlistPosition)) + curChannel.showTimeOffset            #todo: clean up

                        ADDON_SETTINGS.Channels[i].time = int(tottime)
                    progress += 1

                self.storeFiles()

        if ADDON.getSettingBool("ResetWatched"):
            updateDialog.update(100, message='Exiting - Resetting Watched Status')
            Reset = ResetWatched(validChannels)
            Reset.Resetter()

        xbmc.PlayList(xbmc.PLAYLIST_MUSIC).clear()
        xbmc.executebuiltin("PlayerControl(RepeatOff)")
        updateDialog.close()
        self.close()
