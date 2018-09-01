import functools
import json
import fileutil
from experiment.projectutil import pipelineFolder, scenesFolder, iterPipelineNames, iterSceneStitches, iterSceneNames, SCENE_EXT, sceneDefaultChannels, iterPublicStitches
from qtutil import *
import icons
from send2trash import send2trash
import subprocess


class SceneList(QWidget):
    currentChanged = pyqtSignal(QStandardItem)
    requestCreateShot = pyqtSignal(str)
    requestCreateClip = pyqtSignal(dict, str)
    requestCreateShot = pyqtSignal(str)

    def __init__(self):
        super(SceneList, self).__init__()

        main = vlayout()
        self.setLayout(main)
        belt = hlayout()

        addScene = QPushButton(icons.get('Add Image'), '')
        addScene.clicked.connect(self.__onAddScene)
        addScene.setIconSize(QSize(24, 24))
        addScene.setToolTip('Add scene')
        addScene.setStatusTip('Add scene')
        belt.addWidget(addScene)

        delScene = QPushButton(icons.get('Remove Image'), '')
        delScene.clicked.connect(self.__onDeleteScene)
        delScene.setIconSize(QSize(24, 24))
        delScene.setToolTip('Delete scene')
        delScene.setStatusTip('Delete scene')
        belt.addWidget(delScene)

        belt.addStretch(1)
        main.addLayout(belt)

        self.view = QTreeView()
        self.view.header().hide()
        self.view.setModel(QStandardItemModel())
        self.view.activated.connect(self.__onOpenFile)
        self.view.setEditTriggers(self.view.NoEditTriggers)
        main.addWidget(self.view)
        main.setStretch(1, 1)
        self.view.selectionModel().currentChanged.connect(self.__onCurrentChanged)

        self.view.setContextMenuPolicy(Qt.CustomContextMenu)
        self.view.customContextMenuRequested.connect(self.__contextMenu)

        self.contextMenu = QMenu()

        self.updateWithCurrentProject()

    def __requestClip(self, item, isMaster=False):
        sceneName = item.text()
        self.requestCreateClip.emit(sceneDefaultChannels(sceneName, isMaster), sceneName)
    def __requestShot(self, item):
        self.requestCreateShot.emit(item.text())

    def selectSceneWithName(self, name):
        items = self.view.model().findItems(name)
        if items:
            self.view.setExpanded(items[0].index(), True)
            self.view.selectionModel().select(items[0].index(), QItemSelectionModel.ClearAndSelect)

    def __contextMenu(self, pos):
        index = self.view.indexAt(pos)
        if not index.isValid():
            return
        item = self.view.model().itemFromIndex(index)

        self.contextMenu.clear()
        action = self.contextMenu.addAction('Show in explorer')
        action.triggered.connect(functools.partial(self.__showInExplorer, item))

        if not item.parent() and item.text()[0] != ':':
            action = self.contextMenu.addAction('Create clip')
            action.triggered.connect(functools.partial(self.__requestClip, item))
            action = self.contextMenu.addAction('Create master clip')
            action.triggered.connect(functools.partial(self.__requestClip, item, True))
            action = self.contextMenu.addAction('Create shot')
            action.triggered.connect(functools.partial(self.__requestShot, item))

        self.contextMenu.popup(self.view.mapToGlobal(pos))

    def __showInExplorer(self, item):
        subprocess.Popen('explorer /select,"%s"' % item.data())

    def __onOpenFile(self, current):
        if not current.parent().isValid():
            return
        item = self.view.model().itemFromIndex(current)
        os.startfile(item.data())

    def __onCurrentChanged(self, current, __):
        if not current.parent().isValid():
            self.currentChanged.emit(self.view.model().itemFromIndex(current))

    def __onDeleteScene(self):
        if QMessageBox.warning(self, 'Deleting scene(s)', 'This action is not undoable! Continue?', QMessageBox.Yes | QMessageBox.No) != QMessageBox.Yes:
            return
        rows = []
        for idx in self.view.selectionModel().selectedIndexes():
            rows.append(idx.row())
            item = self.view.model().itemFromIndex(idx)
            sceneName = str(item.text())
            sceneDir = os.path.join(scenesFolder(), sceneName)
            sceneFile = sceneDir + SCENE_EXT
            send2trash(sceneFile)
            send2trash(sceneDir)
        rows.sort()
        for row in rows[::-1]:
            self.view.model().removeRow(row)

    def updateWithCurrentProject(self):
        self.setEnabled(True)
        self.clear()
        self.initShared()
        for scene in iterSceneNames():
            self.appendSceneItem(scene)

    def initShared(self):
        for pipelineName in iterPipelineNames():
            item = QStandardItem(':' + pipelineName)
            item.setData(os.path.join(pipelineFolder(), pipelineName))
            filtered = {path.lower(): path for path in iterPublicStitches(pipelineName)}
            allPaths = (filtered[key] for key in sorted(filtered.keys()))
            for path in allPaths:
                name = os.path.splitext(os.path.basename(path))[0]
                sub = QStandardItem(name)
                sub.setData(path)
                item.appendRow(sub)
            if item.rowCount():
                self.view.model().appendRow(item)

    def appendSceneItem(self, sceneName):
        item = QStandardItem(sceneName)
        item.setData(os.path.join(scenesFolder(), sceneName))
        self.view.model().appendRow(item)
        filtered = {path.lower(): path for path in iterSceneStitches(sceneName)}
        allPaths = (filtered[key] for key in sorted(filtered.keys()))
        for path in allPaths:
            name = os.path.splitext(os.path.basename(path))[0]
            sub = QStandardItem(name)
            sub.setData(path)
            item.appendRow(sub)

    def clear(self):
        self.view.model().clear()

    def __onAddScene(self):
        # request user for a template if there are multiple options
        pipelines = list(iterPipelineNames())
        if not pipelines:
            QMessageBox.critical(self, 'Could not create scene', 'Can not add scenes to this project until a pipeline has been set up to base them off.')
            return

        if len(pipelines) > 1:
            pipeline = QInputDialog.getItem(self, 'Create scene', 'Select pipeline', pipelines, 0, False)
            if not pipeline[1] or not pipeline[0] in pipelines:
                return
            pipeline = pipeline[0]
        else:
            pipeline = pipelines[0]

        name = QInputDialog.getText(self, 'Create scene', 'Scene name')
        if not name[1]:
            return

        scenesPath = scenesFolder()
        outFile = os.path.join(scenesPath, name[0] + SCENE_EXT)
        outDir = os.path.join(scenesPath, name[0])
        if fileutil.exists(outFile):
            QMessageBox.critical(self, 'Could not create scene', 'A scene with name "%s" already exists. No scene was created.' % name[0])
            return

        if fileutil.exists(outDir):
            if QMessageBox.warning(self, 'Scene not empty', 'A folder with name "%s" already exists. Create scene anyways?' % name[0], QMessageBox.Ok | QMessageBox.Cancel) == QMessageBox.Cancel:
                return
        else:
            os.makedirs(outDir.replace('\\', '/'))

        # create scene
        with fileutil.edit(outFile) as fh:
            initialSceneContent = {'pipeline': 'default', 'camera': {'tx': 0.0, 'ty': 1.0, 'tz': -10.0, 'rx': 0.0, 'ry': 0.0, 'rz': 0.0}}
            json.dump(initialSceneContent, fh)

        # create files required per-scene as defined by the pipeline
        srcDir = os.path.join(pipelineFolder(), pipeline)
        for sitchName in sceneStitchNames(pipeline):
            # read source data if any
            src = os.path.join(srcDir, sitchName + '.glsl')
            text = ''
            if fileutil.exists(src):
                with fileutil.read(src) as fh:
                    text = fh.read()
            # create required shader stitch
            dst = os.path.join(outDir, sitchName + '.glsl')
            with fileutil.edit(dst) as fh:
                fh.write(text)

        self.appendSceneItem(name[0])
