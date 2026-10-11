"""Качает альбом Spotify целиком. Подробности и флаги: spotlib/commands/album.py, python album.py --help"""
from spotlib.commands import run
from spotlib.commands.album import main

if __name__ == "__main__":
    run(main)
