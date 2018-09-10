# TODO: Save project & ask to save on exit

# TODO: 3D view should adhere to some aspect ratio, based on user configured resolution
# TODO: Resolution factor selector, if mode is not "viewport size" image should be rendered at target and rescaled to fit window, serves as a performance test as well; if window is floating add "resize window" button to auto-size it to the underlying buffer size
# TODO: No signal image

# TODO: Record button
# TODO: Copy paste support
# TODO: There are still some abstract functions and other TODOs in widgets.py

import functools
import json
from experiment.demomodel import DemoModel
from experiment.modelbase import UndoableModel
from experiment.timelineview import TimelineManager
from view3d import View3D
from experiment.scenelist import SceneList
from qtutil import *
from experiment.curvemodel import HermiteCurve, HermiteKey, ELoopMode, ETangentMode
from experiment.model import Clip, Event, Shot
from experiment.timer import Time
from experiment.widgets import CurveUI, ClipUI, ShotManager, EventManager
from experiment.projectutil import settings
from experiment.camerawidget import Camera


def evalCamera(camera, model, timer):
    __, anim = model.evaluate(timer.time)
    camera.setData(anim.get('uOrigin.x', 0.0), anim.get('uOrigin.y', 0.0), anim.get('uOrigin.z', 0.0), anim.get('uAngles.x', 0.0), anim.get('uAngles.y', 0.0), anim.get('uAngles.z', 0.0))


def eventChanged(iterSelectedRows, curveUI):
    for event in iterSelectedRows():
        curveUI.setEvent(event.data(Qt.UserRole + 1))
        return
    curveUI.setEvent(None)


def openProjectDialog():
    """
    Prompts user to open a project json file and returns True if a project was succefully opened.
    """
    res = QFileDialog.getOpenFileName(None, 'Open project', os.path.dirname(os.path.abspath(__file__)), 'Project files (*.json)')
    if res:
        with open(res) as fh:
            data = json.load(fh)
        if 'Identifier' in data and data['Identifier'] == 'SqrMelonProject':
            settings().setValue('currentproject', res)
            return res


class ProjectManager(object):
    def __init__(self, undoStack, demoModel, clipsModel, eventManager, shotManager, timer, timelineManager):
        self.__undoStack = undoStack
        self.__demoModel = demoModel
        self.__clipsModel = clipsModel
        self.__eventManager = eventManager
        self.__shotManager = shotManager
        self.__timelineManager = timelineManager
        self.__timer = timer

    def open(self):
        currentProject = openProjectDialog()
        if not currentProject:
            # no project opened
            return False
        self.reload(currentProject)
        return True

    def reload(self, currentProject):
        with open(currentProject) as fh:
            data = json.load(fh)

        # load clips
        clips = {}
        for clipData in data['Clips']:
            clip = Clip(clipData['Name'], self.__undoStack)
            clips[clip.name] = clip

            # load curves
            for curveData in clipData['Curves']:
                keyData = curveData['Keys']
                keys = []
                for i in xrange(0, len(keyData), 6):
                    key = HermiteKey(keyData[i],
                                     keyData[i + 1],
                                     keyData[i + 2],
                                     keyData[i + 3],
                                     ETangentMode(keyData[i + 4]),
                                     ETangentMode(keyData[i + 5]))
                    keys.append(key)
                curve = HermiteCurve(curveData['Name'], ELoopMode(curveData['LoopMode']), keys)
                clip.curves.appendRow(curve.items)
            self.__clipsModel.appendRow(clip.items)

        # load events
        for shotData in data['Shots']:
            self.__demoModel.appendRow(Shot(shotData['Name'],
                                            shotData['Scene'],
                                            float(shotData['Start']),
                                            float(shotData['End']),
                                            int(shotData['Track'])).items)

        for eventData in data['Events']:
            self.__demoModel.appendRow(Event(eventData['Name'],
                                             clips[eventData['Clip']],
                                             float(eventData['Start']),
                                             float(eventData['End']),
                                             float(eventData['Speed']),
                                             float(eventData['Roll']),
                                             int(eventData['Track'])).items)

        # restore other settings
        self.__timer.loopStart = data['LoopStart']
        self.__timer.loopEnd = data['LoopEnd']
        self.__timer.bpm = data['BPM']

        # Fix widgets after content change
        self.__timelineManager.view.frameAll()
        self.__shotManager.view.updateSections()
        self.__eventManager.view.updateSections()


def run():
    app = QApplication([])

    # initialze project sensitive elements
    # these elements are pretty "global" in that they are referenced by most widgets
    undoStack = QUndoStack()
    timer = Time()
    demoModel = DemoModel(timer, undoStack)

    # initialize objects that have the containers for project-level seriaized data
    clipsModel = UndoableModel(undoStack)

    def iterItemRows(model):
        # TODO: this pattern appears quite a lot, move to be a member of a model base class
        for row in xrange(model.rowCount()):
            yield model.index(row, 0).data(Qt.UserRole + 1)

    iterClips = functools.partial(iterItemRows, clipsModel)

    eventManager = EventManager(undoStack, demoModel, timer, iterClips)
    shotManager = ShotManager(undoStack, demoModel, timer)
    timelineManager = TimelineManager(timer, undoStack, demoModel, (shotManager.view.selectionModel(), eventManager.view.selectionModel()))
    projectManager = ProjectManager(undoStack, demoModel, clipsModel, eventManager, shotManager, timer, timelineManager)

    value = settings().value('currentproject', None)
    if value is None or not os.path.exists(value):
        if not projectManager.open():
            # no project opened
            return
    else:
        projectManager.reload(value)

    # main widgets
    undoView = QUndoView(undoStack)

    clips = ClipUI(clipsModel, undoStack, demoModel, timer, eventManager.view.selectionChange, eventManager.firstSelectedEvent)
    sceneList = SceneList(timer, clips.createClip, demoModel.addShot)
    curveUI = CurveUI(timer, clips.manager.selectionChange, clips.manager.firstSelectedItem, eventManager.firstSelectedEventWithClip, undoStack)

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
    mainWindow.createDockWidget(timelineManager)
    mainWindow.createDockWidget(sceneList)
    mainWindow.createDockWidget(camera)
    mainWindow.createDockWidget(view)

    # set up menu actions & shortcuts
    menuBar = QMenuBar()
    mainWindow.setMenuBar(menuBar)

    fileMenu = menuBar.addMenu('&File')
    openProj = fileMenu.addAction('&Open project')
    openProj.triggered.connect(projectManager.open)

    editMenu = menuBar.addMenu('&Edit')

    undo = undoStack.createUndoAction(editMenu, '&Undo ')
    editMenu.addAction(undo)
    undo.setShortcut(QKeySequence(QKeySequence.Undo))
    undo.setShortcutContext(Qt.ApplicationShortcut)

    redo = undoStack.createRedoAction(editMenu, '&Redo ')
    editMenu.addAction(redo)
    redo.setShortcut(QKeySequence(QKeySequence.Redo))
    redo.setShortcutContext(Qt.ApplicationShortcut)

    keyCamera = editMenu.addAction('&Key camera')
    keyCamera.setShortcut(QKeySequence(Qt.Key_K))
    keyCamera.setShortcutContext(Qt.ApplicationShortcut)

    toggleCamera = editMenu.addAction('&Toggle camera control')
    toggleCamera.setShortcut(QKeySequence(Qt.Key_T))
    toggleCamera.setShortcutContext(Qt.ApplicationShortcut)

    resetCamera = editMenu.addAction('Snap came&ra to animation')
    resetCamera.setShortcuts(QKeySequence(Qt.Key_R))
    resetCamera.setShortcutContext(Qt.ApplicationShortcut)

    # connection widgets together
    timer.loopStartChanged.connect(timelineManager.view.repaint)
    timer.loopEndChanged.connect(timelineManager.view.repaint)
    
    # changing the model contents seems to mess with the column layout stretch
    demoModel.rowsInserted.connect(shotManager.view.updateSections)
    demoModel.rowsInserted.connect(eventManager.view.updateSections)
    demoModel.rowsRemoved.connect(shotManager.view.updateSections)
    demoModel.rowsRemoved.connect(eventManager.view.updateSections)

    demoModel.dataChanged.connect(curveUI.view.repaint)

    eventManager.view.selectionChange.connect(functools.partial(eventChanged, eventManager.view.selectionModel().selectedRows, curveUI))
    camera.requestAnimatedCameraPosition.connect(functools.partial(evalCamera, camera, demoModel, timer))

    # when animating, the camera will see about animation
    # if it is not set to follow animation it will do nothing
    # else it will emit requestAnimatedCameraPosition, so that the internal state will match
    timer.timeChanged.connect(camera.followAnimation)

    # when the camera is changed  through flying (WASD, Mouse) or through the input widgets, it will emit an edited event, signaling repaint
    camera.edited.connect(view.repaint)
    # when the time changes, the camera is connected first so animation is applied, then we still have to manually trigger a repaint here
    timer.timeChanged.connect(view.repaint)

    keyCamera.triggered.connect(functools.partial(curveUI.keyCamera, camera))
    toggleCamera.triggered.connect(camera.toggle)
    resetCamera.triggered.connect(camera.copyAnim)

    mainWindow.show()
    # makes sure qt cleans up & python stops after closing the main window; https://stackoverflow.com/questions/39304366/qobjectstarttimer-qtimer-can-only-be-used-with-threads-started-with-qthread
    mainWindow.setAttribute(Qt.WA_DeleteOnClose)

    app.exec_()


if __name__ == '__main__':
    run()
