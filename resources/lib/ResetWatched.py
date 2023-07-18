# This file is part of PseudoTV.  It resets the watched status (playcount and resume) for all files in all playlists
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
import xbmc
import threading
import traceback
import re
import json

from Globals import *
from Playlist import Playlist
from log import Log


class ResetWatched(Log):
    def __init__(self, channels: dict[int, Channel] = {}):
        self.channels: dict[int, Channel] = channels
        self.processingSemaphore = threading.BoundedSemaphore()

    def resetChannels(self):
        for channel in self.channels.values():
            self.resetPlaylist(channel.Playlist)

    def loadandResetPlaylist(self, filename, channel: int = None):
        self.log("Load Playlist - " + filename)
        self.processingSemaphore.acquire()

        playlist = Playlist(channel)
        try:
            playlist.load(filename)
        except:
            self.log("ERROR loading playlist: " + filename + xbmc.LOGERROR)
            self.processingSemaphore.release()
            return False

        return self.resetPlaylist(playlist)

    # todo: refactor logic, per playlist logic causes tvshows/movies in different channels to override/duplicate resettings
    #       merge, sort, select latest items and then reset once
    #       or add tracking  variable to playlistItems watched and only update these
    def resetPlaylist(self, playlist: Playlist) -> bool:
        self.log("Reset Playlist - " + str(playlist.channel or playlist.filename))
        self.processingSemaphore.acquire()

        for tmpitem in playlist.itemlist:
            ID = tmpitem.ID
            M3Ucount = tmpitem.playcount
            M3Uresume = tmpitem.resume
            M3Ulastplayed = tmpitem.lastplayed
            episodetitle = tmpitem.episodetitle
            self.log("Parsing index Count: " + str(M3Ucount) + " Resume: " +
                     str(M3Uresume) + "  lastplayed: " + M3Ulastplayed + " ID: " + str(ID))

            if ID:  # avoiding Directory channels or any other invalid
                if 'x' in episodetitle:
                    # episode

                    json_query = '{"jsonrpc": "2.0", "method": "VideoLibrary.GetEpisodeDetails", "params": {"episodeid": %d, "properties": ["lastplayed","playcount","resume"]}, "id": 1}' % ID
                    json_folder_detail = xbmc.executeJSONRPC(json_query)

                    # next two lines accounting for how JSON returns resume info; stripping it down to just get the position
                    json_folder_detail = json_folder_detail.replace('"resume":{', '')
                    json_folder_detail = re.sub(r',"total":.+?}', '', json_folder_detail)

                    try:
                        params = json.loads(json_folder_detail)
                        result = params['result']
                        details = result['episodedetails']
                        JSONcount = details.get('playcount')
                        JSONresume = details.get('position')
                        JSONlastplayed = details.get('lastplayed')

                        # if (JSONcount != 0) and (JSONresume !=0):

                        if (JSONcount != M3Ucount) or (JSONresume != M3Uresume) or (JSONlastplayed != M3Ulastplayed):
                            self.log("TV JSON playcount: " + str(JSONcount) + " resume: " +
                                     str(JSONresume) + " lastplayed: " + JSONlastplayed)
                            self.log("TV M3U playcount: " + str(M3Ucount) + " resume: " +
                                     str(M3Uresume) + " lastplayed: " + M3Ulastplayed)
                            self.log("TV Resetting: " + episodetitle)
                            response = xbmc.executeJSONRPC('{"jsonrpc": "2.0", "id": 1, "method": "VideoLibrary.SetEpisodeDetails", "params": {"episodeid" : %d, "lastplayed": "%s", "playcount": %d , "resume": {"position": %d}   }} ' % (
                                ID, M3Ulastplayed, M3Ucount, M3Uresume))
                            self.log("Response: " + response)
                    except:
                        self.log("Failed to reset Episode " + str(ID), xbmc.LOGWARNING)

                else:
                    # movie
                    json_query = '{"jsonrpc": "2.0", "method": "VideoLibrary.GetMovieDetails", "params": {"movieid": %d, "properties": ["lastplayed","playcount","resume"]}, "id": 1}' % ID
                    json_folder_detail = xbmc.executeJSONRPC(json_query)

                    # next two lines accounting for how JSON returns resume info; stripping it down to just get the position
                    json_folder_detail = json_folder_detail.replace('"resume":{', '')
                    json_folder_detail = re.sub(r',"total":.+?}', '', json_folder_detail)

                    try:
                        params = json.loads(json_folder_detail)
                        result = params['result']
                        details = result['moviedetails']
                        JSONcount = details.get('playcount')
                        JSONresume = details.get('position')
                        JSONlastplayed = details.get('lastplayed')

                        # if (JSONcount != 0) and (JSONresume !=0):

                        if (JSONcount != M3Ucount) or (JSONresume != M3Uresume) or (JSONlastplayed != M3Ulastplayed):
                            self.log("Movie JSON playcount: " + str(JSONcount) + " resume: " +
                                     str(JSONresume) + " lastplayed: " + JSONlastplayed)
                            self.log("Movie M3U playcount: " + str(M3Ucount) + " resume: " +
                                     str(M3Uresume) + " lastplayed: " + M3Ulastplayed)
                            self.log("Movie Resetting: %s - %d" % (tmpitem.title, ID))
                            response = xbmc.executeJSONRPC('{"jsonrpc": "2.0", "id": 1, "method": "VideoLibrary.SetMovieDetails", "params": {"movieid" : %d, "lastplayed": "%s", "playcount": %d , "resume": {"position": %d}   }} ' % (
                                ID, M3Ulastplayed, M3Ucount, M3Uresume))
                            self.log("Response: " + response)

                    except:
                        self.log("Failed to reset Movie " + str(ID), xbmc.LOGWARNING)
                        self.log("Failed to reset Movie: " + traceback.format_exc())

        self.processingSemaphore.release()

        if not playlist.itemlist:
            return False

        return True

    def Resetter(self):
        self.resetChannels()
