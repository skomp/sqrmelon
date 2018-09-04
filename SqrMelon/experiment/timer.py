from math import floor
import time
import icons
from qtutil import *
from OSC import OSCClientError, OSCMessage, OSCClient


class OSCManager(object):
    def __init__(self):
        self.__client = OSCClient()
        self.__client.connect(('127.0.0.1', 2223))
        self.__isPlaying = False

    def __del__(self):
        self.__client.close()

    def __sendSilent(self, msg):
        # silently ignore any failure while sending
        try:
            self.__client.send(msg)
        except OSCClientError:
            return

    def setPosition(self, time):
        if self.__isPlaying:
            return
        msg = OSCMessage()
        msg.setAddress('/position')
        msg.append(time)
        self.__sendSilent(msg)

    def setBpm(self, bpm):
        msg = OSCMessage()
        msg.setAddress('/bpm')
        msg.append(bpm)
        self.__sendSilent(msg)

    def play(self):
        msg = OSCMessage()
        msg.setAddress('/play')
        msg.append(1)
        self.__sendSilent(msg)
        self.__isPlaying = True

    def pause(self):
        msg = OSCMessage()
        msg.setAddress('/play')
        msg.append(0)
        self.__sendSilent(msg)
        self.__isPlaying = False

    def scrub(self, state):
        msg = OSCMessage()
        msg.setAddress('/scrub')
        msg.append(state)
        self.__sendSilent(msg)

    def loop(self, start, end):
        msg = OSCMessage()
        msg.setAddress('/loopstart')
        msg.append(start)
        self.__sendSilent(msg)
        msg = OSCMessage()
        msg.setAddress('/looplength')
        msg.append(end - start)
        self.__sendSilent(msg)


class Time(QObject):
    timeChanged = pyqtSignal(float)
    timeLooped = pyqtSignal(float)
    loopStartChanged = pyqtSignal(float)
    loopEndChanged = pyqtSignal(float)
    bpmChanged = pyqtSignal(float)

    def __init__(self):
        super(Time, self).__init__()

        self.changed = Signal()
        self._time = 0.0
        self._loopStart = 0.0
        self._loopEnd = 10.0
        self._bpm = 120.0

        self._osc = OSCManager()
        self.timeChanged.connect(self._osc.setPosition)
        self.loopStartChanged.connect(self._oscSetLoopRange)
        self.loopEndChanged.connect(self._oscSetLoopRange)

        self._timer = QTimer()
        self._timer.timeout.connect(self._tick)
        self._prevTime = None

    def beatsToSeconds(self, beats):
        return beats * 60.0 / self._bpm

    def _secondsToBeats(self, seconds):
        return seconds * self._bpm / 60.0

    def _oscSetLoopRange(self, *args):
        self._osc.loop(self._loopStart, self._loopEnd)

    # def oscScrub(self, state):
    #    self._osc.scrub(state)

    @property
    def time(self):
        return self._time

    @time.setter
    def time(self, time):
        self._time = time
        self.timeChanged.emit(self._time)

    def setTime(self, value):
        self.time = value

    @property
    def bpm(self):
        return self._bpm

    @bpm.setter
    def bpm(self, bpm):
        self._bpm = bpm
        self.bpmChanged.emit(self._bpm)

    def setBpm(self, bpm):
        self._bpm = bpm
        self._osc.setBpm(int(bpm))
        self.bpmChanged.emit(bpm)

    @property
    def loopStart(self):
        return self._loopStart

    @loopStart.setter
    def loopStart(self, loopStart):
        self._loopStart = loopStart
        self.loopStartChanged.emit(self._loopStart)

    def setLoopStart(self, loopStart):
        self.loopStart = loopStart

    @property
    def loopEnd(self):
        return self._loopEnd

    @loopEnd.setter
    def loopEnd(self, loopEnd):
        self._loopEnd = loopEnd
        self.loopEndChanged.emit(self._loopEnd)

    def setLoopEnd(self, loopEnd):
        self.loopEnd = loopEnd

    def _tick(self):
        if self._prevTime is None:
            self._prevTime = time.time()
            return
        delta = time.time() - self._prevTime
        self._prevTime = time.time()

        delta = self._secondsToBeats(delta)

        t = self._time + delta - self._loopStart
        r = self._loopEnd - self._loopStart
        if r > 0.001:
            loop = floor(t / r)
        else:
            loop = 0.0
        self._time = t - loop * r + self._loopStart
        self.timeChanged.emit(self.time)
        if loop != 0:
            self.timeLooped.emit(self.time)

    def isPlaying(self):
        return self._timer.isActive()

    def playPause(self):
        if self._timer.isActive():
            self._prevTime = None
            self._timer.stop()
            self._osc.pause()
        else:
            self._timer.start(1.0 / 60.0)
            self._osc.play()

    def stepNext(self):
        if self.time + 1.0 > self._loopEnd:
            self.time = self._loopStart
        else:
            self.time += 1.0

    def stepBack(self):
        if self.time - 1.0 < self._loopStart:
            self.time = self._loopEnd
        else:
            self.time -= 1.0

    def goToStart(self):
        self.time = self._loopStart

    def goToEnd(self):
        self.time = self._loopEnd


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
