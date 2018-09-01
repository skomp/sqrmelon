import colorsys
from qtutil import *


def sign(x): return -1 if x < 0 else 1


_randomColorSeed = 0.0


def randomColor(seed=None):
    if seed is None:
        global _randomColorSeed
        _randomColorSeed = (_randomColorSeed + 0.7) % 1.0
        r, g, b = colorsys.hsv_to_rgb(_randomColorSeed, 0.4, 0.9)
    else:
        r, g, b = colorsys.hsv_to_rgb(seed, 0.4, 0.9)
    return r * 255, g * 255, b * 255


class PooledResource(object):
    _pool = {}

    @classmethod
    def pool(cls, *key):
        if key in cls._pool:
            scene = cls._pool[key]
        else:
            scene = cls(*key)
            cls._pool[key] = scene
        return scene


class FileSystemWatcher2(QFileSystemWatcher):
    def __init__(self, pathsToWatch):
        super(FileSystemWatcher2, self).__init__()
        for pathToWatch in pathsToWatch:
            self.addPath(pathToWatch)
        for dirName in {os.path.dirname(pathToWatch) for pathToWatch in pathsToWatch}:
            self.addPath(dirName)
        self.pathsToWatch = [unicode(os.path.abspath(pathToWatch)) for pathToWatch in pathsToWatch]
        self.directoryChanged.connect(self.__handleDeleteCreateInsteadOfSave)

    def addNewPaths(self, pathsToWatch):
        for pathToWatch in pathsToWatch:
            if pathToWatch in self.pathsToWatch:
                continue
            self.addPath(pathToWatch)
            self.pathsToWatch.append(unicode(os.path.abspath(pathToWatch)))
        for dirName in {os.path.dirname(pathToWatch) for pathToWatch in pathsToWatch} - set(self.directories()):
            self.addPath(dirName)

    def clear(self):
        self.removePaths(self.pathsToWatch)
        del self.pathsToWatch[:]

    def __handleDeleteCreateInsteadOfSave(self):
        """
        https://stackoverflow.com/questions/18300376/qt-qfilesystemwatcher-signal-filechanged-gets-emited-only-once/30076119
        some text editors save to a temp file, delete the existing file and move their temp file
        file system watcher stops watching files upon delete
        but we do get a lot of directory changes, so we can ensure we are watching the right files all the time
        we could technically do this during the fileChanged callback, but the un-watching happens async so it is not reliable
        """
        for missingStitch in set(self.pathsToWatch) - set(self.files()):
            self.addPath(missingStitch)
