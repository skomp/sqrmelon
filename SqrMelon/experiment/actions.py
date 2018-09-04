from experiment import cursor
from experiment.commands import TimeEdit, KeyEdit, ModelEdit, EventEdit
from qtutil import *


class Action(object):
    def draw(self, painter):
        pass


class MoveTimeAction(Action):
    def __init__(self, originalTime, xToT, setTime, undoable=True):
        self.valueChanged = Signal()
        self.__originalTime = originalTime
        self.__setTime = setTime
        self.__xToT = xToT
        self.__newTime = originalTime
        self.__undoable = undoable

    def mousePressEvent(self, event):
        self.mouseMoveEvent(event)

    def mouseMoveEvent(self, event):
        self.__newTime = self.__xToT(event.x())
        self.__setTime(self.__newTime)
        self.valueChanged.emit(self.__newTime)

    def mouseReleaseEvent(self, undoStack):
        if self.__undoable:
            undoStack.push(TimeEdit(self.__originalTime, self.__newTime, self.__setTime))


class DirectionalAction(Action):
    def __init__(self, reproject, mask=3):
        self._reproject = reproject
        self._dragStartPx = None
        self._dragStartU = None
        self._mask = mask

    def mousePressEvent(self, event):
        self._dragStartPx = event.pos()
        self._dragStartU = self._reproject(event.x(), event.y())
        # when we are omni-directional and shift is pressed we can lock the event to a single axis
        if self._mask == 3 and event.modifiers() & Qt.ShiftModifier:
            self._mask = 0
        else:
            cursor.set(Qt.SizeAllCursor)
        return False

    def mouseMoveEvent(self, event):
        if not self._mask:
            deltaPx = event.pos() - self._dragStartPx
            dxPx = deltaPx.x()
            dyPx = deltaPx.y()
            if abs(dxPx) > 4 and abs(dxPx) > abs(dyPx):
                cursor.set(Qt.SizeHorCursor)
                self._mask = 1
            elif abs(dyPx) > 4 and abs(dyPx) > abs(dxPx):
                cursor.set(Qt.SizeVerCursor)
                self._mask = 2
            return

        return self.processMouseDelta(event)

    def mouseReleaseEvent(self, __=None):
        cursor.restore()

    def processMouseDelta(self, event):
        raise NotImplementedError()


class ViewPanAction(Action):
    def __init__(self, viewRect, widgetSize):
        self.__dragStart = None
        self.__startPos = None
        self.__rect = viewRect
        self.__widgetSize = widgetSize

    def mousePressEvent(self, event):
        self.__dragStart = event.pos()
        self.__startPos = self.__rect.left, self.__rect.right, self.__rect.top, self.__rect.bottom
        cursor.set(Qt.SizeAllCursor)

    def mouseMoveEvent(self, event):
        delta = event.pos() - self.__dragStart
        ux = delta.x() * (self.__rect.right - self.__rect.left) / float(self.__widgetSize.width())
        uy = delta.y() * (self.__rect.bottom - self.__rect.top) / float(self.__widgetSize.height())
        self.__rect.left = self.__startPos[0] - ux
        self.__rect.right = self.__startPos[1] - ux
        self.__rect.top = self.__startPos[2] - uy
        self.__rect.bottom = self.__startPos[3] - uy

    def mouseReleaseEvent(self, __=None):
        cursor.restore()


def zoom(pivotUnits, viewRect, hSteps, vSteps, baseValues=None):
    if baseValues is None:
        baseValues = viewRect.left, viewRect.right, viewRect.top, viewRect.bottom

    cx, cy = pivotUnits
    extents = [baseValues[0] - cx, baseValues[1] - cx, baseValues[2] - cy, baseValues[3] - cy]

    for step in xrange(abs(hSteps)):
        if hSteps > 0:
            extents[0] *= 1.0005
            extents[1] *= 1.0005
        else:
            extents[0] /= 1.0005
            extents[1] /= 1.0005

    for step in xrange(abs(vSteps)):
        if vSteps > 0:
            extents[2] *= 1.0005
            extents[3] *= 1.0005
        else:
            extents[2] /= 1.0005
            extents[3] /= 1.0005

    viewRect.set(cx + extents[0], cx + extents[1], cy + extents[2], cy + extents[3])


class ViewZoomAction(DirectionalAction):
    def __init__(self, viewRect, pixelSize, reproject, mask):
        super(ViewZoomAction, self).__init__(reproject, mask)
        self.__rect = viewRect
        self.__pixelSize = pixelSize
        self.__baseValues = self.__rect.left, self.__rect.right, self.__rect.top, self.__rect.bottom

    def processMouseDelta(self, event):
        dx = self._dragStartPx.x() - event.x()
        dy = self._dragStartPx.y() - event.y()
        dx = int(dx * 4000.0 / float(self.__pixelSize.width()))
        dy = int(dy * 4000.0 / float(self.__pixelSize.height()))
        if not self._mask & 1:
            dx = 0
        if not self._mask & 2:
            dy = 0

        zoom(self._dragStartU, self.__rect, dx, dy, self.__baseValues)

        return False


class MoveKeyAction(DirectionalAction):
    def __init__(self, reproject, snapTime, selectedKeys, triggerRepaint):
        super(MoveKeyAction, self).__init__(reproject)
        self.__snapTime = snapTime
        self.__curves = {key.parent for key in selectedKeys}
        self.__selectedKeys = list(selectedKeys.iterkeys())
        self.__initialState = {key: key.copyData() for curve in self.__curves for key in curve.keys}
        self.__triggerRepaint = triggerRepaint

    def mouseReleaseEvent(self, undoStack):
        super(MoveKeyAction, self).mouseReleaseEvent()
        undoStack.push(KeyEdit(self.__initialState, self.__triggerRepaint))
        return False

    def processMouseDelta(self, event):
        ux, uy = self._reproject(event.x(), event.y())
        ux -= self._dragStartU[0]
        uy -= self._dragStartU[1]

        for key in self.__selectedKeys:
            value = self.__initialState[key]
            if self._mask & 1:
                key.x = self.__snapTime(value[0] + ux)
            if self._mask & 2:
                key.y = value[1] + uy

        if self._mask & 1:
            for curve in self.__curves:
                curve.sort()

        # must do this after sorting...
        for key in self.__initialState:
            key.computeTangents()

        return True  # repaint


class MoveTangentAction(Action):
    def __init__(self, selectedTangents, reproject, triggerRepaint):
        self.__reproject = reproject
        self.__initialState = {key: key.copyData() for (key, mask) in selectedTangents.iteritems()}
        self.__masks = selectedTangents.copy()
        self.__dragStart = None
        self.__triggerRepaint = triggerRepaint

    def mousePressEvent(self, event):
        cursor.set(Qt.SizeVerCursor)
        self.__dragStart = self.__reproject(event.x(), event.y())
        return False

    def mouseReleaseEvent(self, undoStack):
        cursor.restore()
        undoStack.push(KeyEdit(self.__initialState, self.__triggerRepaint))
        return False

    def mouseMoveEvent(self, event):
        from experiment.curvemodel import ETangentMode
        dx, dy = self.__reproject(event.x(), event.y())
        dx -= self.__dragStart[0]
        dy -= self.__dragStart[1]

        for key, value in self.__initialState.iteritems():
            mask = self.__masks[key]
            if mask & 2:
                key.inTangentY = value[2] - dy
                key.inTangentMode = ETangentMode.Custom
            if mask & 4:
                key.outTangentY = value[3] + dy
                key.outTangentMode = ETangentMode.Custom

        return True  # repaint


class MoveEventAction(DirectionalAction):
    def __init__(self, reproject, cellSize, events, handle=3):
        super(MoveEventAction, self).__init__(reproject)
        self._events = {event: (event.start, event.end, event.track) for event in events}
        self._cellSize = cellSize / 8.0  # Snap at 1/8th of a grid cell
        self._handle = handle

    def mousePressEvent(self, event):
        if self._handle in (1, 2):
            self._mask = 1
        result = super(MoveEventAction, self).mousePressEvent(event)
        if self._mask == 1:
            # Change cursor to horizontal move when dragging start or end section
            cursor.set(Qt.SizeHorCursor)
        return result

    def mouseReleaseEvent(self, undoStack):
        super(MoveEventAction, self).mouseReleaseEvent(undoStack)
        undoStack.push(EventEdit(self._events))

    def processMouseDelta(self, event):
        from experiment.timelineview import GraphicsItemEvent
        ux, uy = self._reproject(event.x(), event.y())
        ux -= self._dragStartU[0]
        uy = (event.y() - self._dragStartPx.y()) / float(GraphicsItemEvent.trackHeight)

        for event, value in self._events.iteritems():
            if self._mask & 1:  # X move
                newStart = round(value[0] + ux, 3)
                newEnd = round(value[1] + ux, 3)

                # Snap
                newStart = round(newStart / self._cellSize) * self._cellSize
                newEnd = round(newEnd / self._cellSize) * self._cellSize

                if self._handle & 1 and newStart != event.start:
                    if not self._handle & 2:
                        # truncate from start
                        event.duration = event.end - newStart
                    event.start = newStart

                if self._handle == 2:
                    # truncate from end
                    if newEnd != event.end:
                        event.end = newEnd

            if self._mask & 2:  # Y move
                newTrack = int(round(value[2] + uy))
                if newTrack != event.track:
                    event.track = newTrack


class MarqueeActionBase(object):
    CLICK_SIZE = 10

    def __init__(self, view, selection):
        self._view = view
        self._selection = selection
        self._delta = None
        self._start = None
        self._end = None
        self._mode = None

    def mousePressEvent(self, event):
        self._start = event.pos()
        self._end = event.pos()
        self._mode = event.modifiers() & (Qt.ControlModifier | Qt.ShiftModifier)

    def _rect(self):
        x0, x1 = self._start.x(), self._end.x()
        x0, x1 = min(x0, x1), max(x0, x1)
        y0, y1 = self._start.y(), self._end.y()
        y0, y1 = min(y0, y1), max(y0, y1)
        return x0, y0, x1 - x0, y1 - y0

    @staticmethod
    def _selectNew(selection, itemsIter):
        raise NotImplementedError()

    @staticmethod
    def _selectAdd(selection, itemsIter):
        raise NotImplementedError()

    @staticmethod
    def _selectRemove(selection, itemsIter):
        raise NotImplementedError()

    @staticmethod
    def _selectToggle(selection, itemsIter):
        raise NotImplementedError()

    @staticmethod
    def _createCommand(selection, delta):
        raise NotImplementedError()

    def mouseReleaseEvent(self, undoStack):
        if self._end == self._start:
            x, y, w, h = self._start.x() - (self.CLICK_SIZE / 2), \
                         self._start.y() - (self.CLICK_SIZE / 2), \
                         self.CLICK_SIZE, \
                         self.CLICK_SIZE
        else:
            x, y, w, h = self._rect()
        # build apply state
        itemsIter = self._view.itemsAt(x, y, w, h)
        if self._mode == Qt.NoModifier:
            self._delta = self._selectNew(self._selection, itemsIter)
        elif self._mode == Qt.ControlModifier | Qt.ShiftModifier:
            self._delta = self._selectAdd(self._selection, itemsIter)
        elif self._mode == Qt.ControlModifier:
            self._delta = self._selectRemove(self._selection, itemsIter)
        else:  # if self.mode == Qt.ShiftModifier:
            self._delta = self._selectToggle(self._selection, itemsIter)

        # if we don't plan to change anything, stop right here and don't submit this undoable action
        if not self._delta:
            return True

        # commit self to undo stack
        cmd = self._createCommand(self._selection, self._delta)
        if cmd:
            undoStack.push(cmd)

    def mouseMoveEvent(self, event):
        self._end = event.pos()
        return True

    def draw(self, painter):
        x, y, w, h = self._rect()
        painter.setPen(QColor(0, 160, 255, 255))
        painter.setBrush(QColor(0, 160, 255, 64))
        painter.drawRect(x, y, w, h)


class DuplicateEventAction(Action):
    def __init__(self, items, model, undoStack=None):
        self._events = items
        self._model = model
        self._undoStack = undoStack
        self._copyCounter = 0

    def keyPressEvent(self, _):
        copiedEvents = []

        for event in self._events:
            copy = event.copy()
            if self._copyCounter:
                copy.name = '%s (Copy %s)' % (copy.name, self._copyCounter)
            else:
                copy.name = '%s (Copy)' % copy.name
            self._copyCounter += 1

            # Place copied item at the end of the timeline
            end = 0
            for row in xrange(self._model.rowCount()):
                event = self._model.item(row, 0).data()

                if event.track != copy.track:
                    continue
                if event.end > end:
                    end = event.end

            copy.start = end
            copy.end = copy.start + copy.duration

            copiedEvents.append(copy)
            self._model.appendRow(copy.items)

        if copiedEvents:
            if self._undoStack:
                self._undoStack.push(ModelEdit(self._model, copiedEvents, []))
            return True
        else:
            return False
