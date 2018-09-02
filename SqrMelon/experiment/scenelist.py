import functools
import json
import fileutil
from experiment.demomodel import CreateShotDialog
from experiment.projectutil import pipelineFolder, scenesFolder, iterPipelineNames, iterSceneStitches, iterSceneNames, SCENE_EXT, sceneDefaultChannels, iterPublicStitches, sceneStitchNames
from qtutil import *
import icons
from send2trash import send2trash
import subprocess


class SceneList(QWidget):
    currentChanged = pyqtSignal(QStandardItem)

    def __init__(self, timer, createClipCallable, createShotCallable):
        super(SceneList, self).__init__()

        self.__createShotCallable = createShotCallable
        self.__createClipCallable= createClipCallable
        self.__timer = timer

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

        self.__view = QTreeView()
        self.__view.header().hide()
        self.__view.setModel(QStandardItemModel())
        self.__view.activated.connect(self.__onOpenFile)
        self.__view.setEditTriggers(self.__view.NoEditTriggers)
        main.addWidget(self.__view)
        main.setStretch(1, 1)
        self.__view.selectionModel().currentChanged.connect(self.__onCurrentChanged)

        self.__view.setContextMenuPolicy(Qt.CustomContextMenu)
        self.__view.customContextMenuRequested.connect(self.__contextMenu)

        self.__contextMenu = QMenu()

        self.__updateWithCurrentProject()

    @property
    def view(self):
        return self.__view

    def __requestClip(self, item, isMaster=False):
        self.__createClipCallable(sceneDefaultChannels(item.text(), isMaster))

    def __requestShot(self, item):
        shot = CreateShotDialog.run(self.__timer.time, item.text(), self)
        if shot:
            self.__createShotCallable(shot)

    def selectSceneWithName(self, name):
        items = self.__view.model().findItems(name)
        if items:
            self.__view.setExpanded(items[0].index(), True)
            self.__view.selectionModel().select(items[0].index(), QItemSelectionModel.ClearAndSelect)

    def __contextMenu(self, pos):
        index = self.__view.indexAt(pos)
        if not index.isValid():
            return
        item = self.__view.model().itemFromIndex(index)

        self.__contextMenu.clear()
        action = self.__contextMenu.addAction('Show in explorer')
        action.triggered.connect(functools.partial(self._showInExplorer, item))

        if not item.parent() and item.text()[0] != ':':
            action = self.__contextMenu.addAction('Create clip')
            action.triggered.connect(functools.partial(self.__requestClip, item))
            action = self.__contextMenu.addAction('Create master clip')
            action.triggered.connect(functools.partial(self.__requestClip, item, True))
            action = self.__contextMenu.addAction('Create shot')
            action.triggered.connect(functools.partial(self.__requestShot, item))

        self.__contextMenu.popup(self.__view.mapToGlobal(pos))

    @staticmethod
    def _showInExplorer(item):
        subprocess.Popen('explorer /select,"%s"' % item.data())

    def __onOpenFile(self, current):
        if not current.parent().isValid():
            return
        item = self.__view.model().itemFromIndex(current)
        os.startfile(item.data())

    def __onCurrentChanged(self, current, __):
        if not current.parent().isValid():
            self.currentChanged.emit(self.__view.model().itemFromIndex(current))

    def __onDeleteScene(self):
        if QMessageBox.warning(self, 'Deleting scene(s)', 'This action is not undoable! Continue?', QMessageBox.Yes | QMessageBox.No) != QMessageBox.Yes:
            return
        rows = []
        for idx in self.__view.selectionModel().selectedIndexes():
            rows.append(idx.row())
            item = self.__view.model().itemFromIndex(idx)
            sceneName = str(item.text())
            sceneDir = os.path.join(scenesFolder(), sceneName)
            sceneFile = sceneDir + SCENE_EXT
            send2trash(sceneFile)
            send2trash(sceneDir)
        rows.sort()
        for row in rows[::-1]:
            self.__view.model().removeRow(row)

    def __updateWithCurrentProject(self):
        self.setEnabled(True)
        self.__clear()
        self.__initShared()
        for scene in iterSceneNames():
            self.__appendSceneItem(scene)

    def __initShared(self):
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
                self.__view.model().appendRow(item)

    def __appendSceneItem(self, sceneName):
        item = QStandardItem(sceneName)
        item.setData(os.path.join(scenesFolder(), sceneName))
        self.__view.model().appendRow(item)
        filtered = {path.lower(): path for path in iterSceneStitches(sceneName)}
        allPaths = (filtered[key] for key in sorted(filtered.keys()))
        for path in allPaths:
            name = os.path.splitext(os.path.basename(path))[0]
            sub = QStandardItem(name)
            sub.setData(path)
            item.appendRow(sub)

    def __clear(self):
        self.__view.model().clear()

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
        for stitchName in sceneStitchNames(pipeline):
            # read source data if any
            src = os.path.join(srcDir, stitchName + '.glsl')
            text = ''
            if fileutil.exists(src):
                with fileutil.read(src) as fh:
                    text = fh.read()
            # create required shader stitch
            dst = os.path.join(outDir, stitchName + '.glsl')
            with fileutil.edit(dst) as fh:
                fh.write(text)

        self.__appendSceneItem(name[0])
