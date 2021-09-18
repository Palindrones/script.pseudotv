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

import xbmc, xbmcaddon, xbmcvfs
import sys, re, os
import time, traceback
import Globals

from FileAccess import FileLock, FileAccess
from xml.dom.minidom import parse, parseString, Document

class Settings:
    currentSettings = {}

    def __init__(self):
        self.logfile = xbmcvfs.translatePath(os.path.join(Globals.SETTINGS_LOC, 'settings2.xml'))
        self.alwaysWrite = 1


    def loadSettings(self):
        self.log("Loading settings from " + self.logfile)
        #self.currentSettings.clear()

        if FileAccess.exists(self.logfile) and len(self.currentSettings) == 0:
            try:
                fle = FileAccess.open(self.logfile, "r")
                dom = parse(fle)
                settings = dom.getElementsByTagName('setting')
                fle.close()
            except:
                self.log("Exception when reading settings: ")
                self.log(traceback.format_exc(), xbmc.LOGERROR)
                fle.close()

            for setting in settings:
                name = setting.getAttribute("id")
                value = setting.getAttribute("value")

                if value:
                    self.currentSettings[name] = value

    def disableWriteOnSave(self):
        self.alwaysWrite = 0


    def log(self, msg, level = xbmc.LOGDEBUG):
        Globals.log('Settings: ' + msg, level)


    def getSetting(self, name, force = False):
        if force:
            self.loadSettings()

        result = self.currentSettings.get(name)

        if result is None:
            return self.realGetSetting(name)

        return result


    def realGetSetting(self, name):
        self.log("realGetSetting - %s" % name)

        try:
            val = Globals.ADDON.getSetting(name)
            return val
        except:
            return ''


    def setSetting(self, name, value):
        self.currentSettings[name] = value
        if self.alwaysWrite == 1:
            self.writeSettings()


    def writeSettings(self):
        doc = Document()
        xml = doc.createElement('settings')  
        doc.appendChild(xml) 

        for name in sorted(self.currentSettings.keys()):
            element = doc.createElement('setting')
            element.setAttribute("id", name)
            element.setAttribute("value",self.currentSettings[name])
            xml.appendChild(element) 
            
        try:
            fle = FileAccess.open(self.logfile, "w")
            fle.write(doc.toprettyxml())
            fle.close()
        except:
            self.log("Unable to write the file")
            self.log(traceback.format_exc(), xbmc.LOGERROR)
            fle.close()
            return

