import sys
from OpenGL.GL import *
from OpenGL.GL import shaders
from qtutil import *
from buffers import FrameBuffer
from experiment.util import PooledResource, FileSystemWatcher2

STATIC_VERT = '#version 410\nout vec2 vUV;void main(){gl_Position=vec4(step(1,gl_VertexID)*step(-2,-gl_VertexID)*2-1,gl_VertexID-gl_VertexID%2-1,0,1);vUV=gl_Position.xy*.5+.5;}'
PASS_THROUGH_FRAG = '#version 410\nin vec2 vUV;uniform vec4 uColor;uniform sampler2D uImages[1];out vec4 outColor0;void main(){outColor0=uColor*texture(uImages[0], vUV);}'


class FullScreenRectSingleton(object):
    """
    glRect() didn't work on linux, so now we pool a VAO and use a vertex shader to position the corners.
    """
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


class Program(PooledResource):
    """
    The shader compiler, hashes the code to pool duplicate shaders automatically
    """
    _errorDialog = None

    @classmethod
    def errorDialog(cls, msg):
        if cls._errorDialog is None:
            cls._errorDialog = QDialog()  # error log
            cls._errorDialog.setWindowTitle('Compile log')
            cls._errorDialog.setLayout(vlayout())
            cls._errorDialogText = QTextEdit()
            cls._errorDialog.layout().addWidget(cls._errorDialogText)
            hbar = hlayout()
            cls._errorDialog.layout().addLayout(hbar)
            hbar.addStretch(1)
            btn = QPushButton('Close')
            hbar.addWidget(btn)
            btn.clicked.connect(cls._errorDialog.accept)
        cls._errorDialog.setHtml(msg)
        cls._errorDialog.setGeometry(100, 100, 800, 600)
        cls._errorDialog.exec_()

    def __init__(self, vertCode, fragCode):
        try:
            # skip shader validation step on linux
            validate = 'linux' not in sys.platform.lower()

            vert = shaders.compileShader(vertCode, GL_VERTEX_SHADER)
            frag = shaders.compileShader(fragCode, GL_FRAGMENT_SHADER)

            program = glCreateProgram()
            glAttachShader(program, vert)
            glAttachShader(program, frag)
            program = shaders.ShaderProgram(program)
            glLinkProgram(program)
            if validate:
                program.check_validate()
            program.check_linked()
            glDeleteShader(vert)
            glDeleteShader(frag)

            self.program = program
        except RuntimeError, e:
            errors = e.args[0].split('\n')
            try:
                code = e.args[1][0].split('\n')
            except:
                errors = str(e.args)
                code = fragCode
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
            self.errorDialog('<pre>' + '\n'.join(log) + '</pre>')


class Shader(PooledResource):
    """
    Stitched shaders, invalidates shader on file change
    and pools shaders that use the same stitch file paths.

    Lazily compiled.
    """

    def __init__(self, stitches):
        self.watcher = FileSystemWatcher2(stitches)
        self.watcher.fileChanged.connect(self.invalidate)
        self._stitches = [unicode(os.path.abspath(stitch)) for stitch in stitches]
        self._program = None

    @property
    def program(self):
        if self._program is None:
            code = []
            for stitch in self._stitches:
                with open(stitch) as fh:
                    code.append(fh.read())
            self._program = Program.pool(STATIC_VERT, '\n'.join(code))
        return self._program.program

    def invalidate(self, changedPath):
        self._program = None


_passThroughProgram = None


def passThroughProgram():
    # simple program that draws an image as a full screen rect
    global _passThroughProgram
    if _passThroughProgram is not None:
        return _passThroughProgram
    _passThroughProgram = Program.pool(STATIC_VERT, PASS_THROUGH_FRAG).program
    return _passThroughProgram


def usePassThroughProgram(color=(1.0, 1.0, 1.0, 1.0)):
    # simple program that draws an image as a full screen rect
    passThrough = passThroughProgram()
    glUseProgram(passThrough)
    glUniform4f(glGetUniformLocation(passThrough, 'uColor'), *color)
    return passThrough


def drawColorBufferToScreen(colorBuffer, viewport, color=(1.0, 1.0, 1.0, 1.0)):
    # draw to screen
    FrameBuffer.clear()
    # draw at screen resolution
    glViewport(*viewport)
    # apply the given color buffer as texture
    passThrough = usePassThroughProgram(color)
    glActiveTexture(GL_TEXTURE0)
    colorBuffer.use()
    glUniform1i(glGetUniformLocation(passThrough, 'uImages[0]'), 0)
    # draw
    FullScreenRectSingleton.instance().draw()
