from collections import OrderedDict
from glutil import *
import json
from buffers import Texture
from experiment.projectutil import pipelineFolder, scenesFolder, SCENE_EXT
from experiment.renderpipeline.fileio import deserializePipeline
from experiment.renderpipeline.model import EStitchScope
from experiment.util import FileSystemWatcher2


class Pipeline(PooledResource):
    """
    Lazily deserialized pipeline, invalidadtes on file change
    and pools to avoid data duplication.
    """

    def __init__(self, name):
        self.name = name
        self.pipelineDir = os.path.join(pipelineFolder(), self.name)
        pipelineFile = self.pipelineDir + '.json'

        self.watcher = FileSystemWatcher2([pipelineFile])
        self.watcher.fileChanged.connect(self.invalidate)

        self.__graph = None
        self.__tail = None
        self.__channels = None

    def invalidate(self, changedPath):
        self.__graph = None
        self.__tail = None
        self.__channels = None

    def iterStitchNames(self, scope):
        if self.__graph is None:
            self.__reloadInternalData()
        for node in self.__graph:
            for stitch in node.stitches:
                if stitch.scope == scope:
                    yield stitch.name

    def __reloadInternalData(self):
        # load graph
        pipelineFile = self.pipelineDir + '.json'
        data = deserializePipeline(pipelineFile)
        self.__graph = data['graph']
        self.__channels = data['channels']
        # find a node with outputs that are not connected
        for node in self.__graph:
            for output in node.outputs:
                if not output.connections:
                    self.__tail = node
                    break
            else:
                continue
            break
        assert self.__tail

    @property
    def channels(self):
        if self.__channels is None:
            self.__reloadInternalData()
        return self.__channels

    @property
    def tail(self):
        if self.__tail is None:
            self.__reloadInternalData()
        return self.__tail


class FrameBufferPool(FrameBuffer):
    """
    This is not a PooledResource subclass because we don't pool by key,
    we also pool by internal state (buffers can be in use and therefore not available to the request).
    """
    _pool = []
    _ref = {}
    _inUse = []

    @staticmethod
    def clear():
        del FrameBufferPool._pool[:]

    @staticmethod
    def resetRefCount():
        FrameBufferPool._ref.clear()
        del FrameBufferPool._inUse[:]

    @staticmethod
    def get(w, h, numOutputs):
        for buffer in FrameBufferPool._pool:
            if buffer in FrameBufferPool._inUse:
                continue
            if buffer.width() == w and buffer.height() == h and len(list(buffer.textures())) == numOutputs:
                return buffer
        return FrameBufferPool(w, h, numOutputs)

    def ref(self):
        FrameBufferPool._ref[self] = FrameBufferPool._ref.get(self, 0) + 1
        FrameBufferPool._inUse.append(self)

    def free(self):
        FrameBufferPool._ref[self] = FrameBufferPool._ref[self] - 1
        if FrameBufferPool._ref[self] == 0:
            del FrameBufferPool._ref[self]
            FrameBufferPool._inUse.remove(self)

    def __init__(self, w, h, numOutputs):
        super(FrameBufferPool, self).__init__(w, h)
        for i in xrange(numOutputs):
            self.addTexture(Texture(Texture.HALF_COLOR, w, h))
        FrameBufferPool._pool.append(self)


class ColorBufferInput(object):
    """
    Internal class used by renderNode to track what a buffer
    is being used for (& who rendered into it).
    """

    def __init__(self, inputName, frameBuffer, colorBufferIndex, sourceNode):
        # assuming frameBuffer was rendered into by sourceNode
        # we can use the frameBuffer.colorBuffers[colorBufferIndex]
        # ans assign it to the given uniform inputName

        # the uniform name that wants this input:
        self.inputName = inputName
        # which color buffer to get:
        self.frameBuffer = frameBuffer
        self.colorBufferIndex = colorBufferIndex
        # the node that we assume rendered (and currently owns) the framebuffer:
        self.sourceNode = sourceNode

    def colorBuffer(self):
        return list(self.frameBuffer.textures())[self.colorBufferIndex]


class Scene(PooledResource):
    """
    A renderable scene.
    Given a scene name if finds the pipeline and scene/ and public/ directories to load code from.
    render() will traverse the pipeline graph starting at the tail and finally output the result to screen.
    """

    def __init__(self, name):
        self.changed = Signal()

        self.sceneDir = os.path.join(scenesFolder(), name)
        # TODO: pool the scene file and watch for file changes ? probably not needed once channels can be edited from the UI
        with open(self.sceneDir + SCENE_EXT) as fh:
            data = json.load(fh, object_pairs_hook=OrderedDict)
            self.__channels = data['channels']
            self.pipeline = Pipeline.pool(data['pipeline'])

        self.pipeline.watcher.fileChanged.connect(self.__pipelineChanged)

        self.watcher = FileSystemWatcher2([])
        self.watcher.fileChanged.connect(self.emitChanged)
        self.__shaderCache = {}

    @property
    def channels(self):
        return self.__channels

    def emitChanged(self, *args):
        self.changed.emit()

    def __pipelineChanged(self):
        self.watcher.clear()
        self.__shaderCache.clear()

    def render(self, screenResolution, uniforms):
        renderBuffers = {}  # track what node rendered into what buffer
        FrameBufferPool.resetRefCount()

        tail = self.pipeline.tail
        finalBuffer = self.renderNode(tail, screenResolution, uniforms, renderBuffers)
        colorBuffer = finalBuffer.textures().next()
        drawColorBufferToScreen(colorBuffer, [0, 0, screenResolution[0], screenResolution[1]])

    def renderNode(self, node, screenResolution, uniforms, renderBuffers):
        # recursively render dependencies
        inputs = []
        for input in node.inputs:
            if not input.connections:
                continue
            # if an input has an incoming connection, we render the source of that connection
            # and take ownership of the buffer (so that the buffer pool does not allow it to be overwritten elsewhere, before we used the input data)
            source = input.connections[0].node
            colorBufferIndex = source.outputs.index(input.connections[0])
            # we track which nodes we've passed while rendering
            inputFrameBuffer = renderBuffers.get(source, None)
            if inputFrameBuffer is None:
                # this node was not yet rendered, we must render it and take ownership of the resuling framebuffer
                inputFrameBuffer = self.renderNode(source, screenResolution, uniforms, renderBuffers)
                renderBuffers[source] = inputFrameBuffer
            # increment the refcount to the input to signify we are using this buffer
            inputFrameBuffer.ref()
            # collect the color buffer to use
            inputs.append(ColorBufferInput(input.name, inputFrameBuffer, colorBufferIndex, source))

        shader = self.__shaderCache.get(node, None)
        if shader is None:
            stitchPaths = []
            for stitch in node.stitches:
                if stitch.scope == EStitchScope.Scene:
                    stitchPaths.append(os.path.join(self.sceneDir, stitch.name + '.glsl'))
                else:
                    stitchPaths.append(os.path.join(self.pipeline.pipelineDir, stitch.name + '.glsl'))
            shader = Shader.pool(tuple(stitchPaths))
            self.watcher.addNewPaths(stitchPaths)
            self.__shaderCache[node] = shader
        program = shader.program

        # acquire buffer
        w, h = node.outputs[0].size, node.outputs[0].size
        if w < 0:
            w, h = screenResolution[0] / -w, screenResolution[1] / -h
        frameBuffer = FrameBufferPool.get(w, h, len(node.outputs))
        frameBuffer.use()

        # forward resolution
        uniforms['uResolution'] = float(w), float(h)

        glUseProgram(program)

        # bind inputs
        for i, input in enumerate(inputs):
            glActiveTexture(GL_TEXTURE0 + i)
            input.colorBuffer().use()
            glUniform1i(glGetUniformLocation(program, input.inputName), i)

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
                elif len(value) == 12:
                    glUniformMatrix4x3fv(glGetUniformLocation(program, key), 1, False, value)

        FullScreenRectSingleton.instance().draw()

        # free inputs
        for input in inputs:
            renderBuffers[input.sourceNode].free()

        return frameBuffer
