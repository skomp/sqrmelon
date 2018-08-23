from experiment.scenes import Scene
from qtutil import *
from OpenGL.GL import *
from math import tan
from cgmath import Mat44



class View3D(QGLWidget):
    def __init__(self, camera, model, timer):
        # type: (View3D, Camera, DemoModel, Timer) -> None
        glFormat = QGLFormat()
        glFormat.setVersion(4, 1)
        glFormat.setProfile(QGLFormat.CoreProfile)
        glFormat.setDefaultFormat(glFormat)

        super(View3D, self).__init__()

        self.camera = camera
        self.model = model
        self.timer = timer

    def initializeGL(self):
        pass

    def resizeGL(self, w, h):
        glViewport(0, 0, w, h)

    def paintGL(self):
        glDisable(GL_DEPTH_TEST)
        glDisable(GL_BLEND)
        glClear(GL_COLOR_BUFFER_BIT | GL_DEPTH_BUFFER_BIT)
        sceneName, snapshot = self.model.evaluate(self.timer.time)
        uniforms = {}

        # convert camera to matrix
        for key in ('uOrigin.x', 'uOrigin.y', 'uOrigin.z', 'uAngles.x', 'uAngles.y', 'uAngles.z'):
            try:
                del snapshot[key]
            except KeyError:
                pass  # nothing to delete
        uniforms['uV'] = Mat44.TRS(*self.camera.data().data)
        tfov = tan(uniforms.get('uFovBias', 0.5))
        aspect = self.width() / float(self.height())  # TODO: base off frame buffer
        xfov = tfov * aspect
        uniforms['uFrustum'] = (-xfov, -tfov, 1.0, xfov, -tfov, 1.0, -xfov, tfov, 1.0, xfov, tfov, 1.0)

        # combine vector data types
        for key in snapshot:
            if key.endswith('.x'):
                uniform = key[:-2]
                value = uniforms.get(uniform, [None])
                value[0] = snapshot[key]
            elif key.endswith('.y'):
                uniform = key[:-2]
                value = uniforms.get(uniform, [None, None])
                if len(value) < 2:
                    value.append(snapshot[key])
                else:
                    value[1] = snapshot[key]
            elif key.endswith('.z'):
                uniform = key[:-2]
                value = uniforms.get(uniform, [None, None, None])
                while len(value) < 3:
                    value.append(None)
                value[2] = snapshot[key]
            elif key.endswith('.w'):
                uniform = key[:-2]
                value = uniforms.get(uniform, [None, None, None, None])
                while len(value) < 4:
                    value.append(None)
                value[3] = snapshot[key]
            else:
                uniform = key
                value = snapshot[key]
            uniforms[uniform] = value

        # evaluate scene
        scene = Scene.pool(str(sceneName))

        scene.render((self.width(), self.height()), uniforms)

    # forward events to camera
    def keyPressEvent(self, keyEvent):
        super(View3D, self).keyPressEvent(keyEvent)
        self.camera.flyKeyboardInput(keyEvent, True)

    def keyReleaseEvent(self, keyEvent):
        super(View3D, self).keyReleaseEvent(keyEvent)
        self.camera.flyKeyboardInput(keyEvent, False)

    def mousePressEvent(self, mouseEvent):
        super(View3D, self).mousePressEvent(mouseEvent)
        self.camera.flyMouseStart(mouseEvent)

    def mouseMoveEvent(self, mouseEvent):
        super(View3D, self).mouseMoveEvent(mouseEvent)
        self.camera.flyMouseUpdate(mouseEvent, self.size())

    def mouseReleaseEvent(self, mouseEvent):
        super(View3D, self).mouseReleaseEvent(mouseEvent)
        self.camera.flyMouseEnd(mouseEvent)
