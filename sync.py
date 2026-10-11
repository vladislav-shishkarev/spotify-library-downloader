"""Синхронизирует папку с лайками. Подробности и флаги: spotlib/commands/sync.py, python sync.py --help"""
from spotlib.commands import run
from spotlib.commands.sync import main

if __name__ == "__main__":
    run(main)
