import icons
from qtutil import *


class Time(object):
    def __init__(self, time=0.0):
        self.changed = Signal()
        self._time = time

    @property
    def time(self):
        return self._time

    @time.setter
    def time(self, time):
        self._time = time
        self.changed.emit()


def drawPlayhead(painter, x, height):
    painter.setPen(Qt.red)
    painter.drawLine(x, 16, x, height)
    painter.setPen(Qt.darkRed)
    painter.drawLine(x + 1, 0, x + 1, height)
    painter.drawPixmap(x - 4, 0, icons.getImage('playhead'))


def drawLoopRange(painter, left, right, width, height):
    painter.setOpacity(0.5)

    painter.fillRect(0, 0, left, height, Qt.black)
    painter.fillRect(right + 2, 0, width - right, height, Qt.black)

    painter.setPen(QColor(33, 150, 243))
    painter.drawLine(left, 16, left, height)
    painter.drawLine(right, 16, right, height)

    painter.setPen(QColor(63, 81, 181))
    painter.drawLine(left + 1, 16, left + 1, height)
    painter.drawLine(right + 1, 16, right + 1, height)

    painter.drawPixmap(left, 0, icons.getImage('left'))
    painter.drawPixmap(right - 4, 0, icons.getImage('right'))

    painter.setOpacity(1.0)
