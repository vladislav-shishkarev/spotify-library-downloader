"""Entry points; download.py, ytm_download.py etc. in the root are wrappers around them."""
import sys


def run(main):
    """Runs a command from the console: UTF-8 output, otherwise non-Latin text breaks in the Windows console."""
    sys.stdout.reconfigure(encoding="utf-8")
    main()
