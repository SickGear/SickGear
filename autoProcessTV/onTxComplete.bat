@ECHO OFF
GOTO :main
*******************************************************************************

onTxComplete.bat v1.1 for SickGear

  Script to copy select files to a location for SickGear to post process.

  This is used with the 'Move' post process episode method
  so that seeding files are not post processed over and over.

*******************************************************************************

Supported clients
-----------------
* Deluge clients 1.3.15 and newer clients
* qBittorrent 4.13 and newer clients
* Transmission 2.84 and newer clients
* uTorrent 2.2.1

Supported OS
------------
* Windows 10, 8, 7, Vista


How this works
--------------
Completed downloads are copied from a seeding location to an isolated location.
SG will 'Move' processed content from isolation to the final show location.

The four parameters;
param1 = Isolation path where to copy completed downloads for SG to process.
         This value *must* ..
         1) be different to the path where the client saves completed downloads
         2) be configured in SG (see later, step a)
         This path should be created on first run, if not, create it yourself.

param2 = This filter value is compared with either a client set label, or the
         tail of the path where the client downloaded seeding file is located.
         Matching downloads are copied into isolation.

param3 = Client set downloaded item category or label (e.g. "%L")

param4 = Client set downloaded item content path (e.g. "%F", "%D\%F" etc)

Token values for params 3 and 4 are found documented in the download client or
at the client website. Other clients may be able to replace param3 and param4
to fit (see examples).


To set up SickGear
------------------
a) Set /config/postProcessing/Post Processing -> "Completed TV downloads"
   .. to match param1

b) Set /config/postProcessing/Post Processing -> "Process episode method"
   .. to 'Move'

c) Enable /config/postProcessing/Post Processing -> "Scan and post process"

d) Enable /config/postProcessing/Post Processing -> "Postpone post processing"

e) Set /config/search/Torrent Results -> "Set torrent label/category"
   If using "Black hole" method or if there is no label field, then you must use
   client auto labeller or a torrent completed save path that ends with param2,
   for Transmission, see note(2) in that section below.


To set up the download client
-----------------------------

For Deluge
----------
Deluge clients call scripts with fixed params that prevent passing params,
rename onTxComplete.sample.cfg as onTxComplete.cfg and edit parameters there.

A Deluge label is used to isolate SG downloads from everything else.

1) Enable the "Label" plugin

2) Enable the "Execute" plugin

3) In the "Execute" plugin settings /Add Command/Event/Torrent Complete
   set command to ... [script dir]\onTxComplete.bat

4) Add the label set in step (e) to Deluge, right click the label and select
   "Label Options"/Location/Move completed to/Other/ .. choose a folder created
   where its name is identical to this label e.g. [path]\[label], (F:\Files\SG)

Reference: http://dev.deluge-torrent.org/wiki/Plugins/Execute


For qBittorrent
---------------
The above four parameters are used to configure and run the script.

Use one cmd from below replacing "[script dir]" with the path to this script

Set Options/Downloads/Run an external program on torrent completion

.. to run in windowless mode (the normal run mode used)
   cmd /c start "" /B [script dir]\onTxComplete.bat "F:\sg_pp" "SG" "%L" "%F"

OR ..
.. to run in console window mode (test mode to see console output)
   cmd /c start "" /min [script dir]\onTxComplete.bat "F:\sg_pp" "SG" "%L" "%F"


For Transmission
----------------
Transmission clients call scripts with fixed params that prevent passing params,
rename onTxComplete.sample.cfg as onTxComplete.cfg and edit parameters there.

Transmission does not contain labels, instead, the set path(2) is compared
to the config file param2 value to isolate SG downloads from everything else.

1) Edit/Preferences/Downloading/Call script when torrent is completed
   ... Navigate to this script location and select it

2) Follow "To set up SickGear" instruction but at step (e),
   set "Downloaded files location" to a created folder with name ending in the
   config file value of param2 e.g. [path]\[param2]

Reference: https://web.archive.org/web/20171009055508/https://trac.transmissionbt.com/wiki/Scripts#OnTorrentCompletion


For uTorrent
------------
The above four parameters are used to configure and run the script.

Use one cmd below replacing "[script dir]" with the path to this script

1) Set Preferences/Advanced/Run program/Run this program when a torrent finishes
   cmd /c start "" /B [script dir]\onTxComplete.bat "F:\sg_pp" "SG" "%L" "%D\%F"

It is advised to not use the uTorrent "Move completed downloads" feature because
it runs scripts before move actions complete, bad. Consider switching clients.

Reference: https://stackoverflow.com/a/29071224

:main
rem ***************************************************************************
rem Set 1 to enable test mode output (default: blank)
SET testmode=
SET keeptmp=
rem ***************************************************************************
chcp 65001 >NUL 2>NUL
SETLOCAL
SETLOCAL ENABLEEXTENSIONS
SETLOCAL ENABLEDELAYEDEXPANSION

rem Get install dir stripped of trailing slash
SET "install_dir=%~dp0"

IF "" NEQ "%~4" (

  rem Use the four input parameters
  rem This also strips quotes used to safely pass values containing spaces
  SET "sg_path=%~1"
  SET "sg_label=%~2"
  SET "client_label=%~3"
  SET "content_path=%~4"
  IF "1" NEQ "!testmode!" IF "" NEQ "%~5" SET "testmode=1"
  SET "check_label_path_tail="

) ELSE (

  rem Process config file
  SET "cfgfile=!install_dir!onTxComplete.cfg"
  FOR /F "eol=; tokens=1,2 delims==" %%a IN (!cfgfile!) DO (
    SET "%%a=%%b"
    CALL:Log "Config ... %%a = %%b"
  )

  SET "nullvar="
  IF NOT DEFINED param1 SET "nullvar=1"
  IF NOT DEFINED param2 SET "nullvar=1"
  IF DEFINED nullvar (
    CALL:Log "Error: Issue while reading file !cfgfile!" "force"
    GOTO:exit
  )
  SET "sg_path=!param1!"
  SET "sg_label=!param2!"

  rem Attempt to read Transmission environment variables
  SET "client_name=%TR_TORRENT_NAME%"
  SET "client_path=%TR_TORRENT_DIR%"

  SET "nullvar="
  IF "" == "!client_name!" SET "nullvar=1"
  IF "" == "!client_path!" SET "nullvar=1"

  IF DEFINED nullvar (

    rem With no Transmission vars, attempt to read input parameters from Deluge
    rem Deluge sends id, name, and path
    IF "" == "%~3" (

      CALL:Log "Error: not enough input params, read comments in %0 for usage" "force"
      GOTO :exit

    )

    rem Deluge input parameters (i.e. "TorrentID" "Torrent Name" "Torrent Path")
    rem This also strips quotes used to safely pass values containing spaces
    SET "client_name=%~2"
    SET "client_path=%~3"

  )

  SET "content_path=!client_path!\!client_name!"
  SET "check_label_path_tail=1"
)


rem Replace any double slashes in path with single slash
SET "sg_path=!sg_path:\\=\!"
SET "content_path=!content_path:\\=\!"

rem Remove long path switch for most compatibility, newer OSes may omit this
IF "\?\" == "!sg_path:~0,3!" SET "sg_path=!sg_path:~3!"
IF "\?\" == "!content_path:~0,3!" SET "content_path=!content_path:~3!"

rem Remove any trailing slashes from paths
IF "\" == "!sg_path:~-1!" SET "sg_path=!sg_path:~0,-1!"
IF "\" == "!content_path:~-1!" SET "content_path=!content_path:~0,-1!"
IF "\" == "!client_path:~-1!" SET "client_path=!client_path:~0,-1!"


IF DEFINED check_label_path_tail (

  rem Enable the copy action if path ends with user defined label

  SET "client_label=!sg_label!"

:loop -- label strlen
  IF NOT "" == "!sg_label:~%len%!" SET /A len+=1 & GOTO :loop
  SET /A len+=1

  IF "\!sg_label!" NEQ "!client_path:~-%len%!" SET "client_label=skip copy"

)


rem Create ".!sync" filename
SET "syncext=^!sync"
SET "basefile=!sg_path!\copying"
SET "syncfile=!basefile!.!syncext!" & SET "files=!basefile!.files.txt" & SET "tmp=!basefile!.tmp"
SET num=2
:loopnum
IF EXIST "!syncfile!" (
  SET "syncfile=!basefile!-!num!.!syncext!" & SET "files=!basefile!-!num!.files.txt" & SET "tmp=!basefile!-!num!.tmp"
  SET /A num+=1 & GOTO :loopnum
)

IF "1" == "!testmode!" CALL:Log "Running in ***test mode*** - files will not be copied"
CALL:Log "**** cmd = ""%~f0"""
CALL:Log "  param1 = ""!sg_path!"""
CALL:Log "  param2 = ""!sg_label!"""
CALL:Log "  param3 = ""!client_label!"""
CALL:Log "  param4 = ""!content_path!"""
CALL:Log "syncfile = ""!syncfile!"""


CALL:StartsWith "!client_label!" "!sg_label!" && (

  IF NOT EXIST "!sg_path!" MKDIR "!sg_path!"

  IF EXIST "!sg_path!" (

    rem Determine file/folder as these need to be handled differently
    FOR %%f IN ("!content_path!") DO SET attr=%%~af & SET attr=!attr:~0,1!ir
    IF /I "dir" == "!attr!" (

      rem Create a file to prevent SG premature post processing (ref: step (d)) ..
      ECHO Copying folder "!content_path!" to "!sg_path!">"!syncfile!"

      PUSHD "!content_path!"

      rem Copy from; `parent/` to `{pp}/parent/` and `parent/.../child/` to `{pp}/parent/child/`
      FOR %%f IN ("!content_path!.") DO SET "parent=\%%~nxf"

      rem Sort by largest to smallest filesize for copy
      SET "delim=	"
      FORFILES /P "!content_path!" /S /C "CMD /C IF FALSE == @isdir ECHO @fsize!delim!@relpath!delim!@file" > "!files!"
      (
        FOR /F "tokens=1,2* delims=	" %%a IN ('TYPE "!files!"') DO (
          SET "size=...............%%a"
          SET "relpath=%%b"
          ECHO !size:~-15!!delim!!relpath:%%~c=!!delim!%%c
        )
      )>"!tmp!"
      (
        FOR /F "tokens=1* delims=.	" %%a IN ('SORT /R "!tmp!"') DO ECHO %%b
      )>"!files!"
      IF "1" NEQ "!keeptmp!" IF EXIST "!tmp!" DEL "!tmp!"

      FOR /F "tokens=1* delims=	" %%a IN ('TYPE "!files!"') DO (
        rem Copy
        SET "child="
        SET "relpath=%%~a"
        IF ".\" NEQ "!relpath!" FOR %%f IN ("!relpath:~0,-1!.") DO SET "child=\%%~nxf"
        SET "filename=%%~b"
        SET "dstdir=!sg_path!!parent!!child!"
        SET "dstfile=!dstdir!\!filename!"
        SET "srcfile=!relpath!!filename!"

        IF "1" == "!testmode!" (

          IF NOT EXIST "!dstdir!" CALL:Log "MKDIR ""!dstdir!"""
          IF NOT EXIST "!dstfile!" ( CALL:Log "XCOPY ""!srcfile!"" ""!dstfile!*"" /H /Y /J >NUL 2>NUL"
            ) ELSE ( CALL:Log "Skipping, file exists ""!dstfile!""" )

        ) ELSE (

          IF NOT EXIST "!dstdir!" MKDIR "!dstdir!"
          IF NOT EXIST "!dstfile!" XCOPY "!srcfile!" "!dstfile!*" /H /Y /J >NUL 2>NUL

        )

      )

      IF "1" NEQ "!keeptmp!" IF EXIST "!files!" DEL "!files!"
      IF "1" NEQ "!testmode!" IF EXIST "!syncfile!" DEL "!syncfile!"
      POPD

    ) ELSE (

      rem Create a file to prevent SG premature post processing (ref: step (d)) ..
      ECHO Copying file "!content_path!" to "!sg_path!">"!syncfile!"

      IF "1" == "!testmode!" (

        CALL:Log "COPY ""!content_path!"" ""!sg_path!\"" /Y"

      ) ELSE (

        COPY "!content_path!" "!sg_path!\" /Y >NUL 2>NUL
        IF EXIST "!syncfile!" DEL "!syncfile!"

      )

    )

  )

)
GOTO :exit

rem ****************
rem Helper functions
rem ****************
:StartsWith text string -- Test if text starts with string
SETLOCAL
SET "txt=%~1"
SET "str=%~2"
IF DEFINED str CALL SET "s=%str%%%txt:*%str%=%%"
IF /I "%txt%" NEQ "%s%" SET=2>NUL
EXIT /B

:Log text --  Append text to logfile, and output text to stdio if testmode is "1"
SETLOCAL
SET "logfile=!install_dir!onTxComplete.log"
SET "txt=%~1"
SET "txt=!txt:""="!"
IF "1" == "!testmode!" (
  ECHO !txt!
) ELSE IF "" NEQ "%~2" (
  ECHO !txt!
)

SET "TS=%DATE% %TIME%"
IF EXIST "!logfile!" (
  ECHO !TS! !txt!>>"!logfile!"
) ELSE (
  ECHO !TS! !txt!>"!logfile!"
)
EXIT /B
rem ****************
rem ****************

:exit
IF "1" == "!testmode!" PAUSE
IF "1" NEQ "!testmode!" EXIT
