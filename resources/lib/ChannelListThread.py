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
from typing import Optional
import xbmc
import threading
import traceback
import copy

from ChannelList import ChannelList
from Globals import *
from log import Log


class ChannelListThread(threading.Thread, Log):
    def __init__(self, overlay):
        threading.Thread.__init__(self)
        self.myOverlay: Optional[TVOverlay] = overlay
        # sys.setswitchinterval(interval)     #sys.setcheckinterval(25) //deprecated  python >=3.2
        self.chanlist = ChannelList()
        self.paused = False
        self.fullUpdating = True

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
        validChannels = [chPair for chPair in self.myOverlay.channels.items() if chPair[1].isValid]
        invalidChannels = [chPair for chPair in self.myOverlay.channels.items() if not chPair[1].isValid]
        validchannelCount = len(validChannels)

        # setup invalid channels if Full Background Updating (once)
        if self.fullUpdating and self.myOverlay.isMaster:
            if validchannelCount < self.chanlist.enteredChannelCount:
                xbmc.executebuiltin("Notification(%s, %s, %d, %s)" %
                                    (ADDON_NAME, LANGUAGE(30024), 4000, ICON))

            for iChannel, overlayChannel in invalidChannels:
                if self._pauseOrWait(1, not self.fullUpdating):
                    return

                self.chanlist.channels[iChannel] = copy.copy(overlayChannel)
                try:
                    if self.chanlist.setupChannel(iChannel, True, True, False):
                        # if self._onPause(): return
                        overlayChannel = self.myOverlay.channels[iChannel] = self.chanlist.channels[iChannel]
                        if overlayChannel.isValid:
                            msg = xbmc.getLocalizedString(19029) + ' ' + str(iChannel) + ' ' + LANGUAGE(30025)
                            msg = "Notification(%s, %s, %d, %s)" % (ADDON_NAME, msg, 4000, ICON)
                            xbmc.executebuiltin(msg)
                except:
                    self.log("Unknown Channel Creation Exception", xbmc.LOGERROR)
                    self.log(traceback.format_exc(), xbmc.LOGERROR)
                    return

        ADDON.setSettingBool('ForceChannelReset', False)
        self.chanlist.sleepTime = 0.3
        sleepLimit = 1800 if self.myOverlay.isMaster else 300
        while not self.myOverlay.isExiting:
            processChannels = [copy.copy(chPair) for chPair in self.myOverlay.channels.items(
            ) if chPair[1].isValid or self.fullUpdating]
            for iChannel, iOverlayChannel in processChannels:
                if self._pauseOrWait(2, not self.fullUpdating):
                    return

                self.chanlist.channels[iChannel] = iOverlayChannel
                curtotal = iOverlayChannel.getTotalDuration()
                bNewList = self.myOverlay.isMaster and not curtotal
                bAppend = self.myOverlay.isMaster and curtotal
                try:
                    self.chanlist.setupChannel(iChannel, True, bNewList, bAppend)
                except:
                    self.log("Unknown Channel Loading Exception", xbmc.LOGERROR)
                    self.log(traceback.format_exc(), xbmc.LOGERROR)
                    return

                iOverlayChannel = self.myOverlay.channels[iChannel] = self.chanlist.channels[iChannel]

                if self.myOverlay.isMaster:
                    ADDON_SETTINGS.Channels[iChannel].time = iOverlayChannel.totalTimePlayed

            if self.fullUpdating == False and self.myOverlay.isMaster:  # note: run logic once if minimum bg
                break

            # If we're master, wait 30 minutes in between checks.  If not, wait 5 minutes.
            if self._pauseOrWait(sleepLimit, True):
                return

        self.log("All channels up to date.  Exiting thread.")

    def pause(self):
        self.paused = True
        self.chanlist.threadPaused = True

    def unpause(self):
        self.paused = False
        self.chanlist.threadPaused = False

    def _pauseOrWait(self, timeout=1, sleep=False):
        timeSegmet = 0
        monitor = xbmc.Monitor()
        while timeSegmet < timeout and (self.paused or sleep):
            if self.myOverlay.isExiting or monitor.waitForAbort(1):
                self.log("Closing thread")
                return True
            timeSegmet += 1
        return False
