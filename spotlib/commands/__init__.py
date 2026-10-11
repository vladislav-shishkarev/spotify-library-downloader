"""Точки входа; корневые download.py, ytm_download.py и т.д. — обёртки над ними."""
import sys


def run(main):
    """Запуск команды из консоли: вывод в UTF-8, иначе кириллица в консоли Windows ломается."""
    sys.stdout.reconfigure(encoding="utf-8")
    main()
