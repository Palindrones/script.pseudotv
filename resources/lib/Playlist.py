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

import os
import xbmc, xbmcvfs
import threading
import traceback

from xml.dom.minidom import *#parse, parseString
from Globals import ADDON, GEN_CHAN_LOC, LANGUAGE, MEDIA_LIMIT, MODE_ORDERAIRDATE, log
from FileAccess import FileAccess
from log import Log


class PlaylistItem:
    def __init__(self, duration: int = 0, title: str = '', description: str= '', ID: int= 0, filename: str = '',
                    episodetitle: str = '', playcount: int = 0, resume: float = 0, lastplayed: str= '' ) -> None:
        self.duration = duration       #secs
        self.filename = filename
        self.description = description
        self.title = title
        self.episodetitle = episodetitle
        self.playcount = playcount
        self.resume = resume
        self.ID = ID
        self.lastplayed = lastplayed    #datetime :str

        #extra info
        self.episode = 0
        self.season = 0

    @classmethod
    def fromString(cls, line: str, line2: str = None):
        pl = cls()
        if not line:
            raise ValueError('Invalid parameter value - None')      #failed to create item from given string values
        elif not pl.loadString(line, line2):
            raise ValueError('Failed to parse string value')      #failed to create item from given string values
        else:
            return pl

    def toString( self) -> str:             #todo: refactor to __ method ,         self.__repr__   self.__str__
        tmpstrR = str(self.duration) + ',' +  '//'.join([self.title, self.episodetitle, self.description])
        tmpstrR = tmpstrR[:1990]

        if self.ID:         #these value optional/only pad with default values if id is known
            tmpstrR+='//'+ '//'.join(str(item) for item in [self.playcount, self.resume, self.lastplayed, self.ID])

        tmpstrR += '\n' + self.filename.replace("\\\\", "\\")
        return tmpstrR

    def loadString(self, line: str = None, line2: str = None) -> bool:
        if not line:
            return False

        try:
            if line.count('\n'):
                line, line2, *_ = line.splitlines()

            line = line.rstrip().replace('#EXTINF:', '', 1)#  .removeprefix('#EXTINF:')
            line2 = line2.rstrip() if line2 else None
        except:            
            self.log(traceback.format_exc(), xbmc.LOGERROR)
            return False

        index = line.find(',')
        if index == -1:
            raise ValueError('Invalid PlaylistItem string format')

        self.duration = int(line[:index])
        line = line[index + 1:] + '//' * (7 - line.count('//'))  # trim and pad
        self.title, self.episodetitle, self.description, self.playcount, self.resume, self.lastplayed, self.ID, *_ = line.split('//', 7)        #todo: channelist.directoryplalist clean up description/refactor description capture logic/ this is broken
        if line2:
            self.filename = line2

        #adjust description from bad '//' chars in value overflowing to playcount value
        if self.playcount and not self.playcount.isdecimal():
            self.description += '//' + self.playcount

        self.ID = int(self.ID) if isinstance(self.ID, str) and self.ID.isdecimal() else 0
        self.playcount = int(self.playcount) if isinstance(self.playcount, str) and self.playcount.isdecimal() else 0 # = int(self.playcount or 0)
        self.resume = float(self.resume or 0)                                #this will fail on an invalid resume value

        return True


class Playlist(Log):
    def __init__(self, channel:int = None):
        self.itemlist: list[PlaylistItem] = []
        self.totalDuration = 0      #secs : int
        self.processingSemaphore = threading.BoundedSemaphore()
        self.filename = ''
        self.channel = channel

    def getduration(self, index):
        self.processingSemaphore.acquire()

        if index >= 0 and index < len(self.itemlist):
            dur = self.itemlist[index].duration
            self.processingSemaphore.release()
            return dur

        self.processingSemaphore.release()
        return 0

    def size(self):
        self.processingSemaphore.acquire()
        totsize = len(self.itemlist)
        self.processingSemaphore.release()
        return totsize

        """def getfilename(self, index):
        self.processingSemaphore.acquire()

        if index >= 0 and index < len(self.itemlist):
            fname = self.itemlist[index].filename
            self.processingSemaphore.release()
            return fname

        self.processingSemaphore.release()
        return ''

    def getdescription(self, index):
        self.processingSemaphore.acquire()

        if index >= 0 and index < len(self.itemlist):
            desc = self.itemlist[index].description
            self.processingSemaphore.release()
            return desc

        self.processingSemaphore.release()
        return ''

    def getepisodetitle(self, index):
        self.processingSemaphore.acquire()

        if index >= 0 and index < len(self.itemlist):
            epit = self.itemlist[index].episodetitle
            self.processingSemaphore.release()
            return epit

        self.processingSemaphore.release()
        return ''

    def getplaycount(self, index):
        self.processingSemaphore.acquire()

        if index >= 0 and index < len(self.itemlist):
            pcount = self.itemlist[index].playcount
            self.processingSemaphore.release()
            return pcount

        self.processingSemaphore.release()
        return ''

    def getTitle(self, index):
        self.processingSemaphore.acquire()

        if index >= 0 and index < len(self.itemlist):
            title = self.itemlist[index].title
            self.processingSemaphore.release()
            return title 

        self.processingSemaphore.release()
        return ''   """
        
    def __getitem__(self, key):
        self.processingSemaphore.acquire()

        if key >= 0 and key < len(self.itemlist):
            itemCopy = self.itemlist[key]
            self.processingSemaphore.release()
            return itemCopy

        self.processingSemaphore.release()
        return None

    def clear(self):
        del self.itemlist[:]
        self.totalDuration = 0

    def load(self, filename):
        self.log("load " + filename)
        self.filename = filename
        self.processingSemaphore.acquire()
        self.clear()

        try:
            fle = FileAccess.open(filename, 'r')
        except IOError:
            self.log('Unable to open the file: ' + filename)
            self.processingSemaphore.release()
            return False

        # load content
        try:
            lines = fle.readlines()
        except Exception as e:
            self.log("ERROR loading playlist: " + filename)
            self.log(traceback.format_exc(), xbmc.LOGERROR)
            return False
        finally:
            fle.close()

        # find and read the header
        lineIterator = iter(lines)
        realindex = next((line for line in lineIterator if line.startswith('#EXTM3U')), None)
        if not realindex:
            self.log('Unable to find playlist header for the file: ' + filename)
            self.processingSemaphore.release()
            return False

        # past the header, so get the info
        for line in lineIterator:
            if len(self.itemlist) > 16384:
                break

            if line.startswith('#EXTINF:'):
                try:
                    tmpitem = PlaylistItem.fromString(line.rstrip(), next(lineIterator, None))
                    if tmpitem:
                        self.itemlist.append(tmpitem)
                        self.totalDuration += tmpitem.duration
                except:
                    self.log('Failed to parse playlist item' + traceback.format_exc())

        self.processingSemaphore.release()

        if len(self.itemlist) == 0:
            return False

        return True


    def save(self, filename = None):
        self.log("save " + filename)
        self.filename = filename or self.filename
        try:
            fle = FileAccess.open(filename, 'w')
        except:
            self.log("save Unable to open the smart playlist", xbmc.LOGERROR)
            return
        header = "#EXTM3U\n"
        prefix = "#EXTINF:"
        try:
            fle.write(header)
            for item in self.itemlist:
                fle.write(prefix + item.toString() + "\n")
        except:
            self.log("Unable to save the smart playlist", xbmc.LOGERROR)
        finally:
            fle.close()

class SmartPlaylist:
    def __init__(self, filePath: str, load: bool = True) -> None:
        self.mediaLimit = MEDIA_LIMIT[ADDON.getSettingInt("MediaLimit")]
        self.filePath =  xbmcvfs.translatePath(filePath)
        self.rules: list[dict] = []
        self.name = ''
        self.type = ''
        self.order = "random"
        self.orderDirection = 'ascending'
        self.match = 'all'
        if load:
            self.load()

    def load(self):
        self.log('loading ' + self.filePath)
        try:
            fileStream = FileAccess.open(self.filePath, "r")
        except Exception as e:
            self.log(LANGUAGE(30034) + ' ' + self.filePath, xbmc.LOGERROR)
            self.log(traceback.format_exc())
            return

        # load xml document
        try:
            dom = parse(fileStream)
            plname = dom.getElementsByTagName('name')
            self.name = plname[0].childNodes[0].nodeValue
            pltype = dom.getElementsByTagName('smartplaylist')
            self.type = pltype[0].attributes['type'].value
            match = dom.getElementsByTagName('match')
            self.match = match[0].childNodes[0].nodeValue

            # rules         #todo: add support for muti values rules
            rules = dom.getElementsByTagName('rule')
            for rule in rules:
                attrs = rule.attributes 
                newRule = {'field': attrs['field'].value, 'operator': attrs['operator'].value}
                newRule['value'] =  rule.firstChild.nodeValue if rule.firstChild else None
                self.rules.append(newRule)

            #todo:review adding support for grouping
            plOrder = dom.getElementsByTagName('order')
            self.order = plOrder[0].childNodes[0].nodeValue
            self.orderDirection = plOrder[0].attributes['direction'].value

        except Exception as ex:
            self.log('Problem parsing playlist content ' +  self.filePath, xbmc.LOGERROR)
            self.log(traceback.format_exc())
            return
        finally:
            fileStream.close()

    def save(self):
        self.log('saving to ' + self.filePath)
        doc = Document()
        # header
        xml = doc.createElement('smartplaylist')
        xml.setAttribute('type', self.type)
        doc.appendChild(xml)

        nameElement = doc.createElement('name')
        nameElement.appendChild(doc.createTextNode(self.name))
        xml.appendChild(nameElement)

        matchElement = doc.createElement('match')
        matchElement.appendChild(doc.createTextNode(self.match))
        xml.appendChild(matchElement)
        # body
        # {'field':field, 'operator':operator,'value':value}
        for rule in self.rules:
            element = doc.createElement('rule')
            element.setAttribute("field", rule['field'])
            element.setAttribute("operator", rule['operator'])
            if rule['value']:
                element.appendChild(doc.createTextNode(rule['value'])) #todo: add support for multiple <value> nodes
            xml.appendChild(element)

        # footer
        if self.mediaLimit > 0:
            limitElement = doc.createElement('limit')
            limitElement.appendChild(doc.createTextNode(str(self.mediaLimit)))
            xml.appendChild(limitElement)

        orderElement = doc.createElement('order')
        orderElement.appendChild(doc.createTextNode(self.order))
        orderElement.setAttribute('direction', self.orderDirection)
        xml.appendChild(orderElement)

        try:
            fle = FileAccess.open(self.filePath, "w")
            # note: missing 'standalone' declaration
            doc.writexml(fle, addindent="\t", newl="\n", encoding='utf-8')
            # doc.writexml(fle, addindent="\t", newl="\n",encoding='utf-8', standalone=True) python >=3.9
        except Exception as ex:
            self.log('Problem saving Smartplaylist content ' +
                     self.filePath, xbmc.LOGERROR)
            raise ex
        finally:
            fle.close()

    @staticmethod
    def log(msg, level = xbmc.LOGDEBUG):
        log('SmartPlaylist: ' + msg, level)
        print(msg)##

    # Open the smart playlist and read the name out of it...this is the channel name
    @staticmethod
    def getSmartPlaylistName(filePath):
        log('getSmartPlaylistName')
        smartPL = SmartPlaylist(filePath)
        return smartPL.name

    @staticmethod
    def getSmartPlaylistType(filePath):
        log('getSmartPlaylistType')
        smartPL = SmartPlaylist(filePath)
        return smartPL.type

    @staticmethod
    def createNetworkPlaylist(network, name = None):
        flename = xbmcvfs.makeLegalFilename(GEN_CHAN_LOC + 'Network_' + network + '.xsp')

        smartPl = SmartPlaylist(flename, False)
        smartPl.name =  name or network
        smartPl.type = "episodes"

        smartPl.addRule("Studio", "is", network)
        smartPl.save()
        return smartPl

    @staticmethod
    def createShowPlaylist(show, orderSetting, name = None):
        order = 'episode' if orderSetting.isdecimal() and int(orderSetting) & MODE_ORDERAIRDATE  else "random"
        flename = xbmcvfs.makeLegalFilename(GEN_CHAN_LOC + 'Show_' + show + '_' + order + '.xsp')

        smartPl = SmartPlaylist(flename, False)
        smartPl.name = name or show
        smartPl.type = "episodes"
        smartPl.order = order

        smartPl.addRule("tvshow", "is", show)
        smartPl.save()
        return smartPl

    @staticmethod
    def createGenreMixedPlaylist(genre, name = None):
        flename = xbmcvfs.makeLegalFilename(GEN_CHAN_LOC + 'Mixed_' + genre + '.xsp')
        smartPl = SmartPlaylist(flename, False)
        smartPl.name = name or genre
        smartPl.type = "mixed"
        smartPl.match = 'one'

        epname = os.path.basename(SmartPlaylist.createGenrePlaylist('episodes', genre, genre + ' TV').filePath)
        moname = os.path.basename(SmartPlaylist.createGenrePlaylist('movies', genre, genre +' Movies').filePath)

        smartPl.addRule("playlist", "is", epname)
        smartPl.addRule("playlist", "is", moname)
        smartPl.save()
        return smartPl

    @staticmethod
    def createGenrePlaylist(pltype, genre, name):
        flename = xbmcvfs.makeLegalFilename(GEN_CHAN_LOC + pltype + '_' + genre + '.xsp')
        smartPl = SmartPlaylist(flename, False)
        smartPl.name = name
        smartPl.type = pltype

        smartPl.addRule("genre", "is", genre)
        lAlternativeChars = ['-','/']
        altenatives = [genre.replace(char," ") for char in lAlternativeChars if char in genre]
        for alt in altenatives:
            smartPl.addRule("genre", "is", alt)
            smartPl.match = 'one'
        smartPl.save()
        return smartPl

    @staticmethod
    def createStudioPlaylist(studio, name = None):
        flename = xbmcvfs.makeLegalFilename(GEN_CHAN_LOC + 'Studio_' + studio + '.xsp')
        smartPl = SmartPlaylist(flename, False)
        smartPl.name = name or studio
        smartPl.type = "movies"

        smartPl.addRule("Studio", "is", studio)
        smartPl.save()
        return smartPl

    def addRule(self, field, operator, value):
        self.rules.append({'field':field, 'operator':operator,'value':value})

    def validatePlaylistFileRule(self, setting1, dir_name):
        '''Validate that the 'playlist' rules have a valid(existing) playlist path or name value
        and copy the playlist file to the kodi Playlist directory'''

        self.log('validatePlaylistFileRule')
        try:
            updateLocalFile = False
            for rule in (rule for rule in self.rules if 'playlist' == rule['field']):
                playlistName = rule['value']
                specialPath = xbmcvfs.translatePath('special://profile/playlists/video/')
                #playlistName is full filepath
                if FileAccess.exists(playlistName):  
                    if specialPath not in playlistName:
                        FileAccess.copy(playlistName, specialPath + os.path.basename(playlistName))
                    rule['value'] = os.path.basename(playlistName)
                    updateLocalFile = True
                    self.log("validatePlaylistFileRule: found as fullpath : " + playlistName )

                #check relative path of (parent) channel playlist
                elif FileAccess.exists(os.path.join(os.path.dirname(setting1), playlistName)):
                    if specialPath not in setting1:
                        FileAccess.copy(os.path.join(os.path.dirname(setting1), playlistName), specialPath + playlistName)
                    self.log("validatePlaylistFileRule: found as RelativePath : " + playlistName )

                elif FileAccess.exists(specialPath + playlistName): #check local directory
                    self.log("validatePlaylistFileRule: found in special Playlist videos: " + playlistName )
                    continue

                else:
                    self.log("validatePlaylistFileRule Problems locating playlist rule file " + playlistName)
                #todo: add  smart playlist name checking  logic against xbmc lib /refactor return value once done
                #todo: add  smart playlist file valid format check(load file)                    

            #update playlist value to local name (modify the curernt playlist(local copy))
            if updateLocalFile : 
                self.log("validatePlaylistFileRule: updating local copy's playlist rule paths: " + dir_name )
                self.filePath = xbmcvfs.translatePath(dir_name)
                self.save()
                """ try:
                except Exception as e:
                    self.log('validatePlaylistFileRule Problem updating local Playlist File ' + dir_name + '\n exception:' + str(e), xbmc.LOGERROR) """

        except Exception as e:
            self.log('validatePlaylistFileRule Problem looping rules ' + setting1 + '\n exception:' + str(e), xbmc.LOGERROR)
            return False

        self.log("validatePlaylistFileRule returning")
        return True

