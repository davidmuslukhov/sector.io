"""Thin shim so ``python city.py`` still launches the Surrey city scene."""

from city.__main__ import main

if __name__ == "__main__":
    main()
