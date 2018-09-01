"""
Utility to manage QApplication override cursors.

When overriding a cursor, and then having some exception or edge case not call restore,
the application can normally get stuck with a wrong cursor (because internally the override is a stack).

With this utility a restore call will always fully restore the whole stack
in case a restore was missed for one of the cursor overrides.
"""
from qtutil import *

_cursorStack = []


def set(cursor):
    # track how many layers deep we are overriding the cursor
    _cursorStack.append(cursor)
    QApplication.setOverrideCursor(cursor)


def restore():
    # restore full stack
    while _cursorStack:
        _cursorStack.pop(-1)
        QApplication.restoreOverrideCursor()
