#!/bin/sh
: <<'main'
*******************************************************************************

onTxComplete.sh v1.2 for SickGear

  Script to copy select files to a location for SickGear to post process.

  This is used with the 'Move' post process episode method
  so that seeding files are not post processed over and over.

*******************************************************************************

Supported clients
-----------------
* Deluge clients 1.3.15 and newer clients
* qBittorrent 4.13+ and newer clients
* Transmission 2.84 and newer clients
* uTorrent 2.2.1

Supported OS
------------
* Linux, FreeBSD and POSIX compliant Unix-like systems


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

param4 = Client set downloaded item content path (e.g. "%F", "%D/%F" etc)

Token values for params 3 and 4 are found documented in the download client or
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
   set command to ... [script dir]/onTxComplete.sh

4) Add the label set in step (e) to Deluge, right click the label and select
   "Label Options"/Location/Move completed to/Other/ .. choose a folder created
   where its name is identical to this label e.g. [path]/[label], ($HOME/downloads/SG)

Reference: http://dev.deluge-torrent.org/wiki/Plugins/Execute


For qBittorrent
---------------
The above four parameters are used to configure and run the script.

Use one cmd from below replacing "[script dir]" with the path to this script

Set Options/Downloads/Run an external program on torrent completion

.. to run
   [script dir]/onTxComplete.sh "$HOME/sg_pp" "SG" "%L" "%F"


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
   config file value of param2 e.g. [path]/[param2]

Reference: https://web.archive.org/web/20171009055508/https://trac.transmissionbt.com/wiki/Scripts#OnTorrentCompletion


For uTorrent
------------
The above four parameters are used to configure and run the script.

Use one cmd below replacing "[script dir]" with the path to this script

1) Set Preferences/Advanced/Run program/Run this program when a torrent finishes
   [script dir]/onTxComplete.sh "$HOME/sg_pp" "SG" "%L" "%D/%F"

It is advised to not use the uTorrent "Move completed downloads" feature because
it runs scripts before move actions complete, bad. Consider switching clients.

Reference: https://stackoverflow.com/a/29071224

main
# ***************************************************************************
# Set 1 to enable test mode output (default: blank)
testmode=
# ***************************************************************************

# Get install dir without trailing slash
install_dir="$(dirname $(realpath "$0"))"

# Append text to logfile, and output text to stdio if testmode is "1"
log(){
  local logfile="${install_dir}/onTxComplete.log"
  local txt="$1"
  [ "1" = "$testmode" ] || [ "" != "$2" ] && echo "$txt"

  local ts="$(date '+%Y/%m/%d %H:%M:%S')"
  if [ -e "$logfile" ]; then
    echo "$ts $txt" >> "$logfile"
  else
    echo "$ts $txt" > "$logfile"
  fi
}

if [ -n "$4" ]; then

  # Use the four input parameters
  # This also strips quotes used to safely pass values containing spaces
  sg_path=$(echo $1 | xargs)
  sg_label=$(echo $2 | xargs)
  client_label=$(echo $3 | xargs)
  content_path=$(echo $4 | xargs)
  [ "1" != "$testmode" ] && [ "" != "$(echo $5 | xargs)" ] && testmode="1"
  check_label_path_tail=""

else

  # Process config file
  cfgfile="$install_dir"/onTxComplete.cfg
  eval $(sed -r '/[^=]+=[^=]+/!d;/^[ *]/d;/[;#]/d;s/\s*=\s*/=/g;s/\r//g' "$cfgfile")
  if [ "1" = "$testmode" ]; then
    log "Config ... param1 = ${param1}"
    log "Config ... param2 = ${param2}"
  fi

  if [ -z "$param1" ] || [ -z "$param2" ]; then
    log "Error: Issue while reading file $cfgfile" "force"
    exit
  fi

  sg_path="$param1"
  sg_label="$param2"

  # Attempt to read Transmission environment variables
  client_name="$TR_TORRENT_NAME"
  client_path="$TR_TORRENT_DIR"

  if [ -z "$client_name" ] || [ -z "$client_path" ]; then

    # With no Transmission vars, attempt to read input parameters from Deluge
    # Deluge sends id, name, and path
    if [ -z "$3" ]; then
      log "Error: not enough input params, read comments in $0 for usage" "force"
      exit
    fi

    # Deluge input parameters (i.e. "TorrentID" "Torrent Name" "Torrent Path")
    # This also strips quotes used to safely pass values containing spaces
    client_name=$(echo $2 | xargs)
    client_path=$(echo $3 | xargs)
  fi
  content_path="$client_path/$client_name"
  check_label_path_tail="1"
fi

# Replace any double slashes in path with single slash
sg_path=$(echo ${sg_path} | sed -En "s/([/\])?[/\]*/\1/gp")
content_path=$(echo ${content_path} | sed -En "s/([/\])?[/\]*/\1/gp")

# Remove any trailing slashes from paths
sg_path=${sg_path%/}
content_path=${content_path%/}
client_path=${client_path%/}

if [ -n "$check_label_path_tail" ]; then
  # Enable the copy action if path ends with user defined label
  client_label="$sg_label"

  label_length=$(echo -n "$sg_label" | wc -m)

  [ "/$sg_label" != $(echo -n $client_path | tail -c $((1 + $label_length))) ] && client_label="skip copy"
fi

# Create '.!sync' filename
syncext="!sync"
basefile="$sg_path/copying"
syncfile="$basefile.$syncext" && files="$basefile.files.txt" && tmp="$basefile.tmp"
num=2
while [ -e "$syncfile" ]; do
  syncfile="$sg_path/copying-$num.$syncext" && files="$basefile-$num.files.txt" && tmp="$basefile-$num.tmp"
  num=$((1 + $num))
done

[ "1" = "$testmode" ] && log "Running in ***test mode*** - files will not be copied"
log "**** cmd = \"$(realpath "$0")\""
log "  param1 = \"$sg_path\""
log "  param2 = \"$sg_label\""
log "  param3 = \"$client_label\""
log "  param4 = \"$content_path\""
log "syncfile = \"$syncfile\""


if [[ ! -z "$client_label" ]] \
   && [[ "${client_label}" = "${sg_label}"* ]]; then

  [ ! -d "$sg_path" ] && mkdir -p "$sg_path"

  if [ -d "$sg_path" ]; then

    # Determine file/folder as these need to be handled differently
    if [ -d "$content_path" ]; then

      # Create a file to prevent SG premature post processing (ref: step (d)) ..
      echo "Copying folder \"$content_path\" to \"$sg_path\"" > "$syncfile"

      cd "$content_path"

      # Copy from; `parent/` to `{pp}/parent/` and `parent/.../child/` to `{pp}/parent/child/`
      parent="/${content_path##*/}"

      # Sort by largest to smallest filesize for copy
      find . -type f -print0 | xargs -r0 ls -1S | while read srcfile; do
        # Copy
        child=""
        relpath="${srcfile%/*}"
        if [ "." != "$relpath" ]; then
          child="/${relpath##*/}"
        fi
        filename="${srcfile##*/}"
        dstdir="$sg_path$parent$child"
        dstfile="$dstdir/$filename"

        if [ "1" = "$testmode" ]; then

          [ ! -d "$dstdir" ] && log "mkdir -p \"$dstdir\""
          if [ ! -e "$dstfile" ]; then
            log "cp -p \"$srcfile\" \"$dstfile\" >/dev/null 2>&1"
          else
            log "Skipping, file exists \"$dstfile\""
          fi

        else

          [ ! -d "$dstdir" ] && mkdir -p "$dstdir"
          [ ! -e "$dstfile" ] && cp -p "$srcfile" "$dstfile" >/dev/null 2>&1

        fi
      done

      [ "1" != "$testmode" ] && [ -f "$syncfile" ] && rm -f "$syncfile"

    else

      # Create a file to prevent SG premature post processing (ref: step (d)) ..
      echo "Copying file \"$content_path\" to \"$sg_path/\"" > "$syncfile"

      if [ "1" = "$testmode" ]; then

        log "cp \"$content_path\" \"$sg_path/\""

      else

        cp "$content_path" "$sg_path/" >/dev/null 2>&1
        [ -f "$syncfile" ] && rm -f "$syncfile"

      fi
    fi
  fi
fi

exit
