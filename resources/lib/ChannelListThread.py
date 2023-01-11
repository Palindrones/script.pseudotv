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

from typing import Optional
import xbmc, xbmcgui, xbmcaddon
import subprocess, os
import time, threading
import datetime
import sys, re
import random, traceback

from ChannelList import ChannelList
from Channel import Channel
from Globals import *

class ChannelListThread(threading.Thread):
    def __init__(self):
        from Overlay import TVOverlay

        threading.Thread.__init__(self)
        self.myOverlay: Optional[TVOverlay] = None
        sys.setcheckinterval(25)
        self.chanlist = ChannelList()
        self.paused = False
        self.fullUpdating = True


    def log(self, msg, level = xbmc.LOGINFO):
        log('ChannelListThread: ' + msg, level)


    def run(self):
        self.log("Starting")
        self.chanlist.exitThread = False
        self.chanlist.readConfig()
        self.chanlist.sleepTime = 0.1

        if self.myOverlay == None:
            self.log("Overlay not defined. Exiting.")
            return

        self.chanlist.myOverlay = self.myOverlay
        self.fullUpdating = (self.myOverlay.backgroundUpdating == 0)
        validchannels = sum(ch.isValid for ch in self.myOverlay.channels.values())

        for iChannel in self.myOverlay.channels:
            self.chanlist.channels[iChannel] = Channel()

        # Don't load invalid channels if minimum threading mode is on
        if self.fullUpdating and self.myOverlay.isMaster:
            if validchannels < self.chanlist.enteredChannelCount:
                xbmc.executebuiltin("Notification(%s, %s, %d, %s)" % (ADDON_NAME, LANGUAGE(30024), 4000, ICON))

            for iChannel, overlayChannel in self.myOverlay.channels.items():
                if overlayChannel.isValid == False:
                    while True:
                        if self.myOverlay.isExiting:
                            self.log("Closing thread")
                            return

                        xbmc.sleep(1000)

                        if self.paused == False:
                            break

                    self.chanlist.channels[iChannel].setAccessTime(overlayChannel.lastAccessTime)
                    try:
                        if self.chanlist.setupChannel(iChannel, True, True, False):
                            while self.paused:
                                if self.myOverlay.isExiting:
                                    self.log("IsExiting")
                                    return

                                xbmc.sleep(1000)

                            overlayChannel = self.myOverlay.channels[iChannel] = self.chanlist.channels[iChannel]

                            if overlayChannel.isValid:
                                xbmc.executebuiltin("Notification(%s, %s, %d, %s)" % (ADDON_NAME, xbmc.getLocalizedString(19029) + ' ' + str(iChannel) + ' ' + LANGUAGE(30025), 4000, ICON))
                    except:
                        self.log("Unknown Channel Creation Exception", xbmc.LOGERROR)
                        self.log(traceback.format_exc(), xbmc.LOGERROR)
                        return

        ADDON.setSetting('ForceChannelReset', 'false')
        self.chanlist.sleepTime = 0.3

        while True:
            for iChannel, iOverlayChannel in self.myOverlay.channels.items():
                modified = True

                while modified == True and iOverlayChannel.getTotalDuration() < PREP_CHANNEL_TIME and iOverlayChannel.Playlist.size() < 16288:
                    # If minimum updating is on, don't attempt to load invalid channels
                    if self.fullUpdating == False and iOverlayChannel.isValid == False and self.myOverlay.isMaster:
                        break

                    modified = False

                    if self.myOverlay.isExiting:
                        self.log("Closing thread")
                        return

                    xbmc.sleep(2000)
                    curtotal = iOverlayChannel.getTotalDuration()
                    curChannel = self.chanlist.channels[iChannel]

                    if self.myOverlay.isMaster:
                        if curtotal > 0:
                            # When appending, many of the channel variables aren't set, so copy them over.
                            # This needs to be done before setup since a rule may use one of the values.
                            # It also needs to be done after since one of them may have changed while being setup.
                            curChannel.playlistPosition = iOverlayChannel.playlistPosition
                            curChannel.showTimeOffset = iOverlayChannel.showTimeOffset
                            curChannel.lastAccessTime = iOverlayChannel.lastAccessTime
                            curChannel.totalTimePlayed = iOverlayChannel.totalTimePlayed
                            curChannel.isPaused = iOverlayChannel.isPaused
                            curChannel.mode = iOverlayChannel.mode
                            # Only allow appending valid channels, don't allow erasing them

                            try:
                                self.chanlist.setupChannel(iChannel, True, False, True)
                            except:
                                self.log("Unknown Channel Appending Exception", xbmc.LOGERROR)
                                self.log(traceback.format_exc(), xbmc.LOGERROR)
                                return

                            curChannel.playlistPosition = iOverlayChannel.playlistPosition
                            curChannel.showTimeOffset = iOverlayChannel.showTimeOffset
                            curChannel.lastAccessTime = iOverlayChannel.lastAccessTime
                            curChannel.totalTimePlayed = iOverlayChannel.totalTimePlayed
                            curChannel.isPaused = iOverlayChannel.isPaused
                            curChannel.mode = iOverlayChannel.mode
                        else:
                            try:
                                self.chanlist.setupChannel(iChannel, True, True, False)
                            except:
                                self.log("Unknown Channel Modification Exception", xbmc.LOGERROR)
                                self.log(traceback.format_exc(), xbmc.LOGERROR)
                                return
                    else:
                        try:
                            # We're not master, so no modifications...just try and load the channel
                            self.chanlist.setupChannel(iChannel, True, False, False)
                        except:
                            self.log("Unknown Channel Loading Exception", xbmc.LOGERROR)
                            self.log(traceback.format_exc(), xbmc.LOGERROR)
                            return

                    iOverlayChannel = self.myOverlay.channels[iChannel] = self.chanlist.channels[iChannel]

                    if self.myOverlay.isMaster:
                        ADDON_SETTINGS.setSetting('Channel_' + str(iChannel) + '_time', str(iOverlayChannel.totalTimePlayed))

                    if iOverlayChannel.getTotalDuration() > curtotal and self.myOverlay.isMaster:
                        modified = True

                    # A do-while loop for the paused state
                    while True:
                        if self.myOverlay.isExiting:
                            self.log("Closing thread")
                            return

                        xbmc.sleep(2000)

                        if self.paused == False:
                            break

                timeslept = 0

            if self.fullUpdating == False and self.myOverlay.isMaster:
                return

            # If we're master, wait 30 minutes in between checks.  If not, wait 5 minutes.
            while (timeslept < 1800 and self.myOverlay.isMaster == True) or (timeslept < 300 and self.myOverlay.isMaster == False):
                if self.myOverlay.isExiting:
                    self.log("IsExiting")
                    return

                xbmc.sleep(2000)
                timeslept += 2

        self.log("All channels up to date.  Exiting thread.")           #todo:? review


    def pause(self):
        self.paused = True
        self.chanlist.threadPaused = True


    def unpause(self):
        self.paused = False
        self.chanlist.threadPaused = False
