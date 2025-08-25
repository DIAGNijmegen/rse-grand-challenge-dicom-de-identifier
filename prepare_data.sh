#!/bin/bash

display_help () {
    echo "usage: $0 [target_dir|--dry-run]"
    exit 1
}

CONFIGFILE="./prepare_data.conf"
if [ ! -f $CONFIGFILE ]; then
    echo "$CONFIGFILE is required but was not found"
    exit 1
fi
source $CONFIGFILE

if [ -z ${FILELIST+x} ]; then
    echo "FILELIST variable should be set in $CONFIGFILE"
    exit 1
fi
if [ -z ${INPUTDIR+x} ]; then
    echo "INPUTDIR variable should be set in $CONFIGFILE"
    exit 1
fi
if [ -z ${CHECKMD5+x} ]; then
    echo "CHECKMD5 variable should be set in $CONFIGFILE"
    exit 1
fi

if [ ! -f $FILELIST ]; then
    echo "$FILELIST is required"
    exit 1
fi

FILELIST=`realpath $FILELIST`

if [ $# -eq 0 ] || [ $# -ge 2 ]; then
    display_help
fi

INPUTDIR=`realpath $INPUTDIR`
cd $INPUTDIR

while [ $# -ne 0 ]
do
    case "$1" in
        --dry-run)
            if $CHECKMD5 ; then
                echo "checking file existence and validity (md5)..."
                md5sum -c $FILELIST
            else
                echo "checking file existence only..."
                ! (for i in `awk -F " " '{print $NF}' $FILELIST`; do test ! -f "$i" && echo "$i does not exist" && test -f "$i"; done | grep "not")
            fi
            if [ $? -eq 0 ]; then
                echo "Ok"
                exit 0
            else
                echo "Failed: invalid files found"
                exit 1
            fi
            ;;
        --help) display_help
            ;;
        -h) display_help
            ;;
        *)  echo "copy data to: $1"
            if [ ! -d $1 ]; then
                echo "$1 is not a valid target directory"
                exit 1
            fi
            echo "perform pre-copy file checks..."
            ! (for i in `awk -F " " '{print $NF}' $FILELIST`; do test ! -f "$i" && echo "$i does not exist" && test -f "$i"; done | grep "not")
            if [ $? -eq 0 ]; then
                echo "OK. start file copy from $INPUTDIR to $1"
                TMPFILE=$(mktemp /tmp/abc-script.XXXXXX)
                sed 's/.*\s\s//' $FILELIST > $TMPFILE
                rsync -v --size-only --files-from=$TMPFILE $INPUTDIR $1/
                rm "$TMPFILE"
            else
                echo "Failed: not all files from $FILELIST were found."
                exit 1
            fi
            exit 0
            ;;
    esac
    shift
done
