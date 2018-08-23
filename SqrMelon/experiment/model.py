from collections import OrderedDict
from qtutil import *
from experiment.modelbase import ItemRow, Label


class Clip(ItemRow):
    def __init__(self, name):
        # type: (str) -> None
        super(Clip, self).__init__(name)
        self.__dict__['curves'] = QStandardItemModel()
        self.__dict__['textures'] = OrderedDict()

    def evaluate(self, localTime):
        # type: (float) -> dict[str, float]
        result = {}
        for row in xrange(self.curves.rowCount()):
            pyObj = self.curves.item(row).data()
            result[str(pyObj)] = pyObj.evaluate(localTime)
        return result

    @classmethod
    def properties(cls):
        return 'name',


class Event(ItemRow):
    def __init__(self, name, clip, start=0.0, end=1.0, speed=1.0, roll=0.0, track=0):
        # type: (str, Clip, float, float, float, float, int) -> None
        super(Event, self).__init__(name, clip, start, end, end - start, speed, roll, track)

    def evaluate(self, time):
        # type: (float) -> dict[str, float]
        return self.clip.evaluate((time - self.start) * self.speed + self.roll)

    def propertyChanged(self, index):
        START_INDEX = 2
        END_INDEX = 3
        DURATION_INDEX = 4

        if index == START_INDEX:
            self.end = self.start + self.duration
        elif index == END_INDEX:
            self.duration = self.end - self.start
        elif index == DURATION_INDEX:
            self.end = self.start + self.duration

    @classmethod
    def properties(cls):
        return 'name', 'clip', 'start', 'end', 'duration', 'speed', 'roll', 'track'

    def copy(self):
        return self.__class__(self.name, self.clip, self.start, self.end, self.speed, self.roll, self.track)


class Shot(ItemRow):
    def __init__(self, name, sceneName, start=0.0, end=1.0, track=0):
        super(Shot, self).__init__(name, Label(sceneName), start, end, end - start, track)

    def propertyChanged(self, index):
        START_INDEX = 2
        END_INDEX = 3
        DURATION_INDEX = 4

        if index == START_INDEX:
            self.end = self.start + self.duration
        elif index == END_INDEX:
            self.duration = self.end - self.start
        elif index == DURATION_INDEX:
            self.end = self.start + self.duration

    @classmethod
    def properties(cls):
        return 'name', 'scene', 'start', 'end', 'duration', 'track'

    def copy(self):
        return self.__class__(self.name, self.scene.text, self.start, self.end, self.track)
