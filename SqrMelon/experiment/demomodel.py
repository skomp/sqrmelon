from qtutil import *
from experiment.commands import ModelEdit
from experiment.model import Event, Shot
from experiment.modelbase import UndoableModel
from experiment.projectutil import iterSceneNames


class DemoModel(UndoableModel):
    def addShot(self, shot):
        self.undoStack.push(ModelEdit(self, [shot], []))

    def createEvent(self, timer, clip):
        time = timer.time
        self.undoStack.push(ModelEdit(self, [Event(clip.name, clip, time, time + 8.0)], []))

    def evaluate(self, time):
        # type: (float) -> (Scene, Dict[str, float])
        # find things at this time
        visibleShot = None
        activeEvents = []
        for row in xrange(self.rowCount()):
            pyObj = self.item(row).data()
            if pyObj.start <= time <= pyObj.end:
                if isinstance(pyObj, Shot):
                    if visibleShot is None or pyObj.track < visibleShot.track:
                        visibleShot = pyObj
                if isinstance(pyObj, Event):
                    activeEvents.append(pyObj)
        scene = None
        if visibleShot:
            scene = visibleShot.scene

        # sort events by inverse priority
        activeEvents.sort(key=lambda x: -x.track)

        # evaluate and overwrite (because things with priority are evaluated last)
        evaluatedData = {}
        for event in activeEvents:
            evaluatedData.update(event.evaluate(time))

        return scene, evaluatedData


class CreateItemRowDialog(QDialog):
    def __init__(self, itemLabels, initialItemLabel=None, parent=None):
        super(CreateItemRowDialog, self).__init__(parent)
        layout = vlayout()
        self.setLayout(layout)
        self.name = QLineEdit()
        layout.addWidget(self.name)
        self.options = QComboBox()
        self.options.addItems(itemLabels)
        if initialItemLabel is not None:
            self.options.setCurrentIndex(itemLabels.index(initialItemLabel))
        layout.addWidget(self.options)
        hbar = hlayout()
        ok = QPushButton('Ok')
        hbar.addWidget(ok)
        cancel = QPushButton('Cancel')
        hbar.addWidget(cancel)
        hbar.addStretch(1)
        layout.addLayout(hbar)
        ok.clicked.connect(self.accept)
        cancel.clicked.connect(self.reject)

    def _currentItem(self):
        return self.options.currentText()

    @classmethod
    def run(cls, data, time, initialSceneName, parent):
        d = cls(data, initialSceneName, parent)
        d.exec_()
        if d.result() != QDialog.Accepted:
            return
        name = d.name.text()
        return cls._itemRowClass(name, d._currentItem(), time, time + 8.0)


class CreateShotDialog(CreateItemRowDialog):
    _itemRowClass = Shot

    @classmethod
    def run(cls, time, initialItemLabel, parent):
        return super(CreateShotDialog, cls).run(list(iterSceneNames()), time, initialItemLabel, parent)


class CreateEventDialog(CreateItemRowDialog):
    _itemRowClass = Event

    def __init__(self, clips, initialItemLabel=None, parent=None):
        self.clips = {clip.name: clip for clip in clips}
        super(CreateEventDialog, self).__init__(self.clips.keys(), initialItemLabel, parent)

    def _currentItem(self):
        return self.clips[super(CreateEventDialog, self)._currentItem()]
