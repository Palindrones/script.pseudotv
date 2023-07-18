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

from copy import copy
import json
import xbmc
import xbmcvfs
import os
import traceback
from log import Log
from FileAccess import FileAccess
from xml.dom.minidom import parse, Document


class Settings_Legacy(Log):
    def __init__(self):
        from Globals import SETTINGS_LOC
        self.legacyfile = xbmcvfs.translatePath(os.path.join(SETTINGS_LOC, 'settings2.xml'))
        self.alwaysWrite = 1
        self.currentSettings = {}

    def loadSettings(self):
        self.log("Loading legacy settings from " + self.legacyfile)
        # self.currentSettings.clear()

        from FileAccess import FileLock, FileAccess
        if FileAccess.exists(self.legacyfile):
            try:
                fle = FileAccess.open(self.legacyfile, "r")
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
                self.currentSettings[name] = value

    def disableWriteOnSave(self):
        self.alwaysWrite = 0

    def getSetting(self, name, force=False):
        if force:
            self.loadSettings()

        result = self.currentSettings.get(name)

        if result is None:
            return self.realGetSetting(name)

        return result

    def realGetSetting(self, name):
        self.log("realGetSetting - %s" % name)

        try:
            from Globals import ADDON
            val = ADDON.getSetting(name)
            return val
        except:
            return ''

    def setSetting(self, name, value):
        self.currentSettings[name] = value
        if self.alwaysWrite == 1:  # todo: review need for constant writting
            self.writeSettings()

    def writeSettings(self):
        doc = Document()
        xml = doc.createElement('settings')
        doc.appendChild(xml)

        for name in sorted(self.currentSettings.keys()):
            element = doc.createElement('setting')
            element.setAttribute("id", name)
            element.setAttribute("value", self.currentSettings[name])
            xml.appendChild(element)

        try:
            fle = FileAccess.open(self.legacyfile, "w")
            fle.write(doc.toprettyxml())
            fle.close()
        except:
            self.log("Unable to write the file")
            self.log(traceback.format_exc(), xbmc.LOGERROR)
            fle.close()
            return


class ChannelSettings():
    def __init__(self, dict_=None):
        from Channel import ChannelType
        self.type: ChannelType = ChannelType.UNKNOWN
        self.rules = {}
        self.changed = False
        self.lastscheduled = 0
        self.SetResetTime = 0
        self.time = 0
        self._1 = ''
        self._2 = ''

        if dict_:
            dict_ = {'_%s' % k if k.isdigit() else k: v for k, v in dict_.items()}
            self.__dict__.update(dict_)
            if isinstance(self.type, int):
                self.type = ChannelType(self.type)
            else:
                self.type = ChannelType[self.type]

    def asChannelSettings(dict_):
        if 'type' not in dict_.keys():
            return dict_
        return ChannelSettings(dict_)


class ChannelTypeEncoder(json.JSONEncoder, Log):
    def default(self, obj):
        #from Rules import BaseRule
        if isinstance(obj, ChannelSettings):
            obj = copy(obj)  # note: manipulates the object's internal dict keys/values
            obj.type = obj.type.name
            # note: skip empty values and remove '_' prefix
            obj.__dict__ = {k.lstrip('_'): v for k, v in obj.__dict__.items() if v}
        # if isinstance(obj, BaseRule):
            #obj.id = obj.getName
        #    obj.__dict__ = { k:v for k,v in obj.__dict__.items() if v} #note: skip empty values
        return obj.__dict__


class Settings(Settings_Legacy):
    def __init__(self):
        from Globals import SETTINGS_LOC
        super().__init__()
        self.logfile = xbmcvfs.translatePath(os.path.join(SETTINGS_LOC, 'settings2.json'))
        self.rootSettings: dict = {'settings': {'Channels': {}}}
        self.currentSettings = self.rootSettings['settings']
        self.loaded = False

    def loadSettings(self):
        self.log("Loading settings2 from " + self.logfile)
        # self.currentSettings.clear()
        bJsonLoaded = False
        version = '0.0.0'
        if FileAccess.exists(self.logfile) and not self.loaded:
            try:
                fle = FileAccess.open(self.logfile, "r")
                self.rootSettings = json.load(fle, object_hook=ChannelSettings.asChannelSettings)
                self.currentSettings = self.rootSettings['settings']

                # change the channel dict keys to ints
                self.currentSettings['Channels'] = {
                    int(k): v for k, v in self.currentSettings['Channels'].items()}
                version = self.rootSettings['settings']['Version']
                bJsonLoaded = True
            except Exception as ex:
                self.log("Exception when reading settings: " + str(ex))
                self.log(traceback.format_exc(), xbmc.LOGERROR)
            finally:
                fle.close()

            # determine if legacy settings loading is needed
        if not bJsonLoaded or version < '2.6.0':
            self.load_legacy()
        self.loaded = True

    def load_legacy(self):
        # load old settings
        from Channel import Channel
        super().loadSettings()
        newChannelSettings = {}

        # convert to new format
        legacySettings = [[key, value]
                          for key, value in self.currentSettings.items() if 'channel_' in key.lower()]
        for name, value in legacySettings:
            _, chNumber, subName = name.split('_', 2)
            chNumber = int(chNumber)
            # change channeltype from int to enum.name
            if subName == 'type' and value.isdigit():
                value = Channel.ChannelType(int(value)).name

            ruleNumber = None
            if 'rule_' in subName:
                _, ruleNumber, subName = subName.split('_', 2)
                # value = Globals.ChannelType(int(value)).name  #todo: change rule id to name

            if 'rulecount' in subName:  # remove unneccesary
                self.currentSettings.pop(name)
                continue
            # change channel settings from flat string name to structure channel model
            if chNumber not in newChannelSettings.keys():
                newChannelSettings[chNumber] = {}
            if ruleNumber:
                if 'rules' not in newChannelSettings[chNumber]:
                    newChannelSettings[chNumber]['rules'] = {}
                if ruleNumber not in newChannelSettings[chNumber]['rules']:
                    newChannelSettings[chNumber]['rules'][ruleNumber] = {}
                newChannelSettings[chNumber]['rules'][ruleNumber][subName] = value
            else:
                newChannelSettings[chNumber][subName] = value
            self.currentSettings.pop(name)
        # assign to new structure
        self.currentSettings['Channels'] = {k: ChannelSettings(v) for k, v in newChannelSettings.items()}
        self.rootSettings['settings'] = self.currentSettings
        # update version
        from Globals import VERSION
        self.rootSettings['settings']['Version'] = VERSION

    @property
    def Channels(self) -> dict:
        return self.currentSettings['Channels']

    @Channels.setter
    def Channels(self, value):
        self.currentSettings['Channels'] = value

    def setChannelSettings(self, channel: int, setttings: ChannelSettings, update=True):
        """ if update and channel in self.currentSettings['Channels']:
            self.currentSettings['Channels'][channel].__dict__.update(setttings.__dict__)  #todo: review need to overwrite/over update            
        else: """
        self.currentSettings['Channels'][channel] = setttings

    def getChannelSettings(self, channel: int, force=False) -> ChannelSettings:
        if channel not in self.currentSettings['Channels'] and force:  # todo: review usage/need of force
            self.loadSettings()
        return self.currentSettings['Channels'].get(channel, ChannelSettings())

    def removeChannel(self, channel: int):
        self.currentSettings['Channels'].pop(channel, '')

    def MaxChannel(self) -> int:
        self.log('MaxChannel')
        maxChannels = max(self.currentSettings['Channels'].keys(), default=0)
        return maxChannels

    def ChannelCount(self) -> int:
        self.log('ChannelCount')
        return len(self.currentSettings['Channels'])

    def writeSettings(self):
        try:
            fle = FileAccess.open(self.logfile, "w")
            json.dump(self.rootSettings, fp=fle, indent=2, sort_keys=True, cls=ChannelTypeEncoder)
        except:
            self.log("Unable to write the file")
            self.log(traceback.format_exc(), xbmc.LOGERROR)
        finally:
            fle.close()
