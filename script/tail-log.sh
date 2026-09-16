#!/bin/zsh
tail -n "${1:-200}" -F "$HOME/Library/Logs/Ludeon Studios/RimWorld by Ludeon Studios/Player.log" | grep --line-buffered -iE "rimbridge|exception|error"
