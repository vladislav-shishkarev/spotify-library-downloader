"""Downloads the library from YouTube Music. Details and flags: spotlib/commands/ytm.py, python ytm_download.py --help"""
from spotlib.commands import run
from spotlib.commands.ytm import main

if __name__ == "__main__":
    run(main)
