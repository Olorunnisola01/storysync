#!/usr/bin/env python3
"""StorySync entry point."""

import multiprocessing

from storysync.gui.app import App


def main():
    App().mainloop()


if __name__ == '__main__':
    # Required for ProcessPoolExecutor inside a PyInstaller one-file EXE on
    # Windows: prevents worker processes from re-launching the GUI on spawn.
    multiprocessing.freeze_support()
    main()
