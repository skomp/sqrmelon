# TODO: Press F and A to frame selection / all in timeline view
# TODO: Delete shots and events from TimelineView with keyboard
# TODO: Loop range and curve editor time changes are incorrect
import functools
import icons
from experiment.demomodel import DemoModel
from view3d import View3D
from experiment.scenelist import SceneList
from qtutil import *
from experiment.curvemodel import HermiteCurve, HermiteKey, ELoopMode
from experiment.model import Clip, Event
from experiment.timelineview import TimelineView
from experiment.timer import Time
from experiment.widgets import CurveUI, EventModel, ClipUI, EventView, ShotManager
from experiment.projectutil import settings
from experiment.camerawidget import Camera


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
    settings().setValue('currentproject', os.path.join(os.path.dirname(os.path.abspath(__file__)), 'defaultproject'))

    undoStack = QUndoStack()
    undoView = QUndoView(undoStack)

    clip0 = Clip('Clip 0', undoStack)
    clip0.curves.appendRow(HermiteCurve('uOrigin.x', ELoopMode.Clamp, [HermiteKey(0.0, 0.0, 0.0, 0.0), HermiteKey(4.0, 1.0, 1.0, 1.0)]).items)
    clip0.curves.appendRow(HermiteCurve('uFlash', ELoopMode.Clamp, [HermiteKey(0.0, 1.0, 1.0, 1.0), HermiteKey(1.0, 0.0, 0.0, 0.0)]).items)

    clip1 = Clip('Clip 1', undoStack)
    clip1.curves.appendRow(HermiteCurve('uOrigin.x', ELoopMode.Clamp, [HermiteKey(2.0, 0.0, 0.0, 0.0), HermiteKey(3.0, 1.0, 0.0, 0.0)]).items)
    clip1.curves.appendRow(HermiteCurve('uOrigin.y', ELoopMode.Clamp, [HermiteKey(0.0, 0.0, 1.0, 1.0), HermiteKey(1.0, 1.0, 1.0, 1.0)]).items)

    demoModel = DemoModel(undoStack)

    timer = Time()
    sceneList = SceneList(timer)

    shotManager = ShotManager(undoStack, demoModel, timer)

    deleteEvent = QPushButton(icons.get('Curves Delete-48'), '')
    deleteEvent.setToolTip('Delete selected events')
    deleteEvent.setStatusTip('Delete selected events')

    eventManager = EventView(undoStack, EventModel(demoModel))
    eventManager.model().appendRow(Event('New event', clip0, 0.0, 4.0, 1.0, 0.0, 2).items)
    eventManager.model().appendRow(Event('New event', clip0, 0.0, 1.0, 1.0, 0.0, 1).items)
    eventManager.model().appendRow(Event('New event', clip1, 1.0, 2.0, 0.5, 0.0, 1).items)

    # changing the model contents seems to mess with the column layout stretch
    demoModel.rowsInserted.connect(shotManager.view.updateSections)
    demoModel.rowsInserted.connect(eventManager.updateSections)
    demoModel.rowsRemoved.connect(shotManager.view.updateSections)
    demoModel.rowsRemoved.connect(eventManager.updateSections)

    eventManager.model().appendRow(Event('New event', clip0, 2.0, 4.0, 0.25, 0.0, 1).items)

    clips = ClipUI(eventManager.selectionChange, eventManager.firstSelectedEvent, undoStack)
    clips.manager.model().appendRow(clip0.items)
    clips.manager.model().appendRow(clip1.items)

    sceneList.requestCreateClip.connect(clips.createClipWithDefaults)

    sceneList.requestCreateShot.connect(demoModel.addShot)
    clips.requestEvent.connect(functools.partial(demoModel.createEvent, timer))

    curveUI = CurveUI(timer, clips.manager.selectionChange, clips.manager.firstSelectedItem, eventManager.firstSelectedEventWithClip, undoStack)
    eventManager.selectionChange.connect(functools.partial(eventChanged, eventManager, curveUI))
    eventTimeline = TimelineView(timer, undoStack, demoModel, (shotManager.view.selectionModel(), eventManager.selectionModel()))

    camera = Camera()
    camera.requestAnimatedCameraPosition.connect(functools.partial(evalCamera, camera, demoModel, timer))
    # when animating, the camera will see about animation
    # if it is not set to follow animation it will do nothing
    # else it will emit requestAnimatedCameraPosition, so that the internal state will match
    timer.changed.connect(camera.followAnimation)

    view = View3D(camera, demoModel, timer)
    # when the camera is changed  through flying (WASD, Mouse) or through the input widgets, it will emit an edited event, signaling repaint
    camera.edited.connect(view.repaint)
    # when the time changes, the camera is connected first so animation is applied, then we still have to manually trigger a repaint here
    timer.changed.connect(view.repaint)

    mainWindow = QMainWindowState(settings())
    mainWindow.setDockNestingEnabled(True)
    mainWindow.createDockWidget(undoView)
    mainWindow.createDockWidget(clips)
    mainWindow.createDockWidget(curveUI)
    mainWindow.createDockWidget(shotManager, name='Shots')
    mainWindow.createDockWidget(eventManager, name='Events')
    mainWindow.createDockWidget(eventTimeline)
    mainWindow.createDockWidget(sceneList)
    mainWindow.createDockWidget(camera)
    mainWindow.createDockWidget(view)

    menuBar = QMenuBar()
    mainWindow.setMenuBar(menuBar)
    editMenu = menuBar.addMenu('Edit')

    action = editMenu.addAction('&Key camera')
    action.setShortcut(QKeySequence(Qt.Key_K))
    action.setShortcutContext(Qt.ApplicationShortcut)
    action.triggered.connect(functools.partial(curveUI.keyCamera, camera))

    action = editMenu.addAction('&Toggle camera control')
    action.setShortcut(QKeySequence(Qt.Key_T))
    action.setShortcutContext(Qt.ApplicationShortcut)
    action.triggered.connect(camera.toggle)

    action = editMenu.addAction('Snap came&ra to animation')
    action.setShortcuts(QKeySequence(Qt.Key_R))
    action.setShortcutContext(Qt.ApplicationShortcut)
    action.triggered.connect(camera.copyAnim)

    mainWindow.show()
    # makes sure qt cleans up & python stops after closing the main window; https://stackoverflow.com/questions/39304366/qobjectstarttimer-qtimer-can-only-be-used-with-threads-started-with-qthread
    mainWindow.setAttribute(Qt.WA_DeleteOnClose)

    app.exec_()


if __name__ == '__main__':
    run()
