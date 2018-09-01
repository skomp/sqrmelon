from collections import OrderedDict
from qtutil import *
from experiment.enum import Enum
from utils import lerp


class EStitchScope(Enum):
    Scene = None  # type: EStitchScope
    Public = None  # type: EStitchScope
    Private = None  # type: EStitchScope

    @staticmethod
    def options():
        return 'Scene', 'Public', 'Private'


EStitchScope.Scene = EStitchScope('Scene')
EStitchScope.Public = EStitchScope('Public')
EStitchScope.Private = EStitchScope('Private')


class Stitch(object):
    def __init__(self, name, scope=EStitchScope.Public):
        self.name = name
        self.scope = scope

    def toJson(self):
        return OrderedDict([('name', self.name),
                            ('scope', str(self.scope))])

    @classmethod
    def fromJson(cls, data):
        return cls(data['name'], EStitchScope(data['scope']))


class Plug(object):
    def __init__(self, name, node, connections=tuple()):
        self.name = name
        self.node = node
        self.connections = list(connections)
        self.portRect = None
        self.textRect = None

    def paint(self, painter):
        painter.drawEllipse(self.portRect)
        painter.drawText(self.textRect, Qt.AlignRight | Qt.AlignTop, self.name)

    def toJson(self):
        return OrderedDict([('name', self.name),
                            ('connections', tuple('%s.%s' % (connection.node.id, connection.name) for connection in self.connections))])

    @classmethod
    def fromJson(cls, data):
        return cls(data['name'], None, data['connections'])


class OutputPlug(Plug):
    def __init__(self, name, node, size=-1, connections=tuple()):
        super(OutputPlug, self).__init__(name, node, connections)
        # if size is negative it is a factor of the screen resolution
        self.size = size

    def toJson(self):
        data = super(OutputPlug, self).toJson()
        data['size'] = self.size
        return data

    @classmethod
    def fromJson(cls, data):
        return cls(data['name'], None, data['size'], data['connections'])


class Node(object):
    # serialization utility, cleared before saving graph
    idLut = {}

    def __init__(self, name, x=0, y=0, inputs=tuple(), outputs=tuple(), stitches=tuple()):
        self.name = name
        self.x = x
        self.y = y
        self._rect = None
        self._contentRect = None
        self.inputs = list(inputs)
        self.outputs = list(outputs)
        self.stitches = list(stitches)

        for plug in self.inputs:
            plug.node = self
        for plug in self.outputs:
            plug.node = self

        self.layout()

    def findInput(self, name):
        for port in self.inputs:
            if port.name == name:
                return port

    def findOutput(self, name):
        for output in self.outputs:
            if output.name == name:
                return output

    @property
    def id(self):
        # serialization utility
        idx = Node.idLut.get(self, None)
        if idx is None:
            idx = len(Node.idLut)
            Node.idLut[self] = idx
        return idx

    def toJson(self):
        return OrderedDict([('name', self.name),
                            ('id', self.id),
                            ('x', self.x),
                            ('y', self.y),
                            ('inputs', tuple(port.toJson() for port in self.inputs)),
                            ('outputs', tuple(output.toJson() for output in self.outputs)),
                            ('stitches', tuple(stitch.toJson() for stitch in self.stitches))])

    @classmethod
    def fromJson(cls, data):
        node = cls(data['name'],
                   data['x'],
                   data['y'],
                   tuple(Plug.fromJson(port) for port in data['inputs']),
                   tuple(OutputPlug.fromJson(output) for output in data['outputs']),
                   tuple(Stitch.fromJson(stitch) for stitch in data['stitches']))
        Node.idLut[data['id']] = node
        return node

    def setName(self, name):
        self.name = name

    def setPosition(self, x, y):
        self.x = x
        self.y = y
        dx = (x - self._rect.x())
        dy = (y - self._rect.y())
        self._rect.moveTo(x, y)
        self._contentRect.moveTo(x + Node.PADDING, y + Node.PADDING)
        for plug in self.inputs + self.outputs:
            x, y = plug.portRect.x() + dx, plug.portRect.y() + dy
            plug.portRect.moveTo(x, y)
            x, y = plug.textRect.x() + dx, plug.textRect.y() + dy
            plug.textRect.moveTo(x, y)

    @property
    def rect(self):
        if self._rect is None:
            self.layout()
        return self._rect

    PADDING = 4

    def layout(self):
        PLUG_SIZE = 7

        metrics = QApplication.fontMetrics()
        padding = Node.PADDING
        em = max(PLUG_SIZE, metrics.height()) + padding

        lhs = 0.0
        if self.inputs:
            lhs = max(PLUG_SIZE + padding + metrics.width(port.name) + padding for port in self.inputs)
        rhs = 0.0
        if self.outputs:
            rhs = max(PLUG_SIZE + padding + metrics.width(output.name) + padding for output in self.outputs)
        contentWidth = max(lhs + rhs, metrics.width(self.name))
        self._contentRect = QRect(self.x + padding, self.y + padding, contentWidth, em * (1 + max(len(self.inputs), len(self.outputs))))
        self._rect = QRect(self.x, self.y, contentWidth + 2 * padding, em * (1 + max(len(self.inputs), len(self.outputs))) + 2 * padding)

        contentRect = self._contentRect.adjusted(0, em, 0, 0)
        for i in xrange(max(len(self.inputs), len(self.outputs))):
            o = ((em - padding) - PLUG_SIZE) / 2
            if i < len(self.inputs):
                self.inputs[i].portRect = QRect(contentRect.x(), contentRect.y() + o, PLUG_SIZE, PLUG_SIZE)
                self.inputs[i].textRect = QRect(contentRect.x() + PLUG_SIZE + padding, contentRect.y(), lhs - (PLUG_SIZE + padding), metrics.height())
            if i < len(self.outputs):
                self.outputs[i].portRect = QRect(contentRect.right() - PLUG_SIZE, contentRect.y() + o, PLUG_SIZE, PLUG_SIZE)
                self.outputs[i].textRect = QRect(contentRect.right() - rhs, contentRect.y(), rhs - (PLUG_SIZE + padding), contentRect.height())
            contentRect.adjust(0, em, 0, 0)

    def paint(self, painter):
        path = QPainterPath()
        path.addRoundedRect(QRectF(self._rect), Node.PADDING, Node.PADDING)
        painter.fillPath(path, QColor(220, 220, 220))
        painter.drawText(self._contentRect, Qt.AlignHCenter | Qt.AlignTop, self.name)
        for port in self.inputs:
            port.paint(painter)
            # connections are bidirectional, so by only painting connections for inputs we cover all of them
            for other in port.connections:
                start = port.portRect.center()
                end = other.portRect.center()
                path = QPainterPath()
                path.moveTo(start)
                path.cubicTo(QPoint(lerp(start.x(), end.x(), 0.5), start.y()), QPoint(lerp(end.x(), start.x(), 0.5), end.y()), end)
                painter.drawPath(path)
        for output in self.outputs:
            output.paint(painter)
