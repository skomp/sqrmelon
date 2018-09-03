import functools
import pyglet
from experiment.actions import MarqueeActionBase, MoveTimeAction, MoveEventAction, DuplicateEventAction
from experiment.commands import ModelEdit
from experiment.gridview import GridView
from experiment.model import Shot
from experiment.projectutil import projectFolder, settings
from experiment.timer import drawPlayhead, drawLoopRange
from qtutil import *
import icons


class GraphicsItemEvent(object):
    trackHeight = 24
    handleWidth = 8
    padding = (4, 4, 4, 4)
    iconSize = 16

    _ico = None

    @classmethod
    def iconName(cls):
        return 'Curves'

    def __init__(self, event, x, width):
        self.event = event
        self.rect = QRect(x,
                          event.track * GraphicsItemEvent.trackHeight,
                          width,
                          GraphicsItemEvent.trackHeight)
        self.iconRect = QRect(x, self.rect.y() + (self.rect.height() - GraphicsItemShot.iconSize) / 2, GraphicsItemShot.iconSize, GraphicsItemShot.iconSize)
        self.textRect = self.rect.adjusted(*GraphicsItemEvent.padding)
        self.textRect.setLeft(x + GraphicsItemShot.iconSize + GraphicsItemEvent.padding[0])
        self.__mouseOver = False
        if self.__class__._ico is None:
            self.__class__._ico = icons.getImage(self.iconName())

    def paint(self, painter, isSelected=False):
        painter.fillRect(self.rect, self.event.color)
        highlightColor = QColor(255, 255, 64, 128)
        if self.__mouseOver == 3:
            painter.fillRect(self.rect, highlightColor)
        elif self.__mouseOver == 1:
            painter.fillRect(QRect(self.rect.x(), self.rect.y(), GraphicsItemEvent.handleWidth, self.rect.height()), highlightColor)
        elif self.__mouseOver == 2:
            painter.fillRect(QRect(self.rect.right() - GraphicsItemEvent.handleWidth + 1, self.rect.y(), GraphicsItemEvent.handleWidth, self.rect.height()), highlightColor)
        if isSelected:
            painter.setPen(Qt.yellow)
            painter.drawRect(self.rect.adjusted(0, 0, -1, -1))
            painter.setPen(Qt.black)
        painter.drawText(self.textRect, 0, self.event.name)
        painter.drawPixmap(self.iconRect, self._ico)

    def focusOutEvent(self):
        dirty = self.__mouseOver != 0
        self.__mouseOver = 0
        return dirty

    def mouseMoveEvent(self, pos):
        mouseOver = self.rect.adjusted(0, 0, -1, -1).contains(pos)

        if mouseOver:
            state = 3
            if self.rect.width() > GraphicsItemEvent.handleWidth * 3:
                lx = pos.x() - self.rect.x()
                if lx < GraphicsItemEvent.handleWidth:
                    state = 1
                elif lx > self.rect.width() - GraphicsItemEvent.handleWidth:
                    state = 2
        else:
            state = 0

        if state != self.__mouseOver:
            self.__mouseOver = state
            return True


class GraphicsItemShot(GraphicsItemEvent):
    @classmethod
    def iconName(cls):
        return 'Film Strip'


class TimestampDisplay(QLabel):
    def __init__(self, timer):
        super(TimestampDisplay, self).__init__()
        self.__timer = timer
        self.update()

    def update(self, *args):
        beat = self.__timer.time
        minute = int(beat / self.__timer.bpm)
        second = int(((beat * 60) / self.__timer.bpm) % 60)
        fraction = int(round(((beat * 60 * 1000) / self.__timer.bpm) % 1000))
        self.setText('%02d:%02d,%04d' % (minute, second, fraction))


class BPMInput(QWidget):
    def __init__(self, bpm):
        super(BPMInput, self).__init__()
        bpm = round(bpm, 2)
        self._spinBox = DoubleSpinBox(bpm)
        self.setLayout(QVBoxLayout())
        self.layout().addWidget(self._spinBox)
        self._label = QLabel('%s BPM' % bpm)
        self.layout().addWidget(self._label)
        self._spinBox.hide()
        self._spinBox.editingFinished.connect(self.disable)

    def spinBox(self):
        return self._spinBox

    def setValueSilent(self, bpm):
        bpm = round(bpm, 2)
        self._spinBox.setValueSilent(bpm)
        self._label.setText('%s BPM' % bpm)

    def disable(self):
        self._label.show()
        self._label.setText('%s BPM' % self._spinBox.value())
        self._spinBox.hide()

    def mouseDoubleClickEvent(self, *args, **kwargs):
        self._spinBox.show()
        self._spinBox.setFocus(Qt.MouseFocusReason)
        self._spinBox.selectAll()
        self._label.hide()


class TimelineMarqueeAction(MarqueeActionBase):
    CLICK_SIZE = 2

    def __init__(self, view, selectionModels, undoStack):
        super(TimelineMarqueeAction, self).__init__(view, selectionModels)
        self._undoStack = undoStack

    @staticmethod
    def _preProcess(selectionModels, itemsIter):
        events = list(graphicsItem.event for graphicsItem in itemsIter)
        for selectionModel in selectionModels:
            selectedRows = set(idx.row() for idx in selectionModel.selectedRows())

            touchedRows = set()
            for event in events:
                if event.items[0].model() != selectionModel.model().sourceModel():
                    continue
                proxyRow = selectionModel.model().mapFromSource(event.items[0].index()).row()
                touchedRows.add(proxyRow)
            yield selectionModel, selectedRows, touchedRows

    @staticmethod
    def _selectNew(selectionModels, itemsIter):
        changeMap = {}
        for selectionModel, selectedRows, touchedRows in TimelineMarqueeAction._preProcess(selectionModels, itemsIter):
            keep = selectedRows & touchedRows
            select = (touchedRows - keep)
            deselect = (selectedRows - keep)
            if not select and not deselect:
                continue
            changeMap[selectionModel] = select, deselect
        return changeMap

    @staticmethod
    def _selectAdd(selectionModels, itemsIter):
        changeMap = {}
        for selectionModel, selectedRows, touchedRows in TimelineMarqueeAction._preProcess(selectionModels, itemsIter):
            select = touchedRows - selectedRows
            if not select:
                continue
            changeMap[selectionModel] = select, set()
        return changeMap

    @staticmethod
    def _selectRemove(selectionModels, itemsIter):
        changeMap = {}
        for selectionModel, selectedRows, touchedRows in TimelineMarqueeAction._preProcess(selectionModels, itemsIter):
            deselect = touchedRows & selectedRows
            if not deselect:
                continue
            changeMap[selectionModel] = set(), deselect
        return changeMap

    @staticmethod
    def _selectToggle(selectionModels, itemsIter):
        changeMap = {}
        for selectionModel, selectedRows, touchedRows in TimelineMarqueeAction._preProcess(selectionModels, itemsIter):
            deselect = touchedRows & selectedRows
            select = touchedRows - deselect
            if not select and not deselect:
                continue
            changeMap[selectionModel] = select, deselect
        return changeMap

    def _createCommand(self, selectionModels, changeMap):
        """
        # TODO: If we instead were editing one single model, and our other views were just filtered versions of the same model, this can become so much simpler
        So the SelectionModelEdit does not actually change anything as it reacts to changes
        by Qt views to a selectionModel. We just retroactively try to make those selection changes undoable.
        If we want to push selection changes, which would work as normal and push undo commands to the stack for free.
        But now we want to push multiple selection changes as 1 undo macro.
        """
        self._undoStack.beginMacro('Multi-selection model edit')
        for selectionModel, change in changeMap.iteritems():

            model = selectionModel.model()
            added = QItemSelection()
            removed = QItemSelection()

            for row in change[0]:
                left = model.index(row, 0)
                right = model.index(row, model.columnCount() - 1)
                added.select(left, right)

            for row in change[1]:
                left = model.index(row, 0)
                right = model.index(row, model.columnCount() - 1)
                removed.select(left, right)

            selectionModel.select(added, QItemSelectionModel.Select)
            selectionModel.select(removed, QItemSelectionModel.Deselect)
        self._undoStack.endMacro()


class TimelineView(GridView):
    def __init__(self, timer, undoStack, demoModel, selectionModels):
        super(TimelineView, self).__init__(mask=1)

        self.__demoModel = demoModel
        self.__selectionModels = selectionModels
        for selectionModel in selectionModels:
            selectionModel.selectionChanged.connect(self.repaint)
        demoModel.dataChanged.connect(self.layout)
        demoModel.rowsInserted.connect(self.layout)
        demoModel.rowsRemoved.connect(self.layout)

        self._timer = timer
        timer.timeChanged.connect(self.repaint)
        self._undoStack = undoStack
        self.setMouseTracking(True)
        self.__graphicsItems = []
        self.frameAll()
        self._viewRect.changed.connect(self.layout)
        self._viewRect.changed.disconnect(self.repaint)  # layout already calls repaint
        self._copyPasteAction = None

    def resizeEvent(self, event):
        self.layout()

    def __iterAllItemRows(self):
        for row in xrange(self.__demoModel.rowCount()):
            yield self.__demoModel.item(row, 0).data()

    def layout(self):
        del self.__graphicsItems[:]
        scaleX = self.width() / (self._viewRect.right - self._viewRect.left)
        for pyObj in self.__iterAllItemRows():
            x = round((pyObj.start - self._viewRect.left) * scaleX)
            w = round((pyObj.end - self._viewRect.left) * scaleX - x)
            isShot = isinstance(pyObj, Shot)
            if isShot:
                item = GraphicsItemShot(pyObj, x, w)
            else:
                item = GraphicsItemEvent(pyObj, x, w)
            self.__graphicsItems.append(item)
        self.repaint()

    def itemsAt(self, x, y, w, h):
        rect = QRect(x, y, w, h)
        for item in self.__graphicsItems:
            if item.rect.contains(rect) or item.rect.intersects(rect):
                yield item

    def _reproject(self, x, y):
        return self.xToT(x), y

    def _selectedItems(self):
        for selectionModel in self.__selectionModels:
            for row in set(selectionModel.model().mapToSource(idx).row() for idx in selectionModel.selectedRows()):
                yield self.__demoModel.item(row).data()

    @staticmethod
    def _itemHandleAt(itemRect, pos):
        # reimplemented from GraphicsItemEvent.mouseMoveEvent
        # returns a mask for what part of the event is clicked (start=1, right=2, both=3)
        if itemRect.width() > GraphicsItemEvent.handleWidth * 3:
            lx = pos.x() - itemRect.x()
            if lx < GraphicsItemEvent.handleWidth:
                return 1
            elif lx > itemRect.width() - GraphicsItemEvent.handleWidth:
                return 2
        return 3

    def mousePressEvent(self, event):
        if event.modifiers() & Qt.AltModifier:
            super(TimelineView, self).mousePressEvent(event)
            # creating self._action, calling it's mousePressEvent and repainting is handled in base class
            return

        elif event.button() == Qt.RightButton:
            # Right button moves the time slider
            self._action = MoveTimeAction(self._timer.time, self.xToT, functools.partial(self._timer.__setattr__, 'time'))

        elif event.button() == Qt.LeftButton:
            # Drag selected timeline item under mouse
            items = set(self.itemsAt(event.x(), event.y(), 1, 1))
            events = {item.event for item in items}
            selected = set(self._selectedItems())
            if events & selected:
                handle = 3
                for item in items:
                    handle = self._itemHandleAt(item.rect, event.pos())
                    break
                self._action = MoveEventAction(self._reproject, self.cellSize(self.width(), self._viewRect.left, self._viewRect.right), selected, handle)

        if not self._action:
            # else we start a new selection action
            self._action = TimelineMarqueeAction(self, self.__selectionModels, self._undoStack)

        if self._action.mousePressEvent(event):
            self.repaint()

    def mouseMoveEvent(self, event):
        if self._action:
            super(TimelineView, self).mouseMoveEvent(event)
            return

        if event.button():
            return

        dirty = False
        pos = event.pos()
        for item in self.__graphicsItems:
            dirty = dirty or item.mouseMoveEvent(pos)
        if dirty:
            self.repaint()

    def mouseReleaseEvent(self, event):
        action = self._action
        self._action = None
        # make sure self.action is None before calling mouseReleaseEvent so that:
        # 1. when returning True we will clear any painting done by self.action during mousePress/-Move
        # 2. when a callback results in a repaint the above holds true
        if action and action.mouseReleaseEvent(self._undoStack):
            self.repaint()

    def leaveEvent(self, event):
        dirty = False
        for item in self.__graphicsItems:
            dirty = dirty or item.focusOutEvent()
        if dirty:
            self.repaint()

    def paintEvent(self, event):
        super(TimelineView, self).paintEvent(event)

        selectedPyObjs = set()
        for selectionModel in self.__selectionModels:
            selectedPyObjs |= {idx.data(Qt.UserRole + 1) for idx in selectionModel.selectedRows()}

        painter = QPainter(self)
        for item in self.__graphicsItems:
            isSelected = item.event in selectedPyObjs
            item.paint(painter, isSelected)

        # paint playhead
        x = self.tToX(self._timer.time)
        drawPlayhead(painter, x, self.height())

        # paint loop range
        loopStart = self._timer.loopStart
        loopEnd = self._timer.loopEnd
        if 0 <= loopStart < loopEnd:
            loopStart = self.tToX(loopStart)
            loopEnd = self.tToX(loopEnd)
            drawLoopRange(painter, loopStart, loopEnd, self.width(), self.height())

        if self._action is not None:
            self._action.draw(painter)

    def frameAll(self):
        self.__frameView()

    def __iterSelectedItemRows(self):
        for selectionModel in self.__selectionModels:
            for idx in selectionModel.selectedRows():
                yield idx.data(Qt.UserRole + 1)

    def __frameView(self, pyObjs=tuple()):
        if not pyObjs:
            pyObjs = self.__iterAllItemRows()
        start = float('inf')
        end = float('-inf')
        for pyObj in pyObjs:
            start = min(start, pyObj.start)
            end = max(end, pyObj.end)
        try:
            assert start < end
        except AssertionError:
            start = 0.0
            end = 1.0
        self._viewRect.left = start
        self._viewRect.right = end

    def keyPressEvent(self, event):
        if event.key() == Qt.Key_F:
            # frame view to selected
            self.__frameView(tuple(self.__iterSelectedItemRows()))

        if event.key() == Qt.Key_A:
            # frame view to all content
            self.frameAll()

        if event.key() == Qt.Key_Delete:
            # delete selected
            rows = set()
            for selectionModel in self.__selectionModels:
                # We get the pyObj which contains the source items to get source model row, as idx.row() just contains proxy data.
                rows |= {idx.data(Qt.UserRole + 1).items[0].row() for idx in selectionModel.selectedRows()}
            if rows:
                # Macro to catch selection changes and group them with the delete action
                self._undoStack.beginMacro('Delete timeline items')
                try:
                    self._undoStack.push(ModelEdit(self.__demoModel, [], list(rows)))
                finally:
                    self._undoStack.endMacro()
                self.layout()
                return

        if event.key() == Qt.Key_D and event.modifiers() & Qt.ControlModifier:
            # Duplicate items
            selected = list(self._selectedItems())
            if self._action is None:
                self._action = DuplicateEventAction(selected, self.__models, self._undoStack)

            if self._action.keyPressEvent(event):
                self.layout()

        if event.matches(QKeySequence.Copy):
            # Copy items
            # TODO: What happens when we copy something somewhere else in the UI?
            selected = list(self._selectedItems())
            self._copyPasteAction = DuplicateEventAction(selected, self.__models, self._undoStack)

        if event.matches(QKeySequence.Paste) and self._copyPasteAction:
            # Paste items
            if self._copyPasteAction.keyPressEvent(event):
                self.layout()

    def keyReleaseEvent(self, event):
        if event.key() == Qt.Key_Control:
            if isinstance(self._action, DuplicateEventAction):
                self._action = None


def muteState():
    return settings().value('mute', 'False') == 'True'


def setMuteState(state):
    settings().setValue('mute', str(bool(state)))


class TimelineManager(QWidget):
    def __init__(self, timer, undoStack, demoModel, selectionModels, parent=None):
        super(TimelineManager, self).__init__(parent)
        layout = vlayout()
        self.setLayout(layout)

        hbar = hlayout()
        layout.addLayout(hbar)

        self.view = TimelineView(timer, undoStack, demoModel, selectionModels)
        layout.addWidget(self.view)
        layout.setStretch(1, 1)

        currentSeconds = TimestampDisplay(timer)
        currentSeconds.setToolTip('Current time in minutes:seconds,milliseconds')
        currentSeconds.setStatusTip('Current time in minutes:seconds,milliseconds')
        currentSeconds.setMinimumWidth(70)
        hbar.addWidget(currentSeconds)
        timer.timeChanged.connect(currentSeconds.update)

        loopStart = DoubleSpinBox()
        loopStart.setToolTip('Loop start')
        loopStart.setStatusTip('Loop start')
        loopStart.valueChanged.connect(timer.setLoopStart)
        timer.loopStartChanged.connect(loopStart.setValue)
        hbar.addWidget(loopStart)

        loopEnd = DoubleSpinBox()
        loopEnd.setToolTip('Loop end')
        loopEnd.setStatusTip('Loop end')
        loopEnd.valueChanged.connect(timer.setLoopEnd)
        timer.loopEndChanged.connect(loopEnd.setValue)
        hbar.addWidget(loopEnd)

        bpm = BPMInput(int(round(timer.bpm)))
        bpm.setToolTip('Beats per minute')
        bpm.setStatusTip('Beats per minute, determines playback speed')
        bpm.spinBox().setMinimum(1)
        bpm.spinBox().valueChanged.connect(timer.setBpm)
        timer.bpmChanged.connect(bpm.setValueSilent)
        hbar.addWidget(bpm)

        self.__playPause = QPushButton(icons.get('Play'), '')
        self.__playPause.setToolTip('Play')
        self.__playPause.setStatusTip('Play')
        self.__playPause.setFixedWidth(24)
        hbar.addWidget(self.__playPause)
        shortcut0 = QShortcut(self)
        shortcut0.setKey(QKeySequence(Qt.Key_Space))
        shortcut0.setContext(Qt.ApplicationShortcut)
        shortcut1 = QShortcut(self)
        shortcut1.setKey(QKeySequence(Qt.Key_P))
        shortcut1.setContext(Qt.ApplicationShortcut)
        self.__playPause.clicked.connect(self.__togglePlayPause)
        self.__playPause.clicked.connect(timer.playPause)
        shortcut0.activated.connect(self.__togglePlayPause)
        shortcut0.activated.connect(timer.playPause)
        shortcut1.activated.connect(self.__togglePlayPause)
        shortcut1.activated.connect(timer.playPause)

        isMuted = muteState()
        self.__mute = QPushButton(icons.get('Mute') if isMuted else icons.get('Medium Volume'), '')
        self.__mute.setToolTip('Un-mute' if isMuted else 'Mute')
        self.__mute.setStatusTip('Un-mute' if isMuted else 'Mute')
        self.__mute.clicked.connect(self.__toggleMute)
        self.__mute.setFixedWidth(24)
        hbar.addWidget(self.__mute)
        self.__soundtrack = None

        hbar.addStretch(1)

    def __togglePlayPause(self):
        if self.__playPause.toolTip() == 'Play':
            self.__playPause.setIcon(icons.get('Pause'))
            self.__playPause.setToolTip('Pause')
            self.__playPause.setStatusTip('Pause')
            self.__playSoundtrack()
        else:
            self.__playPause.setIcon(icons.get('Play'))
            self.__playPause.setToolTip('Play')
            self.__playPause.setStatusTip('Play')
            self.__stopSoundtrack()

    def __initAndStartSoundtrack(self):
        if muteState():
            return

        if self.__soundtrack:
            self.__soundtrack.play()
            return self.__soundtrack

        path = None
        song = None
        for ext in ('.wav', '.mp3'):
            for fname in os.listdir(projectFolder()):
                if fname.lower().endswith(ext):
                    try:
                        path = os.path.join(projectFolder(), fname)
                        song = pyglet.media.load(path)
                    except Exception, e:
                        print 'Found a soundtrack that we could not play. pyglet or mp3 libs missing?\n%s' % e.message
                        return
                    break
            if song:
                break
        if not song:
            return

        self.__soundtrackPath = path
        self.__soundtrack = song.play()
        self.__soundtrack.volume = 0 if muteState() else 100
        return self.__soundtrack

    def __seekSoundtrack(self, time):
        if self.__playPause.toolTip() == 'Play':
            # no need to seek when not playing
            self.__stopSoundtrack()
            return
        if self.__initAndStartSoundtrack():
            self.__soundtrack.seek(self.__timer.beatsToSeconds(time))

    def __playSoundtrack(self):
        if self.__initAndStartSoundtrack():
            self.__soundtrack.seek(self.__timer.beatsToSeconds(self.__timer.time))

    def __stopSoundtrack(self):
        if self.__soundtrack:
            self.__soundtrack.pause()
        self.__soundtrack = None

    def __toggleMute(self):
        isMuted = not muteState()
        setMuteState(isMuted)

        self.__mute.setIcon(icons.get('Mute') if isMuted else icons.get('Medium Volume'))
        self.__mute.setToolTip('Un-mute' if isMuted else 'Mute')
        self.__mute.setStatusTip('Un-mute' if isMuted else 'Mute')

        if self.__soundtrack:  # re-applies the mute state if soundtrack already exists
            self.__soundtrack.volume = 0 if muteState() else 100

    def soundtrackPath(self):
        return self.__soundtrackPath
