#!/usr/bin/python
# coding: utf-8

import xbmc


class Log:
    def log(self, msg, level=xbmc.LOGDEBUG):
        import Globals
        Globals.log(self.__class__.__name__ + ': ' + msg, level)


class LogInfo:

    def log(self, msg, level=xbmc.LOGINFO):
        import Globals
        Globals.log(self.__class__.__name__ + ': ' + msg, level)
        print(self.__class__.__name__ + ':  %(funcName)s' + msg, level)
