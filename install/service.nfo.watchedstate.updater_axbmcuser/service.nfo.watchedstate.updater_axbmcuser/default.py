'''
*  This work is licensed under the Creative Commons Attribution-NonCommercial-ShareAlike 4.0 International (CC BY-NC-SA 4.0) License.
*
*
*  To view a copy of this license, visit
*
*  English version: http://creativecommons.org/licenses/by-nc-sa/4.0/
*  German version:  http://creativecommons.org/licenses/by-nc-sa/4.0/deed.de
*
*  or send a letter to Creative Commons, 171 Second Street, Suite 300, San Francisco, California, 94105, USA.
'''


import xbmc
import xbmcvfs
import xbmcaddon
import socket
import json
import xml.etree.ElementTree as ET
from os import path


addon = xbmcaddon.Addon('service.nfo.watchedstate.updater_axbmcuser')
addon_name = addon.getAddonInfo('name')

delay = '4000'
logo = 'special://home/addons/service.nfo.watchedstate.updater_axbmcuser/icon.png'


class NFOWatchedstateUpdater():
    def __init__(self):
        self.methodDict = {"VideoLibrary.OnUpdate": self.VideoLibraryOnUpdate,
                          }

        self.XBMCIP = addon.getSetting('xbmcip')
        self.XBMCPORT = int(addon.getSetting('xbmcport'))
        
        self.s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        self.s.setblocking(1)
        xbmc.sleep(int(delay))
        try:
            self.s.connect((self.XBMCIP, self.XBMCPORT))
        except Exception, e:
            xbmc.executebuiltin('Notification(%s, Error: %s, %s, %s)' %(addon_name, str(e), delay, logo) )
            xbmc.sleep(int(delay))
            xbmc.executebuiltin('Notification(%s, Please check remote control settings, %s, %s)' %(addon_name, delay, logo) )
            xbmc.sleep(int(delay))
            #xbmc.executebuiltin('ActivateWindow(10018)')
            exit(0)
        

    def handleMsg(self, msg):
        jsonmsg = json.loads(msg)        
        method = jsonmsg['method']
        if method in self.methodDict:
            methodHandler = self.methodDict[method]
            methodHandler(jsonmsg)
            

    def listen(self):
        currentBuffer = []
        msg = ''
        depth = 0
        while not xbmc.abortRequested:
            chunk = self.s.recv(1)
            currentBuffer.append(chunk)
            if chunk == '{':
                depth += 1
            elif chunk == '}':
                depth -= 1
                if not depth:
                    msg = ''.join(currentBuffer)
                    self.handleMsg(msg)
                    currentBuffer = []
        self.s.close()


    def VideoLibraryOnUpdate(self, jsonmsg):        
        #xbmc.log(str(jsonmsg["params"]["data"]["item"]["id"]))
        #xbmc.log(str(jsonmsg["params"]["data"]["item"]["type"]))
        #xbmc.log(str(jsonmsg["params"]["data"]["playcount"]))
        
        #if (jsonmsg["params"]["data"]["item"].has_key("id")) and (jsonmsg["params"]["data"]["item"].has_key("type")) and (jsonmsg["params"]["data"].has_key("playcount")):
        
        try:
            if (("id" in jsonmsg["params"]["data"]["item"]) and ("type" in jsonmsg["params"]["data"]["item"]) and ("playcount" in jsonmsg["params"]["data"])):
                itemid = jsonmsg["params"]["data"]["item"]["id"]
                itemtype = jsonmsg["params"]["data"]["item"]["type"]
                itemplaycount = jsonmsg["params"]["data"]["playcount"]

                #xbmc.log(str(type(itemid)))
                #xbmc.log(str(type(itemtype)))
                #xbmc.log(str(type(itemplaycount)))

                if itemtype == u'movie':
                    msg = xbmc.executeJSONRPC('{"jsonrpc":"2.0","method":"VideoLibrary.GetMovieDetails","params":{"movieid":%d,"properties":["file"]},"id":1}' %(itemid) )
                    jsonmsg = json.loads(msg)

                    filepath = jsonmsg["result"]["moviedetails"]["file"]

                    self.updateNFO(filepath, itemplaycount)


                ##When a season is marked as un-/watched, all episodes are edited
                if itemtype == u'episode':
                    msg = xbmc.executeJSONRPC('{"jsonrpc":"2.0","method":"VideoLibrary.GetEpisodeDetails","params":{"episodeid":%s,"properties":["file"]},"id":1}' %(str(itemid)) )
                    jsonmsg = json.loads(msg)

                    filepath = jsonmsg["result"]["episodedetails"]["file"]

                    self.updateNFO(filepath, itemplaycount)


                #if itemtype == u'tvshow':
        except:
            msgfake = ""
        
    def updateNFO(self, filepath, playcount):
        filepath = filepath.replace(path.splitext(filepath)[1], '.nfo')

        if xbmcvfs.exists(filepath):
            sFile = xbmcvfs.File(filepath)
            currentBuffer = []
            msg = ''
            while True:
                buf = sFile.read(1024)
                currentBuffer.append(buf)
                if not buf:
                    msg = ''.join(currentBuffer)                    
                    break

            sFile.close()
            
            tree = ET.ElementTree(ET.fromstring(msg))
            root = tree.getroot()
            
            
            if addon.getSetting('changewatchedtag') == 'true':
                w = root.find('watched')
                if (w is None) and (addon.getSetting('createwatchedtag') == 'true'):
                    w = ET.SubElement(root, 'watched')
                if playcount > 0:
                    w.text = 'true'
                else:
                    w.text = 'false'
            
            
            p = root.find('playcount')
            if p is None:
                p = ET.SubElement(root, 'playcount')
            p.text = str(playcount)
            self.prettyPrintXML(root)
            
            
            msg = ET.tostring(root, encoding='UTF-8')

            if msg:
                dFile = xbmcvfs.File(filepath, 'w')
                dFile.write(msg) ##String msg or bytearray: bytearray(msg)
                dFile.close()

                if addon.getSetting('notification') == 'true':
                    xbmc.executebuiltin('Notification(%s, NFO updated, %s, %s)' %(addon_name, noti_duration, logo) )
            else:
                if addon.getSetting('notification') == 'true':
                    xbmc.executebuiltin('Notification(%s, Error occured, %s, %s)' %(addon_name, delay, logo) )

        else:
            if addon.getSetting('notification') == 'true':
                xbmc.executebuiltin('Notification(%s, File not found, %s, %s)' %(addon_name, delay, logo) )


    def prettyPrintXML(self, elem, level=0):
        i = '\n' + level * '   '
        if len(elem):
            if not elem.text or not elem.text.strip():
                elem.text = i + "  "
            if not elem.tail or not elem.tail.strip():
                elem.tail = i
            for elem in elem:
                self.prettyPrintXML(elem, level+1)
            if not elem.tail or not elem.tail.strip():
                elem.tail = i
        else:
            if level and (not elem.tail or not elem.tail.strip()):
                elem.tail = i


if __name__ == '__main__':
    WU = NFOWatchedstateUpdater()
    WU.listen()
    del WU
