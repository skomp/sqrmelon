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


class CreateShotDialog(QDialog):
    def __init__(self, initialSceneName=None, parent=None):
        super(CreateShotDialog, self).__init__(parent)
        layout = vlayout()
        self.setLayout(layout)
        self.name = QLineEdit()
        layout.addWidget(self.name)
        self.scene = QComboBox()
        items = list(iterSceneNames())
        self.scene.addItems(items)
        if initialSceneName is not None:
            self.scene.setCurrentIndex(items.index(initialSceneName))
        layout.addWidget(self.scene)
        hbar = hlayout()
        ok = QPushButton('Ok')
        hbar.addWidget(ok)
        cancel = QPushButton('Cancel')
        hbar.addWidget(cancel)
        hbar.addStretch(1)
        layout.addLayout(hbar)
        ok.clicked.connect(self.accept)
        cancel.clicked.connect(self.reject)

    @staticmethod
    def run(time, initialSceneName=None, parent=None):
        d = CreateShotDialog(initialSceneName, parent)
        d.exec_()
        if d.result() != QDialog.Accepted:
            return
        name = d.name.text()
        sceneName = d.scene.currentText()
        return Shot(name, sceneName, time, time + 8.0, 0)
