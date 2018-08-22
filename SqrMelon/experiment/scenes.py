import json

import fileutil
from experiment.projectutil import iterSceneNames, scenesFolder, iterPipelineNames, publicStitches, sceneStitches, pipelineFolder, sceneStitchesSource
from qtutil import *
import icons
from send2trash import send2trash
import subprocess

SCENE_EXT = '.json'


class SceneList(QWidget):
    currentChanged = pyqtSignal(QStandardItem)
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
        self.view.setModel(QStandardItemModel())
        self.view.activated.connect(self.__onOpenFile)
        self.view.setEditTriggers(self.view.NoEditTriggers)
        main.addWidget(self.view)
        main.setStretch(1, 1)
        self.view.selectionModel().currentChanged.connect(self.__onCurrentChanged)

        self.view.setContextMenuPolicy(Qt.CustomContextMenu)
        self.view.customContextMenuRequested.connect(self.__contextMenu)
        self.contextMenu = QMenu()
        action = self.contextMenu.addAction('Show in explorer')
        action.triggered.connect(self.__showInExplorer)
        # action = self.contextMenu.addAction('Create shot')
        # action.triggered.connect(self.__createShot)
        self.__contextMenuItem = None

        self.updateWithCurrentProject()

    def selectSceneWithName(self, name):
        items = self.view.model().findItems(name)
        if items:
            self.view.setExpanded(items[0].index(), True)
            self.view.selectionModel().select(items[0].index(), QItemSelectionModel.ClearAndSelect)

    # def __createShot(self):
    #    for idx in self.view.selectionModel().selectedIndexes():
    #        item = self.view.model().itemFromIndex(idx)
    #        self.requestCreateShot.emit(item.text())
    #        return

    def __contextMenu(self, pos):
        index = self.view.indexAt(pos)
        if not index.isValid():
            return
        item = self.view.model().itemFromIndex(index)
        self.__contextMenuItem = item
        self.contextMenu.popup(self.view.mapToGlobal(pos))

    def __itemPath(self, item):
        if item.parent():
            return os.path.join(scenesFolder(), item.parent().text(), item.text() + '.glsl')
        else:
            return os.path.join(scenesFolder(), item.text())

    def __showInExplorer(self):
        if self.__contextMenuItem is None:
            return
        subprocess.Popen('explorer /select,"%s"' % self.__itemPath(self.__contextMenuItem))

    def __onOpenFile(self, current):
        if not current.parent().isValid():
            return
        item = self.view.model().itemFromIndex(current)
        os.startfile(self.__itemPath(item))

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
            filtered = {path.lower(): path for path in publicStitches(pipelineName)}
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
        self.view.model().appendRow(item)
        filtered = {path.lower(): path for path in sceneStitches(sceneName)}
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
        for sitchName in sceneStitchesSource(pipeline):
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
