#!/usr/bin/python
# coding: utf-8

import xbmc
import xbmcaddon

ADDON = xbmcaddon.Addon()
ADDON_ID = ADDON.getAddonInfo('id')
LANGUAGE = ADDON.getLocalizedString
ADDON_NAME = ADDON.getAddonInfo('name')
ICON = ADDON.getAddonInfo('icon')

timer_amounts = [0, 5, 10, 15, 20]

IDLE_TIME = timer_amounts[ADDON.getSettingInt("timer_amount")]
Msg = ADDON.getSettingBool('notify')
Enabled = ADDON.getSettingBool('enable')

def autostart():
    if Msg:
        xbmc.executebuiltin("Notification( %s, %s, %d, %s)" % (ADDON_NAME, LANGUAGE(30030), 4000, ICON))
    xbmc.Monitor().waitForAbort(IDLE_TIME)
    xbmc.executebuiltin("RunScript("+ADDON_ID+")")
    xbmc.log("AUTOSTART PTV: Service Started...")

if Enabled:
    autostart()