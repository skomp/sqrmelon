import json
import sys
import fileutil
from experiment.projectutil import iterSceneNames, scenesFolder, iterPipelineNames, publicStitches, sceneStitches, pipelineFolder, sceneStitchesSource
from experiment.renderpipeline.model import EStitchScope
from qtutil import *
import icons
from send2trash import send2trash
import subprocess
from experiment.renderpipeline.fileio import deserializeGraph
from OpenGL.GL import *
from OpenGL.GL import shaders
import gl_shaders
from buffers import FrameBuffer, Texture

SCENE_EXT = '.json'


class PooledResource(object):
    _pool = {}

    @classmethod
    def pool(cls, key):
        if key in cls._pool:
            scene = cls._pool[key]
        else:
            scene = cls(key)
            cls._pool[key] = scene
        return scene


class ShaderPool(object):
    _instance = None

    def __init__(self):
        self.__cache = {}

        self.__errorDialog = QDialog()  # error log
        self.__errorDialog.setWindowTitle('Compile log')
        self.__errorDialog.setLayout(vlayout())
        self.__errorDialogText = QTextEdit()
        self.__errorDialog.layout().addWidget(self.__errorDialogText)
        hbar = hlayout()
        self.__errorDialog.layout().addLayout(hbar)
        hbar.addStretch(1)
        btn = QPushButton('Close')
        hbar.addWidget(btn)
        btn.clicked.connect(self.__errorDialog.accept)

    @classmethod
    def instance(cls):
        if cls._instance is None:
            cls._instance = cls()
        return cls._instance

    def compileProgram(self, vertCode, fragCode):
        """
        A compileProgram version with error dialogs
        """
        try:
            program = self.__cache.get((vertCode, fragCode), None)
            if program:
                return program
            # skip shader validation step on linux
            validate = 'linux' not in sys.platform.lower()
            program = gl_shaders.compileProgram(shaders.compileShader(vertCode, GL_VERTEX_SHADER),
                                                shaders.compileShader(fragCode, GL_FRAGMENT_SHADER),
                                                validate=validate)
            self.__cache[(vertCode, fragCode)] = program
            return program
        except RuntimeError, e:
            errors = e.args[0].split('\n')
            try:
                code = e.args[1][0].split('\n')
            except:
                print e.args
                # print 'pass: ' + passData.name
                print 'fragCode:'
                print fragCode
                return
            # html escape output
            errors = [Qt.escape(ln) for ln in errors]
            code = [Qt.escape(ln) for ln in code]
            log = []
            for error in errors:
                try:
                    lineNumber = int(error.split(' : ', 1)[0].rsplit('(')[-1].split(')')[0])
                except:
                    continue
                lineNumber -= 1
                log.append('<p><font color="red">%s</font><br/>%s<br/><font color="#081">%s</font><br/>%s</p>' % (
                    error, '<br/>'.join(code[lineNumber - 5:lineNumber]), code[lineNumber], '<br/>'.join(code[lineNumber + 1:lineNumber + 5])))
            self.__errorDialogText.setHtml('<pre>' + '\n'.join(log) + '</pre>')
            self.__errorDialog.setGeometry(100, 100, 800, 600)
            self.__errorDialog.exec_()
            return


class Shader(PooledResource):
    def __init__(self, stitches):
        self.watcher = QFileSystemWatcher()
        for stitch in stitches:
            self.watcher.addPath(stitch)
        self.watcher.fileChanged.connect(self.invalidate)

        self.__stitches = stitches
        self.__program = None

    STATIC_VERT = '#version 410\nout vec2 vUV;void main(){gl_Position=vec4(step(1,gl_VertexID)*step(-2,-gl_VertexID)*2-1,gl_VertexID-gl_VertexID%2-1,0,1);vUV=gl_Position.xy*.5+.5;}'
    PASS_THROUGH_FRAG = '#version 410\nin vec2 vUV;uniform vec4 uColor;uniform sampler2D uImages[1];out vec4 outColor0;void main(){outColor0=uColor*texture(uImages[0], vUV);}'

    @property
    def program(self):
        if self.__program is None:
            code = []
            for stitch in self.__stitches:
                with open(stitch) as fh:
                    code.append(fh.read())
            self.__program = ShaderPool.instance().compileProgram(Shader.STATIC_VERT, '\n'.join(code))
        return self.__program

    def invalidate(self, changedPath):
        self.watcher.addPath(changedPath)
        # reset internal data
        self.__program = None


class Pipeline(PooledResource):
    def __init__(self, name):
        self.name = name
        self.pipelineDir = os.path.join(pipelineFolder(), self.name)
        pipelineFile = self.pipelineDir + '.json'

        self.watcher = QFileSystemWatcher()
        self.watcher.addPath(pipelineFile)
        self.watcher.fileChanged.connect(self.invalidate)

        self.__tail = None

    @property
    def tail(self):
        if self.__tail is None:
            # load graph
            pipelineFile = self.pipelineDir + '.json'
            with open(pipelineFile) as fh:
                graph = deserializeGraph(fh)
            # find a node with outputs that are not connected
            for node in graph:
                for output in node.outputs:
                    if not output.connections:
                        self.__tail = node
                        break
                else:
                    continue
                break
        assert self.__tail
        return self.__tail

    def invalidate(self, changedPath):
        self.watcher.addPath(changedPath)
        # reset internal data
        self.__tail = None


class FullScreenRectSingleton(object):
    _instance = None

    def __init__(self):
        self._vao = glGenVertexArrays(1)

    def draw(self):
        # I don't bind anything, no single buffer or VAO is generated, there are no geometry shaders and no transform feedback systems
        # according to the docs there is no reason why glDrawArrays wouldn't work.
        glBindVertexArray(self._vao)  # glBindVertexArray(0) doesn't work either
        glDrawArrays(GL_TRIANGLE_FAN, 0, 4)

    @classmethod
    def instance(cls):
        if cls._instance is None:
            cls._instance = cls()
        return cls._instance


class BufferPool(object):
    _pool = []

    def __init__(self, w, h, numOutputs):
        self.buffer = FrameBuffer(w, h)
        for i in xrange(numOutputs):
            self.buffer.addTexture(Texture(Texture.HALF_COLOR, w, h))
        self.inUse = False
        BufferPool._pool.append(self)

    @classmethod
    def get(cls, w, h, numOutputs):
        for buffer in BufferPool._pool:
            if buffer.inUse:
                continue
            if buffer.buffer.width == w and buffer.buffer.height == h and len(buffer.buffer.textures()) == numOutputs:
                return buffer
        return BufferPool(w, h, numOutputs)


class Scene(PooledResource):
    def __init__(self, name):
        self.sceneDir = os.path.join(scenesFolder(), name)
        with open(self.sceneDir + SCENE_EXT) as fh:
            self.pipeline = Pipeline.pool(json.load(fh)['pipeline'])

    def render(self, screenResolution, uniforms):
        renderBuffers = {}
        tail = self.pipeline.tail
        self.renderNode(tail, screenResolution, uniforms, renderBuffers)

    def renderNode(self, node, screenResolution, uniforms, renderBuffers):
        # recursively render dependencies
        inputs = []
        for input in node.inputs:
            if input.connections:
                source = input.connections[0].node
                colorBufferIndex = source.outputs.index(input.connections[0])
                r = renderBuffers.get(source, None)
                if r is None:
                    # this node was not yet rendered
                    inputBuffer = self.renderNode(source, screenResolution, uniforms, renderBuffers)
                    refCount = 0
                else:
                    inputBuffer = r[0]
                    refCount = r[1]
                renderBuffers[node] = inputBuffer, refCount
                inputs.append((inputBuffer, input.name, colorBufferIndex, node))

        # TODO: cache the stitch paths in the scene & invalidate when the scene's pipeline changes (the pipeline itself, or which pipeline this scene uses)
        stitchPaths = []
        for stitch in node.stitches:
            if stitch.scope == EStitchScope.Scene:
                stitchPaths.append(os.path.join(self.sceneDir, stitch.name + '.glsl'))
            else:
                stitchPaths.append(os.path.join(self.pipeline.pipelineDir, stitch.name + '.glsl'))
        program = Shader.pool(tuple(stitchPaths)).program

        # acquire buffer
        w, h = node.outputs[0].size, node.outputs[0].size
        if w < 0:
            w, h = screenResolution[0] / -w, screenResolution[1] / -h
        buffer = BufferPool.get(w, h, len(node.outputs))
        buffer.inUse = True
        buffer.buffer.use()

        glUseProgram(program)

        # bind inputs
        for i, entry in enumerate(inputs):
            glActiveTexture(GL_TEXTURE0 + i)
            inputBuffer, name, colorBufferIndex, __ = entry
            list(inputBuffer.buffer.textures())[colorBufferIndex].use()
            glUniform1i(glGetUniformLocation(program, name), colorBufferIndex)

        # apply uniforms
        for key, value in uniforms.iteritems():
            if isinstance(value, float):
                glUniform1f(glGetUniformLocation(program, key), value)

            elif isinstance(value, int):
                glUniform1i(glGetUniformLocation(program, key), value)

            elif hasattr(value, '__iter__'):
                if len(value) == 1:
                    glUniform1f(glGetUniformLocation(program, key), *value)
                elif len(value) == 2:
                    glUniform2f(glGetUniformLocation(program, key), *value)
                elif len(value) == 3:
                    glUniform3f(glGetUniformLocation(program, key), *value)
                elif len(value) == 4:
                    glUniform4f(glGetUniformLocation(program, key), *value)
                elif len(value) == 9:
                    glUniformMatrix3fv(glGetUniformLocation(program, key), 1, False, value)
                elif len(value) == 16:
                    glUniformMatrix4fv(glGetUniformLocation(program, key), 1, False, value)
                #elif len(value) == 12:
                #    glUniformMatrix4x3fv(glGetUniformLocation(program, key), 1, False, value)

        FullScreenRectSingleton.instance().draw()

        # free inputs
        for inputBuffer, __, __, node in inputs:
            refCount = renderBuffers[node][1] - 1
            renderBuffers[node] = inputBuffer, refCount
            if refCount <= 0:
                inputBuffer.inUse = False

        return buffer


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
