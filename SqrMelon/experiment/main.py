import functools

from experiment.scenes import SceneList
from experiment.view3d import View3D
from qtutil import *
from experiment.curvemodel import HermiteCurve, HermiteKey, ELoopMode
from experiment.model import Clip, Shot, Event
from experiment.timelineview import TimelineView
from experiment.timer import Time
from experiment.widgets import ClipManager, CurveUI, EventModel, ShotModel, FilteredView
from experiment.projectutil import settings
from experiment.camerawidget import Camera


class DemoModel(QStandardItemModel):
    def evaluate(self, time):
        # type: (float) -> dict[str, float]
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


def evalCamera(camera, model, timer):
    __, anim = model.evaluate(timer.time)
    camera.setData(anim.get('uOrigin.x', 0.0), anim.get('uOrigin.y', 0.0), anim.get('uOrigin.z', 0.0), anim.get('uAngles.x', 0.0), anim.get('uAngles.y', 0.0), anim.get('uAngles.z', 0.0))


def eventChanged(eventManager, curveUI):
    for event in eventManager.selectionModel().selectedRows():
        curveUI.setEvent(event.data(Qt.UserRole + 1))
        return
    curveUI.setEvent(None)


def run():
    app = QApplication([])
    settings().setValue('currentproject', r'C:\Users\Henk\Documents\git\SqrMelon\SqrMelon\experiment\defaultproject')

    undoStack = QUndoStack()
    undoView = QUndoView(undoStack)

    clip0 = Clip('Clip 0')
    clip0.curves.appendRow(HermiteCurve('uOrigin.x', ELoopMode.Clamp, [HermiteKey(0.0, 0.0, 0.0, 0.0), HermiteKey(4.0, 1.0, 1.0, 1.0)]).items)
    clip0.curves.appendRow(HermiteCurve('uFlash', ELoopMode.Clamp, [HermiteKey(0.0, 1.0, 1.0, 1.0), HermiteKey(1.0, 0.0, 0.0, 0.0)]).items)

    clip1 = Clip('Clip 1')
    clip1.curves.appendRow(HermiteCurve('uOrigin.x', ELoopMode.Clamp, [HermiteKey(2.0, 0.0, 0.0, 0.0), HermiteKey(3.0, 1.0, 0.0, 0.0)]).items)
    clip1.curves.appendRow(HermiteCurve('uOrigin.y', ELoopMode.Clamp, [HermiteKey(0.0, 0.0, 1.0, 1.0), HermiteKey(1.0, 1.0, 1.0, 1.0)]).items)

    model = DemoModel()

    # TODO: Edits in these views are not undoable, but I would like to mass-edit in the future
    shotManager = FilteredView(undoStack, ShotModel(model))
    shotManager.model().appendRow(Shot('New Shot', 'example', 0.0, 4.0, 0).items)

    eventManager = FilteredView(undoStack, EventModel(model))
    eventManager.model().appendRow(Event('New event', clip0, 0.0, 4.0, 1.0, 0.0, 2).items)
    eventManager.model().appendRow(Event('New event', clip0, 0.0, 1.0, 1.0, 0.0, 1).items)
    eventManager.model().appendRow(Event('New event', clip1, 1.0, 2.0, 0.5, 0.0, 1).items)

    # changing the model contents seems to mess with the column layout stretch
    model.rowsInserted.connect(shotManager.updateSections)
    model.rowsInserted.connect(eventManager.updateSections)
    model.rowsRemoved.connect(shotManager.updateSections)
    model.rowsRemoved.connect(eventManager.updateSections)

    eventManager.model().appendRow(Event('New event', clip0, 2.0, 4.0, 0.25, 0.0, 1).items)

    clipManager = ClipManager(eventManager, undoStack)
    clipManager.model().appendRow(clip0.items)
    clipManager.model().appendRow(clip1.items)

    timer = Time()
    # TODO: Curve renames and loop mode changes are not undoable
    curveUI = CurveUI(timer, eventManager, clipManager, undoStack)
    eventManager.selectionChange.connect(functools.partial(eventChanged, eventManager, curveUI))
    eventTimeline = TimelineView(timer, undoStack, model, (shotManager.selectionModel(), eventManager.selectionModel()))

    camera = Camera()
    camera.requestAnimatedCameraPosition.connect(functools.partial(evalCamera, camera, model, timer))
    timer.changed.connect(camera.followAnimation)

    view = View3D(camera, model, timer)
    camera.edited.connect(view.repaint)
    timer.changed.connect(view.repaint)

    mainWindow = QMainWindowState(settings())
    mainWindow.setDockNestingEnabled(True)
    mainWindow.createDockWidget(undoView)
    mainWindow.createDockWidget(clipManager)
    mainWindow.createDockWidget(curveUI)
    mainWindow.createDockWidget(shotManager, name='Shots')
    mainWindow.createDockWidget(eventManager, name='Events')
    mainWindow.createDockWidget(eventTimeline)
    mainWindow.createDockWidget(SceneList())
    mainWindow.createDockWidget(camera)
    mainWindow.createDockWidget(view)

    mainWindow.show()
    # makes sure qt cleans up & python stops after closing the main window; https://stackoverflow.com/questions/39304366/qobjectstarttimer-qtimer-can-only-be-used-with-threads-started-with-qthread
    mainWindow.setAttribute(Qt.WA_DeleteOnClose)

    app.exec_()


if __name__ == '__main__':
    run()
