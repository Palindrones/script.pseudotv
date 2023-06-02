#!/usr/bin/python
# coding: utf-8

import Globals
import xbmc


class Log:
    def log(self, msg, level=xbmc.LOGDEBUG):
        Globals.log(self.__class__.__name__ + ': ' + msg, level)


class LogInfo:
    def log(self, msg, level=xbmc.LOGINFO):
        Globals.log(self.__class__.__name__ + ': ' + msg, level)
