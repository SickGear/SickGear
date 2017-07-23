@ECHO OFF
GOTO :main
*******************************************************************************

onTxComplete.bat v1.0 for Sickgear

  Script to copy select files to a location for SickGear to post process.

  This allows the 'Move' post process episode method to be used so that
  seeding files are not post processed over and over.

*******************************************************************************

Supported clients
-----------------
* Deluge clients 1.3.15 and newer clients
* qBittorrent 3.3.12 and newer clients
* Transmission 2.84 and newer clients
* uTorrent 2.2.1 and newer clients


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
         Every download is skipped except those that compare successfully.

param3 = Client set downloaded item category or label (e.g. "%L")

param4 = Client set downloaded item content path (e.g. "%F", "%D\%F" etc)

The values of params 3 and 4 can be found documented in the download client or
at the client webiste. Other clients may be able to replace param3 and param4
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

Reference: https://trac.transmissionbt.com/wiki/Scripts


For uTorrent
------------
The above four parameters are used to configure and run the script.

Use one cmd below replacing "[script dir]" with the path to this script

1) Set Preferences/Advanced/Run program/Run this program when a torrent finishes
   cmd /c start "" /B [script dir]\onTxComplete.bat "F:\sg_pp" "SG" "%L" "%D\%F"

It is advised to not use the uTorrent "Move completed downloads" feature because
it runs scripts before move actions complete, bad. Consider switching.

Reference: https://stackoverflow.com/a/29071224

:main
rem ***************************************************************************
rem Set 1 to enable test mode output (default: blank)
SET testmode=
rem ***************************************************************************
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
  SET "check_label_path_tail="

) ELSE (

  rem Process config file
  SET "cfgfile=!install_dir!onTxComplete.cfg"
  FOR /F "eol=; tokens=1,2 delims==" %%a IN (!cfgfile!) DO (
    SET "%%a=%%b"
    IF "1" == "!testmode!" (
      ECHO Config ... %%a = %%b
    )
  )

  SET "nullvar="
  IF NOT DEFINED param1 SET "nullvar=1"
  IF NOT DEFINED param2 SET "nullvar=1"
  IF DEFINED nullvar (
    ECHO Error: Issue while reading file !cfgfile!
    GOTO:exit
  )
  SET "sg_path=!param1!"
  SET "sg_label=!param2!"

  rem Attempt to read Transmision environment variables
  SET "client_name=%TR_TORRENT_NAME%"
  SET "client_path=%TR_TORRENT_DIR%"

  SET "nullvar="
  IF "" == "!client_name!" SET "nullvar=1"
  IF "" == "!client_path!" SET "nullvar=1"

  IF DEFINED nullvar (

    rem With no Transmission vars, attempt to read input parameters from Deluge
    IF "" == "%~3" (

      ECHO Error: %0 not enough input params, Deluge sends id, name, and path
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

rem Remove long path switch for most compatiblity, newer OSes may omit this
IF "\?\" == "!sg_path:~0,3!" SET "sg_path=!sg_path:~3!"
IF "\?\" == "!content_path:~0,3!" SET "content_path=!content_path:~3!"

rem Remove any trailing slashes from paths
IF "\" == "!sg_path:~-1!" SET "sg_path=!sg_path:~0,-1!"
IF "\" == "!content_path:~-1!" SET "content_path=!content_path:~0,-1!"


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
SET "syncfile=!sg_path!\copying.!syncext!"


IF "1" == "!testmode!" (

  ECHO Running in ***test mode*** - files will not be copied
  ECHO param1 = !sg_path!
  ECHO param2 = !sg_label!
  ECHO param3 = !client_label!
  ECHO param4 = !content_path!
  ECHO !syncfile!

)


CALL:StartsWith "!client_label!" "!sg_label!" && (

  IF NOT EXIST "!sg_path!" MKDIR "!sg_path!"

  IF EXIST "!sg_path!" (

    rem Determine file/folder as these need to be handled differently
    SET attr=%~a4
    IF /I "dir" == "!attr:~0,1!ir" (

      rem Create a file to prevent SG premature post processing (ref: step (d)) ..
      ECHO Copying folder "!content_path!" to "!sg_path!" > "!syncfile!"

      FOR /F "tokens=*" %%a IN ('DIR "!content_path!" /S/B') DO (

        IF "1" == "!testmode!" (

          ECHO XCOPY "%%a" "!sg_path!\.%%~pa" /Y/I/S

        ) ELSE (

          XCOPY "%%a" "!sg_path!\.%%~pa" /Y/I/S >NUL 2>NUL
          IF EXIST "!syncfile!" DEL "!syncfile!"

        )

      )

    ) ELSE (

      rem Create a file to prevent SG premature post processing (ref: step (d)) ..
      ECHO Copying file "!content_path!" to "!sg_path!" > "!syncfile!"

      IF "1" == "!testmode!" (

        ECHO COPY "!content_path!" "!sg_path!\" /Y

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
rem ****************
rem ****************

:exit
IF "1" == "!testmode!" PAUSE
IF "1" NEQ "!testmode!" EXIT
