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
import xbmc
import xbmcgui
import xbmcaddon
import xbmcvfs
import subprocess
import os
import time
import threading
import datetime
import traceback

from Globals import *
from FileAccess import FileAccess
from Overlay import TVOverlay
from log import Log


class EPGWindow(xbmcgui.WindowXMLDialog, Log):
    def __init__(self, *args, **kwargs):
        self.focusRow = 0
        self.focusIndex = 0
        self.focusTime = 0
        self.focusEndTime = 0
        self.shownTime = 0
        self.centerChannel = 0
        self.rowCount = 6
        self.channelButtons = [None] * self.rowCount
        self.buttonCache = []
        self.actionSemaphore = threading.BoundedSemaphore()
        self.lastActionTime = time.time()
        self.channelLogos = ''
        self.textcolor = "FFFFFFFF"
        self.focusedcolor = "FF7d7d7d"
        self.clockMode = 0
        self.textfont = "font13"
        self.MyOverlayWindow: Optional[TVOverlay] = None

        # Set media path.
        if os.path.exists(xbmcvfs.translatePath(os.path.join(CWD, 'resources', 'skins', xbmc.getSkinDir(), 'media'))):
            self.mediaPath = xbmcvfs.translatePath(os.path.join(
                CWD, 'resources', 'skins', xbmc.getSkinDir(), 'media' + '/'))
        else:
            self.mediaPath = xbmcvfs.translatePath(os.path.join(
                CWD, 'resources', 'skins', 'default', 'media' + '/'))

        self.log('Media Path is ' + self.mediaPath)

        # Use the given focus and non-focus textures if they exist.  Otherwise use the defaults.
        if xbmc.skinHasImage(self.mediaPath + BUTTON_FOCUS):
            self.textureButtonFocus = self.mediaPath + BUTTON_FOCUS
        else:
            self.textureButtonFocus = 'button-focus.png'

        if xbmc.skinHasImage(self.mediaPath + BUTTON_NO_FOCUS):
            self.textureButtonNoFocus = self.mediaPath + BUTTON_NO_FOCUS
        else:
            self.textureButtonNoFocus = 'button-nofocus.png'

        for i in range(self.rowCount):
            self.channelButtons[i] = []

        self.clockMode = ADDON_SETTINGS.getSetting("ClockMode")
        self.toRemove = []

    def onFocus(self, controlid):
        pass

    # set the time labels

    def setTimeLabels(self, thetime):
        self.log('setTimeLabels')
        now = datetime.datetime.fromtimestamp(thetime)
        self.getControl(104).setLabel(now.strftime('%A, %d %B %Y').lstrip("0").replace(" 0", " "))
        delta = datetime.timedelta(minutes=30)

        for i in range(3):
            if self.clockMode == "0":
                self.getControl(101 + i).setLabel(now.strftime("%I:%M %p").lstrip("0").replace(" 0", " "))
            else:
                self.getControl(101 + i).setLabel(now.strftime("%H:%M"))

            now = now + delta

        self.log('setTimeLabels return')

    def onInit(self):
        self.log('onInit')
        timex, timey = self.getControl(120).getPosition()
        timew = self.getControl(120).getWidth()
        timeh = self.getControl(120).getHeight()
        self.currentTimeBar = xbmcgui.ControlImage(timex, timey, timew, timeh, self.mediaPath + TIME_BAR)

        self.addControl(self.currentTimeBar)

        try:
            textcolor = int(self.getControl(100).getLabel(), 16)
            focusedcolor = int(self.getControl(100).getLabel2(), 16)
            self.textfont = self.getControl(105).getLabel()

            if textcolor > 0:
                self.textcolor = hex(textcolor)[2:]

            if focusedcolor > 0:
                self.focusedcolor = hex(focusedcolor)[2:]
        except:
            pass

        try:
            if self.setChannelButtons(time.time(), self.MyOverlayWindow.currentChannel) == False:
                self.log('Unable to add channel buttons')
                return

            curtime = time.time()
            self.focusIndex = -1
            basex, basey = self.getControl(113).getPosition()
            baseh = self.getControl(113).getHeight()
            basew = self.getControl(113).getWidth()

            self.log('curtime: ' + str(curtime))
            # set the button that corresponds to the currently playing show
            for i in range(len(self.channelButtons[2])):
                left, top = self.channelButtons[2][i].getPosition()
                width = self.channelButtons[2][i].getWidth()
                left = left - basex
                starttime = self.shownTime + (left / (basew / 5400.0))
                endtime = starttime + (width / (basew / 5400.0))
                self.log('starttime: ' + str(starttime) + ' | endtime: ' + str(endtime))

                if curtime >= starttime and curtime <= endtime:
                    self.log('setting focus time to : ' + str(int(time.time())))
                    self.focusIndex = i
                    self.setFocus(self.channelButtons[2][i])
                    self.focusTime = int(time.time())
                    self.focusEndTime = endtime
                    break

            # If nothing was highlighted, just select the first button
            if self.focusIndex == -1:
                self.focusIndex = 0
                self.setFocus(self.channelButtons[2][0])
                left, top = self.channelButtons[2][0].getPosition()
                width = self.channelButtons[2][0].getWidth()
                left = left - basex
                starttime = self.shownTime + (left / (basew / 5400.0))
                endtime = starttime + (width / (basew / 5400.0))
                self.focusTime = int(starttime + 30)
                self.focusEndTime = endtime

            self.focusRow = 2
            self.setShowInfo()
        except:
            self.log("Unknown EPG Initialization Exception", xbmc.LOGERROR)
            self.log(traceback.format_exc(), xbmc.LOGERROR)

            try:
                self.close()
            except:
                self.log("Error closing", xbmc.LOGERROR)

            self.MyOverlayWindow.sleepTimeValue = 1
            self.MyOverlayWindow.startSleepTimer()
            return

        self.log('onInit return')

    # setup all channel buttons for a given time

    def setChannelButtons(self, starttime, curchannel, singlerow=-1):
        self.log('setChannelButtons ' + str(starttime) + ', ' + str(curchannel))
        self.centerChannel = self.MyOverlayWindow.fixChannel(curchannel)
        # This is done twice to guarantee we go back 2 channels.  If the previous 2 channels
        # aren't valid, then doing a fix on curchannel - 2 may result in going back only
        # a single valid channel.
        curchannel = self.MyOverlayWindow.fixChannel(curchannel - 1, False)
        curchannel = self.MyOverlayWindow.fixChannel(curchannel - 1, False)
        starttime = self.roundToHalfHour(int(starttime))
        self.setTimeLabels(starttime)
        self.shownTime = starttime
        basex, basey = self.getControl(111).getPosition()
        basew = self.getControl(111).getWidth()
        tmpx, tmpy = self.getControl(110 + self.rowCount).getPosition()
        timex, timey = self.getControl(120).getPosition()
        timew = self.getControl(120).getWidth()
        timeh = self.getControl(120).getHeight()
        basecur = curchannel
        self.toRemove.append(self.currentTimeBar)
        EpgLogo = ADDON.getSettingBool('ShowEpgLogo')
        myadds = []

        for i in range(self.rowCount):
            if singlerow == -1 or singlerow == i:
                self.setButtons(starttime, basecur, i)
                myadds.extend(self.channelButtons[i])

            basecur = self.MyOverlayWindow.fixChannel(basecur + 1)

        basecur = curchannel

        for i in range(self.rowCount):
            self.getControl(301 + i).setLabel(self.MyOverlayWindow.channels[basecur].name)
            basecur = self.MyOverlayWindow.fixChannel(basecur + 1)

        for i in range(self.rowCount):
            try:
                self.getControl(311 + i).setLabel(str(curchannel))
            except:
                pass

            try:
                if EpgLogo:
                    self.getControl(321 + i).setImage(self.channelLogos +
                                                      ascii(self.MyOverlayWindow.channels[curchannel].name) + ".png")
                    if not FileAccess.exists(self.channelLogos + ascii(self.MyOverlayWindow.channels[curchannel].name) + ".png"):
                        self.getControl(321 + i).setImage(IMAGES_LOC + "Default.png")
            except:
                pass

            curchannel = self.MyOverlayWindow.fixChannel(curchannel + 1)

        if time.time() >= starttime and time.time() < starttime + 5400:
            dif = int((starttime + 5400 - time.time()))
            self.currentTimeBar.setPosition(
                int((basex + basew - (timew / 2)) - (dif * (basew / 5400.0))), timey)
        else:
            if time.time() < starttime:
                self.currentTimeBar.setPosition(basex, timey)
            else:
                self.currentTimeBar.setPosition(basex + basew - timew, timey)

        myadds.append(self.currentTimeBar)

        try:
            self.removeControls(self.toRemove)
        except:
            for cntrl in self.toRemove:
                try:
                    self.removeControl(cntrl)
                except:
                    pass

        self.addControls(myadds)
        self.toRemove = []
        self.log('setChannelButtons return')

    # round the given time down to the nearest half hour

    def roundToHalfHour(self, thetime):
        n = datetime.datetime.fromtimestamp(thetime)
        delta = datetime.timedelta(minutes=30)

        if n.minute > 29:
            n = n.replace(minute=30, second=0, microsecond=0)
        else:
            n = n.replace(minute=0, second=0, microsecond=0)

        return time.mktime(n.timetuple())

    # create the buttons for the specified channel in the given row

    def setButtons(self, starttime, channelNumber, row):
        self.log('setButtons ' + str(starttime) + ", " + str(channelNumber) + ", " + str(row))

        try:
            channelNumber = self.MyOverlayWindow.fixChannel(channelNumber)
            curchannel = self.MyOverlayWindow.channels[channelNumber]
            basex, basey = self.getControl(111 + row).getPosition()
            baseh = self.getControl(111 + row).getHeight()
            basew = self.getControl(111 + row).getWidth()

            if xbmc.Player().isPlaying() == False:
                self.log('No video is playing, not adding buttons')
                self.closeEPG()
                return False

            # Backup all of the buttons to an array
            self.toRemove.extend(self.channelButtons[row])
            del self.channelButtons[row][:]

            # if the channel is paused, then only 1 button needed
            if curchannel.isPaused:
                self.channelButtons[row].append(xbmcgui.ControlButton(basex, basey, basew, baseh, curchannel.getCurrentTitle() + " (paused)", focusTexture=self.textureButtonFocus,
                                                noFocusTexture=self.textureButtonNoFocus, alignment=4, font=self.textfont, textColor=self.textcolor, shadowColor='0xAA000000', focusedColor=self.focusedcolor))
            else:
                # Find the show that was running at the given time
                # Use the current time and show offset to calculate it
                # At timedif time, channelShowPosition was playing at channelTimes
                # The only way this isn't true is if the current channel is curchannel since
                # it could have been fast forwarded or rewinded (rewound)?
                if channelNumber == self.MyOverlayWindow.currentChannel:
                    playlistpos = xbmc.PlayList(xbmc.PLAYLIST_MUSIC).getposition()
                    videotime = xbmc.Player().getTime()
                    reftime = time.time()
                else:
                    playlistpos = curchannel.playlistPosition
                    videotime = curchannel.showTimeOffset
                    reftime = curchannel.lastAccessTime

                # normalize reftime to the beginning of the video
                reftime -= videotime

                while reftime > starttime:
                    playlistpos -= 1
                    # No need to check bounds on the playlistpos, the duration function makes sure it is correct
                    reftime -= curchannel.getItemDuration(playlistpos)

                while reftime + curchannel.getItemDuration(playlistpos) < starttime:
                    reftime += curchannel.getItemDuration(playlistpos)
                    playlistpos += 1

                # create a button for each show that runs in the next hour and a half
                endtime = starttime + 5400
                totaltime = 0
                totalloops = 0

                while reftime < endtime and totalloops < 1000:
                    xpos = int(basex + (totaltime * (basew / 5400.0)))
                    tmpdur = curchannel.getItemDuration(playlistpos)
                    shouldskip = False

                    # this should only happen the first time through this loop
                    # it shows the small portion of the show before the current one
                    if reftime < starttime:
                        tmpdur -= starttime - reftime
                        reftime = starttime

                        if tmpdur < 60 * 3:
                            shouldskip = True

                    # Don't show very short videos
                    if self.MyOverlayWindow.hideShortItems and shouldskip == False:
                        if curchannel.getItemDuration(playlistpos) < self.MyOverlayWindow.shortItemLength:
                            shouldskip = True
                            tmpdur = 0
                        else:
                            nextlen = curchannel.getItemDuration(playlistpos + 1)
                            prevlen = curchannel.getItemDuration(playlistpos - 1)

                            if nextlen < 60:
                                tmpdur += nextlen / 2

                            if prevlen < 60:
                                tmpdur += prevlen / 2

                    width = int((basew / 5400.0) * tmpdur)

                    if width < 30 and shouldskip == False:
                        width = 30
                        tmpdur = int(30.0 / (basew / 5400.0))

                    if width + xpos > basex + basew:
                        width = basex + basew - xpos

                    if shouldskip == False and width >= 30:
                        mylabel = curchannel.getItemTitle(playlistpos)
                        self.channelButtons[row].append(xbmcgui.ControlButton(xpos, basey, width, baseh, mylabel, focusTexture=self.textureButtonFocus, noFocusTexture=self.textureButtonNoFocus,
                                                        alignment=4, font=self.textfont, shadowColor='0xAA000000', textColor=self.textcolor, focusedColor=self.focusedcolor))

                    totaltime += tmpdur
                    reftime += tmpdur
                    playlistpos += 1
                    totalloops += 1

                if totalloops >= 1000:
                    self.log("Broken big loop, too many loops, reftime is " +
                             str(reftime) + ", endtime is " + str(endtime))

                # If there were no buttons added, show some default button
                if len(self.channelButtons[row]) == 0:
                    self.channelButtons[row].append(xbmcgui.ControlButton(basex, basey, basew, baseh, curchannel.name, focusTexture=self.textureButtonFocus,
                                                    noFocusTexture=self.textureButtonNoFocus, alignment=4, font=self.textfont, textColor=self.textcolor, shadowColor='0xAA000000', focusedColor=self.focusedcolor))
        except:
            self.log("Exception in setButtons", xbmc.LOGERROR)
            self.log(traceback.format_exc(), xbmc.LOGERROR)

        self.log('setButtons return')
        return True

    def onAction(self, act):
        self.log('onAction ' + str(act.getId()))

        if self.actionSemaphore.acquire(False) is False:
            self.log('Unable to get semaphore')
            return

        action = act.getId()

        try:
            if action in ACTION_PREVIOUS_MENU:
                self.closeEPG()
            elif action == ACTION_MOVE_DOWN:
                self.GoDown()
            elif action == ACTION_MOVE_UP:
                self.GoUp()
            elif action == ACTION_MOVE_LEFT:
                self.GoLeft()
            elif action == ACTION_MOVE_RIGHT:
                self.GoRight()
            elif action == ACTION_STOP:
                self.closeEPG()
            elif action == ACTION_SELECT_ITEM:
                lastaction = time.time() - self.lastActionTime

                if lastaction >= 2:
                    self.selectShow()
                    self.closeEPG()
                    self.lastActionTime = time.time()
        except:
            self.log("Unknown EPG Exception", xbmc.LOGERROR)
            self.log(traceback.format_exc(), xbmc.LOGERROR)

            try:
                self.close()
            except:
                self.log("Error closing", xbmc.LOGERROR)

            self.MyOverlayWindow.sleepTimeValue = 1
            self.MyOverlayWindow.startSleepTimer()
            return

        self.actionSemaphore.release()
        self.log('onAction return')

    def closeEPG(self):
        self.log('closeEPG')

        try:
            self.removeControl(self.currentTimeBar)
            self.MyOverlayWindow.startSleepTimer()
        except:
            pass

        self.close()

    def onControl(self, control):
        self.log('onControl')

    # Run when a show is selected, so close the epg and run the show
    def onClick(self, controlid):
        self.log('onClick')

        if self.actionSemaphore.acquire(False) is False:
            self.log('Unable to get semaphore')
            self.log('Unable to get semaphore', xbmc.LOGFATAL)
            return

        lastaction = time.time() - self.lastActionTime

        if lastaction >= 2:
            for i in range(self.rowCount):
                for x in range(len(self.channelButtons[i])):
                    mycontrol = 0
                    mycontrol = self.channelButtons[i][x].getId()

                    if controlid == mycontrol:
                        self.log('The values are equal for selected button and mycontrol')
                        self.focusRow = i
                        self.focusIndex = x
                        self.selectShow()
                        self.closeEPG()
                        self.lastActionTime = time.time()
                        self.actionSemaphore.release()
                        return

            self.log('onClick did not find button for :' + str(controlid))
            self.lastActionTime = time.time()
            self.closeEPG()

        self.actionSemaphore.release()
        self.log('onClick return')

    def GoDown(self):
        self.log('goDown')

        # change controls to display the proper junks
        if self.focusRow == self.rowCount - 1:
            self.setChannelButtons(self.shownTime, self.MyOverlayWindow.fixChannel(self.centerChannel + 1))
            self.focusRow = self.rowCount - 2

        self.setProperButton(self.focusRow + 1)
        self.log('goDown return')

    def GoUp(self):
        self.log('goUp')

        # same as godown
        # change controls to display the proper junks
        if self.focusRow == 0:
            self.setChannelButtons(self.shownTime, self.MyOverlayWindow.fixChannel(
                self.centerChannel - 1, False))
            self.focusRow = 1

        self.setProperButton(self.focusRow - 1)
        self.log('goUp return')

    def GoLeft(self):
        self.log('goLeft')
        basex, basey = self.getControl(111 + self.focusRow).getPosition()
        basew = self.getControl(111 + self.focusRow).getWidth()

        # change controls to display the proper junks
        if self.focusIndex == 0:
            left, top = self.channelButtons[self.focusRow][self.focusIndex].getPosition()
            width = self.channelButtons[self.focusRow][self.focusIndex].getWidth()
            left = left - basex
            starttime = self.shownTime + (left / (basew / 5400.0))
            self.setChannelButtons(self.shownTime - 1800, self.centerChannel)
            curbutidx = self.findButtonAtTime(self.focusRow, starttime + 30)

            if (curbutidx - 1) >= 0:
                self.focusIndex = curbutidx - 1
            else:
                self.focusIndex = 0
        else:
            self.focusIndex -= 1

        left, top = self.channelButtons[self.focusRow][self.focusIndex].getPosition()
        width = self.channelButtons[self.focusRow][self.focusIndex].getWidth()
        left = left - basex
        starttime = self.shownTime + (left / (basew / 5400.0))
        endtime = starttime + (width / (basew / 5400.0))
        self.setFocus(self.channelButtons[self.focusRow][self.focusIndex])
        self.setShowInfo()
        self.focusEndTime = endtime
        self.focusTime = starttime + 30
        self.log('goLeft return')

    def GoRight(self):
        self.log('goRight')
        basex, basey = self.getControl(111 + self.focusRow).getPosition()
        basew = self.getControl(111 + self.focusRow).getWidth()

        # change controls to display the proper junks
        if self.focusIndex == len(self.channelButtons[self.focusRow]) - 1:
            left, top = self.channelButtons[self.focusRow][self.focusIndex].getPosition()
            width = self.channelButtons[self.focusRow][self.focusIndex].getWidth()
            left = left - basex
            starttime = self.shownTime + (left / (basew / 5400.0))
            self.setChannelButtons(self.shownTime + 1800, self.centerChannel)
            curbutidx = self.findButtonAtTime(self.focusRow, starttime + 30)

            if (curbutidx + 1) < len(self.channelButtons[self.focusRow]):
                self.focusIndex = curbutidx + 1
            else:
                self.focusIndex = len(self.channelButtons[self.focusRow]) - 1
        else:
            self.focusIndex += 1

        left, top = self.channelButtons[self.focusRow][self.focusIndex].getPosition()
        width = self.channelButtons[self.focusRow][self.focusIndex].getWidth()
        left = left - basex
        starttime = self.shownTime + (left / (basew / 5400.0))
        endtime = starttime + (width / (basew / 5400.0))
        self.setFocus(self.channelButtons[self.focusRow][self.focusIndex])
        self.setShowInfo()
        self.focusEndTime = endtime
        self.focusTime = starttime + 30
        self.log('goRight return')

    def findButtonAtTime(self, row, selectedtime):
        self.log('findButtonAtTime ' + str(row))
        basex, basey = self.getControl(111 + row).getPosition()
        baseh = self.getControl(111 + row).getHeight()
        basew = self.getControl(111 + row).getWidth()

        for i in range(len(self.channelButtons[row])):
            left, top = self.channelButtons[row][i].getPosition()
            width = self.channelButtons[row][i].getWidth()
            left = left - basex
            starttime = self.shownTime + (left / (basew / 5400.0))
            endtime = starttime + (width / (basew / 5400.0))

            if selectedtime >= starttime and selectedtime <= endtime:
                return i

        return -1

    # based on the current focus row and index, find the appropriate button in
    # the new row to set focus to

    def setProperButton(self, newrow, resetfocustime=False):
        self.log('setProperButton ' + str(newrow))
        self.focusRow = newrow
        basex, basey = self.getControl(111 + newrow).getPosition()
        baseh = self.getControl(111 + newrow).getHeight()
        basew = self.getControl(111 + newrow).getWidth()

        for i in range(len(self.channelButtons[newrow])):
            left, top = self.channelButtons[newrow][i].getPosition()
            width = self.channelButtons[newrow][i].getWidth()
            left = left - basex
            starttime = self.shownTime + (left / (basew / 5400.0))
            endtime = starttime + (width / (basew / 5400.0))

            if self.focusTime >= starttime and self.focusTime <= endtime:
                self.focusIndex = i
                self.setFocus(self.channelButtons[newrow][i])
                self.setShowInfo()
                self.focusEndTime = endtime

                if resetfocustime:
                    self.focusTime = starttime + 30

                self.log('setProperButton found button return')
                return

        self.focusIndex = 0
        self.setFocus(self.channelButtons[newrow][0])
        left, top = self.channelButtons[newrow][0].getPosition()
        width = self.channelButtons[newrow][0].getWidth()
        left = left - basex
        starttime = self.shownTime + (left / (basew / 5400.0))
        endtime = starttime + (width / (basew / 5400.0))
        self.focusEndTime = endtime

        if resetfocustime:
            self.focusTime = starttime + 30

        self.setShowInfo()
        self.log('setProperButton return')

    def setShowInfo(self):
        self.log('setShowInfo')
        basex, basey = self.getControl(111 + self.focusRow).getPosition()
        baseh = self.getControl(111 + self.focusRow).getHeight()
        basew = self.getControl(111 + self.focusRow).getWidth()
        # use the selected time to set the video
        left, top = self.channelButtons[self.focusRow][self.focusIndex].getPosition()
        width = self.channelButtons[self.focusRow][self.focusIndex].getWidth()
        left = left - basex + (width / 2)
        starttime = self.shownTime + (left / (basew / 5400.0))
        chnoffset = self.focusRow - 2
        newchan = self.centerChannel

        while chnoffset != 0:
            if chnoffset > 0:
                newchan = self.MyOverlayWindow.fixChannel(newchan + 1, True)
                chnoffset -= 1
            else:
                newchan = self.MyOverlayWindow.fixChannel(newchan - 1, False)
                chnoffset += 1

        plpos = self.determinePlaylistPosAtTime(starttime, newchan)

        if plpos == -1:
            self.log('Unable to find the proper playlist to set from EPG')
            return

        newChannel = self.MyOverlayWindow.channels[newchan]
        self.getControl(500).setLabel(newChannel.getItemTitle(plpos))
        self.getControl(501).setLabel(newChannel.getItemEpisodeTitle(plpos))
        self.getControl(502).setText(newChannel.getItemDescription(plpos))
        self.getControl(503).setImage(self.channelLogos + ascii(newChannel.name) + '.png')
        if not FileAccess.exists(self.channelLogos + ascii(newChannel.name) + '.png'):
            self.getControl(503).setImage(IMAGES_LOC + 'Default.png')
        self.log('setShowInfo return')

    # using the currently selected button, play the proper shows
    def selectShow(self):
        self.log('selectShow')
        basex, basey = self.getControl(111 + self.focusRow).getPosition()
        baseh = self.getControl(111 + self.focusRow).getHeight()
        basew = self.getControl(111 + self.focusRow).getWidth()
        # use the selected time to set the video
        left, top = self.channelButtons[self.focusRow][self.focusIndex].getPosition()
        width = self.channelButtons[self.focusRow][self.focusIndex].getWidth()
        left = left - basex + (width / 2)
        starttime = self.shownTime + (left / (basew / 5400.0))
        chnoffset = self.focusRow - 2
        newchan = self.centerChannel

        while chnoffset != 0:
            if chnoffset > 0:
                newchan = self.MyOverlayWindow.fixChannel(newchan + 1, True)
                chnoffset -= 1
            else:
                newchan = self.MyOverlayWindow.fixChannel(newchan - 1, False)
                chnoffset += 1

        plpos = self.determinePlaylistPosAtTime(starttime, newchan)
        newChannel = self.MyOverlayWindow.channels[newchan]

        if plpos == -1:
            self.log('Unable to find the proper playlist to set from EPG', xbmc.LOGERROR)
            return

        timedif = (time.time() - newChannel.lastAccessTime)
        pos = newChannel.playlistPosition
        showoffset = newChannel.showTimeOffset

        # adjust the show and time offsets to properly position inside the playlist
        while showoffset + timedif > newChannel.getItemDuration(pos):
            timedif -= newChannel.getItemDuration(pos) - showoffset
            pos = newChannel.fixPlaylistIndex(pos + 1)
            showoffset = 0

        if self.MyOverlayWindow.currentChannel == newchan:
            if plpos == xbmc.PlayList(xbmc.PLAYLIST_MUSIC).getposition():
                self.log('selectShow return current show')
                return

        if pos != plpos:
            newChannel.setShowPosition(plpos)
            newChannel.setShowTime(0)
            newChannel.setAccessTime(time.time())

        self.MyOverlayWindow.newChannel = newchan
        self.log('selectShow return')

    def determinePlaylistPosAtTime(self, starttime, channelNumber):
        self.log('determinePlaylistPosAtTime ' + str(starttime) + ', ' + str(channelNumber))
        channelNumber = self.MyOverlayWindow.fixChannel(channelNumber)
        currentChannel = self.MyOverlayWindow.channels[channelNumber]

        # if the channel is paused, then it's just the current item
        if currentChannel.isPaused:
            self.log('determinePlaylistPosAtTime paused return')
            return currentChannel.playlistPosition
        else:
            # Find the show that was running at the given time
            # Use the current time and show offset to calculate it
            # At timedif time, channelShowPosition was playing at channelTimes
            # The only way this isn't true is if the current channel is curchannel since
            # it could have been fast forwarded or rewinded (rewound)?
            if channelNumber == self.MyOverlayWindow.currentChannel:
                playlistpos = xbmc.PlayList(xbmc.PLAYLIST_MUSIC).getposition()
                videotime = xbmc.Player().getTime()
                reftime = time.time()
            else:
                playlistpos = currentChannel.playlistPosition
                videotime = currentChannel.showTimeOffset
                reftime = currentChannel.lastAccessTime

            # normalize reftime to the beginning of the video
            reftime -= videotime

            self.log('reftime before updates: ' + str(reftime))
            while reftime > starttime:
                playlistpos -= 1
                reftime -= currentChannel.getItemDuration(playlistpos)

            while reftime + currentChannel.getItemDuration(playlistpos) < starttime:
                reftime += currentChannel.getItemDuration(playlistpos)
                playlistpos += 1

            self.log('determinePlaylistPosAtTime: reftime after loops: ' + str(reftime) +
                     ' | return ' + str(currentChannel.fixPlaylistIndex(playlistpos)))
            return currentChannel.fixPlaylistIndex(playlistpos)
