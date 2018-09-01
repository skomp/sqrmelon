# TODO: Press F and A to frame selection / all in timeline view
# TODO: Delete shots and events from TimelineView with keyboard
# TODO: Loop range and curve editor time changes are incorrect
import functools
from experiment.demomodel import DemoModel
from view3d import View3D
from experiment.scenelist import SceneList
from qtutil import *
from experiment.curvemodel import HermiteCurve, HermiteKey, ELoopMode
from experiment.model import Clip, Event, Shot
from experiment.timelineview import TimelineView
from experiment.timer import Time
from experiment.widgets import CurveUI, ClipUI, ShotManager, EventManager
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

    # these elements are pretty "global" in that they are referenced by most widgets
    undoStack = QUndoStack()
    timer = Time()
    demoModel = DemoModel(undoStack)

    # main widgets
    undoView = QUndoView(undoStack)
    sceneList = SceneList(timer)
    shotManager = ShotManager(undoStack, demoModel, timer)

    def iterItemRows(model):
        for row in xrange(model.rowCount()):
            yield model.index(row, 0).data(Qt.UserRole + 1)

    eventManager = EventManager(undoStack, demoModel, timer)
    # TODO: passing in these callables is achieving the same as some of the "requestX" connections, perhaps we should settle on 1 mechanism (in which case the requestX actions feel less intuitive)
    clips = ClipUI(eventManager.view.selectionChange, eventManager.view.firstSelectedEvent, undoStack)
    # TODO: ClipUI context menu should use CreateEventDialog
    # TODO: Bi-directional connection between ClipsUI and EventManager... need to rething this as it's quite an ugly workaround for a required argument
    eventManager.iterClips = functools.partial(iterItemRows, clips.manager.model())

    curveUI = CurveUI(timer, clips.manager.selectionChange, clips.manager.firstSelectedItem, eventManager.view.firstSelectedEventWithClip, undoStack)
    eventTimeline = TimelineView(timer, undoStack, demoModel, (shotManager.view.selectionModel(), eventManager.view.selectionModel()))
    camera = Camera()

    # the 3D view is the only widget that references other widgets
    view = View3D(camera, demoModel, timer)

    # set up main window and dock widgets
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

    # set up menu actions & shortcuts
    menuBar = QMenuBar()
    mainWindow.setMenuBar(menuBar)

    editMenu = menuBar.addMenu('Edit')

    keyCamera = editMenu.addAction('&Key camera')
    keyCamera.setShortcut(QKeySequence(Qt.Key_K))
    keyCamera.setShortcutContext(Qt.ApplicationShortcut)

    toggleCamera = editMenu.addAction('&Toggle camera control')
    toggleCamera.setShortcut(QKeySequence(Qt.Key_T))
    toggleCamera.setShortcutContext(Qt.ApplicationShortcut)

    resetCamera = editMenu.addAction('Snap came&ra to animation')
    resetCamera.setShortcuts(QKeySequence(Qt.Key_R))
    resetCamera.setShortcutContext(Qt.ApplicationShortcut)

    # add test content
    clip0 = Clip('Clip 0', undoStack)
    clip0.curves.appendRow(HermiteCurve('uOrigin.x', ELoopMode.Clamp, [HermiteKey(0.0, 0.0, 0.0, 0.0), HermiteKey(4.0, 1.0, 1.0, 1.0)]).items)
    clip0.curves.appendRow(HermiteCurve('uFlash', ELoopMode.Clamp, [HermiteKey(0.0, 1.0, 1.0, 1.0), HermiteKey(1.0, 0.0, 0.0, 0.0)]).items)

    clip1 = Clip('Clip 1', undoStack)
    clip1.curves.appendRow(HermiteCurve('uOrigin.x', ELoopMode.Clamp, [HermiteKey(2.0, 0.0, 0.0, 0.0), HermiteKey(3.0, 1.0, 0.0, 0.0)]).items)
    clip1.curves.appendRow(HermiteCurve('uOrigin.y', ELoopMode.Clamp, [HermiteKey(0.0, 0.0, 1.0, 1.0), HermiteKey(1.0, 1.0, 1.0, 1.0)]).items)

    demoModel.appendRow(Shot('New Shot', 'example', 0.0, 4.0, 0).items)

    demoModel.appendRow(Event('New event', clip0, 0.0, 4.0, 1.0, 0.0, 2).items)
    demoModel.appendRow(Event('New event', clip0, 0.0, 1.0, 1.0, 0.0, 1).items)
    demoModel.appendRow(Event('New event', clip1, 1.0, 2.0, 0.5, 0.0, 1).items)
    demoModel.appendRow(Event('New event', clip0, 2.0, 4.0, 0.25, 0.0, 1).items)

    clips.manager.model().appendRow(clip0.items)
    clips.manager.model().appendRow(clip1.items)

    # connection widgets together
    # changing the model contents seems to mess with the column layout stretch
    demoModel.rowsInserted.connect(shotManager.view.updateSections)
    demoModel.rowsInserted.connect(eventManager.view.updateSections)
    demoModel.rowsRemoved.connect(shotManager.view.updateSections)
    demoModel.rowsRemoved.connect(eventManager.view.updateSections)

    sceneList.requestCreateClip.connect(clips.createClip)
    sceneList.requestCreateShot.connect(demoModel.addShot)
    clips.requestEvent.connect(functools.partial(demoModel.createEvent, timer))
    eventManager.view.selectionChange.connect(functools.partial(eventChanged, eventManager.view, curveUI))
    camera.requestAnimatedCameraPosition.connect(functools.partial(evalCamera, camera, demoModel, timer))

    # when animating, the camera will see about animation
    # if it is not set to follow animation it will do nothing
    # else it will emit requestAnimatedCameraPosition, so that the internal state will match
    timer.changed.connect(camera.followAnimation)

    # when the camera is changed  through flying (WASD, Mouse) or through the input widgets, it will emit an edited event, signaling repaint
    camera.edited.connect(view.repaint)
    # when the time changes, the camera is connected first so animation is applied, then we still have to manually trigger a repaint here
    timer.changed.connect(view.repaint)

    keyCamera.triggered.connect(functools.partial(curveUI.keyCamera, camera))
    toggleCamera.triggered.connect(camera.toggle)
    resetCamera.triggered.connect(camera.copyAnim)

    mainWindow.show()
    # makes sure qt cleans up & python stops after closing the main window; https://stackoverflow.com/questions/39304366/qobjectstarttimer-qtimer-can-only-be-used-with-threads-started-with-qthread
    mainWindow.setAttribute(Qt.WA_DeleteOnClose)

    app.exec_()


if __name__ == '__main__':
    run()
