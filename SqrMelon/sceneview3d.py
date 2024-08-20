import os
import time
from typing import Iterable, Optional

from OpenGL.GL import GL_BLEND, GL_DEPTH_TEST, GL_LEQUAL, GL_ONE_MINUS_SRC_ALPHA, GL_SRC_ALPHA, GL_VERSION, glBlendFunc, glDepthFunc, glDisable, glEnable, glGetString, glClear, GL_COLOR_BUFFER_BIT, GL_DEPTH_BUFFER_BIT

from buffers import Texture
from camerawidget import Camera
from fileutil import FilePath
from overlays import loadImage, Overlays
from projutil import currentProjectDirectory, gSettings
from qt import *
from scene import CameraTransform, Scene
from shots import ShotManager
from timeslider import Timer

_noSignalImage = None


def execfile(path: str, globals_: Optional[dict] = None, locals_: Optional[dict] = None):
    exec(open(path).read(), globals_ or {}, locals_ or {})


class SceneView(QOpenGLWidget):
    """OpenGL 3D viewport.

    Core functionalities are that it is aware of the camera sequencer and timeline,
    so it can decide what camera to evaluate & extract animation data for this frame.

    This is done implicitly in paintGL.

    It wraps a single Scene() instance, which is set from outside and intended
    to match the scene used by the current shot. When a valid scene is set,
    it is rendered to the viewport on every repaint.

    Last it can be connected to a camera widget (setCamera) to which it fill
    forward left mouse drag and keyboard input (WASDQE).
    """

    def __init__(self, shotManager: ShotManager, timer: Timer, overlays: Optional[Overlays] = None):
        # We found that not setting a version in Ubuntu didn't work
        glFormat = QSurfaceFormat()
        glFormat.setVersion(4, 1)
        glFormat.setProfile(QSurfaceFormat.OpenGLContextProfile.CoreProfile)
        glFormat.setDefaultFormat(glFormat)

        # We found that Qt started destroying OpenGL contexts
        QApplication.setAttribute(Qt.ApplicationAttribute.AA_ShareOpenGLContexts, True)

        super(SceneView, self).__init__()

        self._timer = timer
        self._animator = shotManager
        self.__overlays = overlays
        self._scene: Optional[Scene] = None
        self._size = 1, 1
        self._previewRes = None, None, 1.0
        if gSettings.contains('GLViewScale'):
            self._previewRes = None, None, float(gSettings.value('GLViewScale'))
        self._cameraInput = None
        self.setFocusPolicy(Qt.FocusPolicy.StrongFocus)
        self._textures: dict[str, Texture] = {}
        self._prevTime = time.time()

    def cameraInput(self) -> Camera:
        return self._cameraInput

    def textureUniforms(self) -> Iterable[tuple[str, int]]:
        for key, value in self._textures.items():
            yield key, value.id()

    def saveStaticTextures(self) -> None:
        exportDir = QFileDialog.getExistingDirectory(None, 'Choose destination folder to save static textures as .png files.', '.')
        if not exportDir:
            return
        for passData in self._scene.passes:
            if passData.realtime:
                continue
            for index, cbo in enumerate(self._scene.colorBuffers[passData.targetBufferId]):
                cbo.save(FilePath(os.path.join(exportDir, '{}{}.png'.format(passData.name, index))))

    def setPreviewRes(self, widthOverride: Optional[int], heightOverride: Optional[int], scale: float) -> None:
        if widthOverride is not None:
            x = self.parent().width() - self.width()
            y = self.parent().height() - self.height()
            self.parent().setGeometry(self.parent().x(), self.parent().y(), widthOverride + x, heightOverride + y)
        self._previewRes = widthOverride, heightOverride, scale
        gSettings.setValue('GLViewScale', scale)
        self.__onResize()

    @property
    def _cameraData(self) -> CameraTransform:
        return self._cameraInput.data()

    def setCamera(self, cameraInput: Camera) -> None:
        self._cameraInput = cameraInput
        if self._scene:
            # copy the scene camera data to the camera input, so each scene can store it's own user-camera
            self._cameraInput.setCamera(self._scene.readCameraData())

    def saveCameraData(self) -> None:
        if self._cameraInput and self._scene:
            # back up user camera position in scene data
            self._scene.setCameraData(self._cameraInput.camera())

    def setScene(self, scene: Optional[Scene]) -> None:
        if scene == self._scene:
            self.update()
            return

        if self._cameraInput:
            # back up user camera position in scene data
            self.saveCameraData()
            if scene is not None:
                # copy the scene camera data to the camera input, so each scene can store it's own user-camera
                self._cameraInput.setCamera(scene.readCameraData())

        # update which scene's files we are watching for updates
        if self._scene:
            try:
                self._scene.fileSystemWatcher.fileChanged.disconnect(self.update)
            except:
                pass

        if scene:
            scene.fileSystemWatcher.fileChanged.connect(self.update)

        # resize color buffers used by scene
        self._scene = scene
        if scene is not None:
            self._scene.setSize(*self._size)

        self.update()

    def initializeGL(self) -> None:
        print(glGetString(GL_VERSION))

        glEnable(GL_DEPTH_TEST)
        glDepthFunc(GL_LEQUAL)
        # glDepthMask(GL_TRUE)

        IMAGE_EXTENSIONS = '.png', '.bmp', '.tga'
        textureFolder = FilePath(__file__).join('..', 'Textures').abs()
        if textureFolder.exists():
            for texture in textureFolder.iter():
                if texture.ext() in IMAGE_EXTENSIONS:
                    self._textures[texture.name()] = loadImage(textureFolder.join(texture))

        self._prevTime = time.time()
        self._timer.kick()

        SceneView.screenFBO = self.defaultFramebufferObject()

    screenFBO = 0

    @staticmethod
    def calculateAspect(w: int, h: int):
        aspectH = w / 16 * 9
        aspectW = h / 9 * 16

        newW = w
        if aspectH > h:
            aspectH = h
            newW = int(aspectW)

        return newW, int(aspectH)

    def paintGL(self) -> None:
        self.makeCurrent()
        SceneView.screenFBO = self.defaultFramebufferObject()

        # If we don't clear the default FBO first we can get garbage pixels in the black bars
        glClear(GL_COLOR_BUFFER_BIT | GL_DEPTH_BUFFER_BIT)

        newTime = time.time()
        deltaTime = newTime - self._prevTime

        # work around double repaint events collecting in the queue
        if deltaTime == 0.0:
            return

        self._prevTime = newTime

        width, height = self.calculateAspect(self.width(), self.height())
        viewport = (int((self.width() - width) * 0.5),
                    int((self.height() - height) * 0.5),
                    width,
                    height)

        if self._scene:
            uniforms = self._animator.evaluate(self._timer.time)
            textureUniforms = self._animator.additionalTextures(self._timer.time)

            cameraData = self._cameraData
            scene = self._scene
            modifier = currentProjectDirectory().join('animationprocessor.py')
            if modifier.exists():
                beats = self._timer.time
                execfile(modifier, globals(), locals())

            for uniformName in self._textures:
                uniforms[uniformName] = self._textures[uniformName].id()

            self._scene.drawToScreen(self._timer.beatsToSeconds(self._timer.time), self._timer.time, uniforms, viewport, additionalTextureUniforms=textureUniforms)

        else:
            # no scene active, time cursor outside any enabled shots?
            global _noSignalImage
            if _noSignalImage is None:
                _noSignalImage = loadImage(FilePath(__file__).parent().join('icons', 'nosignal.png'))
            if _noSignalImage:
                glDisable(GL_DEPTH_TEST)
                glEnable(GL_BLEND)
                glBlendFunc(GL_SRC_ALPHA, GL_ONE_MINUS_SRC_ALPHA)
                Scene.drawColorBufferToScreen(_noSignalImage, viewport)
                glDisable(GL_BLEND)
                glEnable(GL_DEPTH_TEST)

        if self.__overlays:
            image = self.__overlays.colorBuffer()
            if image:
                color = (self.__overlays.overlayColor().red() / 255.0,
                         self.__overlays.overlayColor().green() / 255.0,
                         self.__overlays.overlayColor().blue() / 255.0,
                         self.__overlays.overlayColor().alpha() / 255.0)
                glDisable(GL_DEPTH_TEST)
                glEnable(GL_BLEND)
                glBlendFunc(GL_SRC_ALPHA, GL_ONE_MINUS_SRC_ALPHA)
                Scene.drawColorBufferToScreen(image, viewport, color)
                glDisable(GL_BLEND)
                glEnable(GL_DEPTH_TEST)

    def __onResize(self) -> None:
        w = self.width()
        h = self.height()
        if self._previewRes[0]:
            w = self._previewRes[0]
        if self._previewRes[1]:
            h = self._previewRes[1]
        w = int(w * self._previewRes[2])
        h = int(h * self._previewRes[2])
        self._size = self.calculateAspect(w, h)[0:2]
        if self._scene:
            self._scene.setSize(*self._size)
        self.update()

    def resizeGL(self, w: int, h: int):
        SceneView.screenFBO = self.defaultFramebufferObject()
        self.__onResize()

    def keyPressEvent(self, keyEvent: QKeyEvent):
        super(SceneView, self).keyPressEvent(keyEvent)
        if self._cameraInput:
            self._cameraInput.flyKeyboardInput(keyEvent, True)

    def keyReleaseEvent(self, keyEvent: QKeyEvent):
        super(SceneView, self).keyReleaseEvent(keyEvent)
        if self._cameraInput:
            self._cameraInput.flyKeyboardInput(keyEvent, False)

    def mousePressEvent(self, mouseEvent: QMouseEvent):
        super(SceneView, self).mousePressEvent(mouseEvent)
        if self._cameraInput:
            self._cameraInput.flyMouseStart(mouseEvent)

    def mouseMoveEvent(self, mouseEvent: QMouseEvent):
        super(SceneView, self).mouseMoveEvent(mouseEvent)
        if self._cameraInput:
            self._cameraInput.flyMouseUpdate(mouseEvent, self.size())

    def mouseReleaseEvent(self, mouseEvent: QMouseEvent):
        super(SceneView, self).mouseReleaseEvent(mouseEvent)
        if self._cameraInput:
            self._cameraInput.flyMouseEnd(mouseEvent)
