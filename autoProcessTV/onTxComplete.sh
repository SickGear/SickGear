#!/bin/sh
#*******************************************************************************
#
# onTxComplete.sh v1.0 for SickGear
#
#  Script to copy select files to a location for SickGear to post process.
#
#  This allows the 'Move' post process episode method to be used so that
#  seeding files are not post processed over and over.
#
#*******************************************************************************
#
# Supported clients
# -----------------
# * Deluge clients 1.3.15 and newer clients
# * qBittorrent 3.3.12 and newer clients
# * Transmission 2.84 and newer clients
# * uTorrent 2.2.1 and newer clients
#
#
# How this works
#--------------
# Completed downloads are copied from a seeding location to an isolated location.
# SG will 'Move' processed content from isolation to the final show location.
#
# The four parameters;
# param1 = Isolation path where to copy completed downloads for SG to process.
#          This value *must* ..
#          1) be different to the path where the client saves completed downloads
#          2) be configured in SG (see later, step a)
#          This path should be created on first run, if not, create it yourself.
#
# param2 = This filter value is compared with either a client set label, or the
#          tail of the path where the client downloaded seeding file is located.
#          Every download is skipped except those that compare successfully.
#
# param3 = Client set downloaded item category or label (e.g. "%L")
#
# param4 = Client set downloaded item content path (e.g. "%F", "%D/%F" etc)
#
# The values of params 3 and 4 can be found documented in the download client or
# at the client webiste. Other clients may be able to replace param3 and param4
# to fit (see examples).
#
#
# To set up SickGear
# ------------------
# a) Set /config/postProcessing/Post Processing -> "Completed TV downloads"
#    .. to match param1
#
# b) Set /config/postProcessing/Post Processing -> "Process episode method"
#    .. to 'Move'
#
# c) Enable /config/postProcessing/Post Processing -> "Scan and post process"
#
# d) Enable /config/postProcessing/Post Processing -> "Postpone post processing"
#
# e) Set /config/search/Torrent Results -> "Set torrent label/category"
#    If using "Black hole" method or if there is no label field, then you must use
#    client auto labeller or a torrent completed save path that ends with param2,
#    for Transmission, see note(2) in that section below.
#
#
# To set up the download client
# -----------------------------
#
# For Deluge
# ----------
# Deluge clients call scripts with fixed params that prevent passing params,
# rename onTxComplete.sample.cfg as onTxComplete.cfg and edit parameters there.
#
# A Deluge label is used to isolate SG downloads from everything else.
#
# 1) Enable the "Label" plugin
#
# 2) Enable the "Execute" plugin
#
# 3) In the "Execute" plugin settings /Add Command/Event/Torrent Complete
#    set command to ... [script dir]\onTxComplete.sh
#
# 4) Add the label set in step (e) to Deluge, right click the label and select
#    "Label Options"/Location/Move completed to/Other/ .. choose a folder created
#    where its name is identical to this label e.g. [path]\[label], (/home/downloads/SG)
#
# Reference: http://dev.deluge-torrent.org/wiki/Plugins/Execute
#
#
# For qBittorrent
# ---------------
# The above four parameters are used to configure and run the script.
#
# Use one cmd from below replacing "[script dir]" with the path to this script
#
# Set Options/Downloads/Run an external program on torrent completion
#
# .. to run in windowless mode (the normal run mode used)
#    [script dir]\onTxComplete.sh "/home/sg_pp" "SG" "%L" "%F"
#
# OR ..
# .. to run in console window mode (test mode to see console output)
#    [script dir]\onTxComplete.sh "/home/sg_pp" "SG" "%L" "%F"
#
#
# For Transmission
# ----------------
# Transmission clients call scripts with fixed params that prevent passing params,
# rename onTxComplete.sample.cfg as onTxComplete.cfg and edit parameters there.
#
# Transmission does not contain labels, instead, the set path(2) is compared
# to the config file param2 value to isolate SG downloads from everything else.
#
# 1) Edit/Preferences/Downloading/Call script when torrent is completed
#    ... Navigate to this script location and select it
#
# 2) Follow "To set up SickGear" instruction but at step (e),
#    set "Downloaded files location" to a created folder with name ending in the
#    config file value of param2 e.g. [path]\[param2]
#
# Reference: https://trac.transmissionbt.com/wiki/Scripts
#
#
# For uTorrent
# ------------
# The above four parameters are used to configure and run the script.
#
# Use one cmd below replacing "[script dir]" with the path to this script
#
# 1) Set Preferences/Advanced/Run program/Run this program when a torrent finishes
#    [script dir]\onTxComplete.sh "/home/sg_pp" "SG" "%L" "%D/%F"
#
# It is advised to not use the uTorrent "Move completed downloads" feature because
# it runs scripts before move actions complete, bad. Consider switching.
#
# Reference: https://stackoverflow.com/a/29071224
BASEDIR=$(dirname $(realpath "$0"))

# ***************************************************************************
# Set 1 to enable test mode output (default: blank)
testmode=""
# ***************************************************************************

# Get install dir without trailing slash
install_dir="$BASEDIR"

if [ -n "$4" ]
then
  # Use the four input parameters
  # Also strip trailing slashes
  sg_path="${1%/}"
  sg_label="${2%/}"
  client_label="${3%/}"
  content_path="${4%/}"
  check_label_path_tail=""

else
  # Process config file
  cfgfile="$install_dir"/onTxComplete.cfg
  # get param1 & param2 from cfg file
  . "$cfgfile"
  [ $testmode == "1" ] && echo "Config ... \"${param1}\" = \"${param2}\""

  if [ -z "$param1" ] || [ -z "$param2" ]; then
    echo "Error: Issue while reading file $cfgfile"
    exit
  fi

  sg_path="$param1"
  sg_label="$param2"

  # Read Transmision environment variables
  client_name="$TR_TORRENT_NAME"
  client_path="$TR_TORRENT_DIR"

  # When client_name or client_path are empty, use script arguments
  if [ -z "$client_name" ] || [ -z "$client_path" ]; then

    # With no Transmission vars, attempt to read input parameters from Deluge
    if [ -z "$3" ]; then
      echo "Error: $0 not enough input params, Deluge sends id, name, and path"
      exit
    fi

    # Deluge input parameters (i.e. \"TorrentID\" \"Torrent Name\" \"Torrent Path\")
    # This also strips quotes used to safely pass values containing spaces
    client_name="${2%/}"
    client_path="${3%/}"

  fi

  content_path="$client_path"/"$client_name"
  check_label_path_tail="1"

fi

# Remove any trailing slashes from paths
sg_path=${sg_path%/}

if [ -n "$check_label_path_tail" ]; then
  # Enable the copy action if path ends with user defined label
  client_label="$sg_label"
  label_length=$(echo -n "$sg_label" | wc -m)
  [ "$sg_label" != ${client_path: -$label_length} ] && client_label="skip copy"
fi

# Create '.!sync' file
syncext="!sync"
syncfile="$sg_path/copying.$syncext"

if [ "$testmode" == "1" ]; then
  echo "Running in ***test mode*** - files will not be copied"
  echo "param1 = $sg_path"
  echo "param2 = $sg_label"
  echo "param3 = $client_label" 
  echo "param4 = $content_path"
  echo "$syncfile"
fi

if [[ "$client_label" == *"$sg_label"* ]]; then

  [ ! -d "$sg_path" ] && mkdir "$sg_path"

  if [ -d "$sg_path" ]; then

    # Determine file/folder as these need to be handled differently
    if [ -d "$content_path" ]; then
      # Create a file to prevent SG premature post processing (ref: step (d)) ..
      echo "Copying folder '$content_path' to '$sg_path' > '$syncfile'"

      if [ "$testmode" == "1" ]; then
        echo "cp -rp $content_path $sg_path/"
      else
        touch $syncfile
        cp -rp "$content_path" "$sg_path/"
        [ -f "$syncfile" ] && rm "$syncfile"
      fi

    else
      # Create a file to prevent SG premature post processing (ref: step (d)) ..
      echo "Copying file \"$content_path\" to \"$sg_path\" > \"$syncfile\""

      if [ "$testmode" == "1" ]; then
        echo "cp \"$content_path\" \"$sg_path\""
      else
        cp "$content_path" "$sg_path"
        [ -f "$syncfile" ] && rm "$syncfile"
      fi
    fi
  # Skip copying
  fi
else
  exit
fi

