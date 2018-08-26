import re
import functools
import icons
from experiment.actions import KeyEdit, CurveModelEdit
from experiment.curvemodel import HermiteCurve, ETangentMode, ELoopMode
from experiment.curveview import CurveView
from experiment.delegates import UndoableSelectionView
from experiment.model import Shot, Clip, Event
from qtutil import *


def sign(x): return -1 if x < 0 else 1


class CurveList(UndoableSelectionView):
    def __init__(self, clipManagerSelectionChange, firstSelectedClip, undoStack, parent=None):
        # TODO: Instead of passing in a ClipManager instance (source) perhaps we can get a selectionChange signal & a "getFirstSelectedItem" callable that returns an ItemRow instance
        super(CurveList, self).__init__(undoStack, parent)
        self.setModel(QStandardItemModel())
        self._firstSelectedItem = firstSelectedClip
        clipManagerSelectionChange.connect(self._pull)

    def dataChanged(self, firstIndex, lastIndex):
        # there
        pass

    @staticmethod
    def columnNames():
        return HermiteCurve.properties()

    def _pull(self, *args):
        # get first selected container
        clip = self._firstSelectedItem()
        curves = None
        if clip:
            curves = clip.curves
        if self.model() == curves:
            return
        if curves is None:
            self.clearSelection()
        self.setModel(curves)
        self._updateNames()
        self.selectAll()


def createToolButton(iconName, toolTip, parent):
    btn = QPushButton(icons.get(iconName), '')
    btn.setToolTip(toolTip)
    btn.setStatusTip(toolTip)
    parent.addWidget(btn)
    return btn


class CurveUI(QWidget):
    # TODO: Show which clip / shot is active somehow (window title?)
    def __init__(self, timer, clipManagerSelectionChange, firstSelectedClip, firstSelectedEventWithClip, undoStack):
        super(CurveUI, self).__init__()
        self._undoStack = undoStack

        mainLayout = vlayout()
        self.setLayout(mainLayout)
        toolBar = hlayout()

        createToolButton('Add Node-48', 'Add channel', toolBar).clicked.connect(self.__addChannel)

        btn = createToolButton('Delete Node-48', 'Remove selected channels', toolBar)
        btn.clicked.connect(self.__deleteChannels)
        self._curveActions = [btn]

        self._relative = QCheckBox()
        self._time = QDoubleSpinBox()
        self._value = QDoubleSpinBox()

        toolBar.addWidget(QLabel('Relative:'))
        toolBar.addWidget(self._relative)
        toolBar.addWidget(QLabel('Time:'))
        toolBar.addWidget(self._time)
        toolBar.addWidget(QLabel('Value:'))
        toolBar.addWidget(self._value)

        self._time.editingFinished.connect(self.__timeChanged)
        self._value.editingFinished.connect(self.__valueChanged)

        self._keyActions = [self._time, self._value]

        btn = createToolButton('tangent-auto', 'Set selected tangents to Auto', toolBar)
        btn.clicked.connect(functools.partial(self.__setTangentMode, ETangentMode.Auto))
        self._keyActions.append(btn)
        btn = createToolButton('tangent-spline', 'Set selected tangents to Spline', toolBar)
        btn.clicked.connect(functools.partial(self.__setTangentMode, ETangentMode.Spline))
        self._keyActions.append(btn)
        btn = createToolButton('tangent-linear', 'Set selected tangents to Linear', toolBar)
        btn.clicked.connect(functools.partial(self.__setTangentMode, ETangentMode.Linear))
        self._keyActions.append(btn)
        btn = createToolButton('tangent-flat', 'Set selected tangents to Flat', toolBar)
        btn.clicked.connect(functools.partial(self.__setTangentMode, ETangentMode.Flat))
        self._keyActions.append(btn)
        btn = createToolButton('tangent-stepped', 'Set selected tangents to Stepped', toolBar)
        btn.clicked.connect(functools.partial(self.__setTangentMode, ETangentMode.Stepped))
        self._keyActions.append(btn)
        btn = createToolButton('tangent-broken', 'Set selected tangents to Custom', toolBar)
        btn.clicked.connect(functools.partial(self.__setTangentMode, ETangentMode.Custom))
        self._keyActions.append(btn)

        btn = createToolButton('Move-48', 'Key camera position into selected channels', toolBar)
        btn.clicked.connect(self.__copyCameraPosition)
        self._curveActions.append(btn)
        btn = createToolButton('3D Rotate-48', 'Key camera radians into selected channels', toolBar)
        btn.clicked.connect(self.__copyCameraAngles)
        self._curveActions.append(btn)

        btn = createToolButton('Duplicate-Keys-24', 'Duplicated selected keys', toolBar)
        btn.clicked.connect(self.__copyKeys)
        self._keyActions.append(btn)

        toolBar.addStretch(1)

        splitter = QSplitter(Qt.Horizontal)
        clipManagerSelectionChange.connect(self.__activeClipChanged)
        self._firstSelectedClip = firstSelectedClip
        self._firstSelectedEventWithClip = firstSelectedEventWithClip

        self._curveList = CurveList(clipManagerSelectionChange, firstSelectedClip, undoStack)
        self._curveList.selectionChange.connect(self.__visibleCurvesChanged)

        self._curveView = CurveView(timer, self._curveList, undoStack)
        self._curveView.requestAllCurvesVisible.connect(self._curveList.selectAll)
        self._curveView.selectionModel.changed.connect(self.__keySelectionChanged)

        def forwardFocus(event):
            self._curveView.setFocus(Qt.MouseFocusReason)

        self._curveList.focusInEvent = forwardFocus

        splitter.addWidget(self._curveList)
        splitter.addWidget(self._curveView)

        mainLayout.addLayout(toolBar)
        mainLayout.addWidget(splitter)
        mainLayout.setStretch(0, 0)
        mainLayout.setStretch(1, 1)

        self._toolBar = toolBar
        toolBar.setEnabled(False)

    def setEvent(self, event):
        self._curveView.setEvent(event)

    def __activeClipChanged(self):
        clip = self._firstSelectedClip()
        self._toolBar.setEnabled(bool(clip))

        event = self._firstSelectedEventWithClip(clip)
        self._curveView.setEvent(event)

    def __visibleCurvesChanged(self):
        state = self._curveView.hasVisibleCurves()
        for action in self._curveActions:
            action.setEnabled(state)

    def __keySelectionChanged(self):
        # set value and time fields to match selection
        cache = None
        for key, mask in self._curveView.selectionModel.iteritems():
            if not mask & 1:
                continue
            if cache is None:
                cache = key
            else:
                break
        if not cache:
            for action in self._keyActions:
                action.setEnabled(False)
            return
        for action in self._keyActions:
            action.setEnabled(True)
        self._time.setValue(cache.x)
        self._value.setValue(cache.y)

    def __valueChanged(self, value):
        restore = {}
        for key, mask in self._curveView.selectionModel.iteritems():
            if not mask & 1:
                continue
            restore[key] = key.copyData()
            key.y = value
        self._undostack.push(KeyEdit(restore, self._curveView.repaint))

    def __timeChanged(self, value):
        restore = {}
        for key, mask in self._curveView.selectionModel.iteritems():
            if not mask & 1:
                continue
            restore[key] = key.copyData()
            key.x = value
        self._undostack.push(KeyEdit(restore, self._curveView.repaint))

    def __setTangentMode(self, tangentMode):
        restore = {}
        dirty = False
        for key, mask in self._curveView.selectionModel.iteritems():
            restore[key] = key.copyData()
            if mask & 2:
                key.inTangentMode = tangentMode
                dirty = True

            if mask & 4:
                key.outTangentMode = tangentMode
                dirty = True

            if mask == 1:
                key.inTangentMode = tangentMode
                key.outTangentMode = tangentMode
                dirty = True

            key.computeTangents()

        if not dirty:
            return

        self._undoStack.push(KeyEdit(restore, self._curveView.repaint))
        self.repaint()

    def __addChannel(self):
        res = QInputDialog.getText(self, 'Create channel',
                                   'Name with optional [xy], [xyz], [xyzw] suffix\n'
                                   'e.g. "uPosition[xyz]", "uSize[xy]".')
        if not res[1] or not res[0]:
            return
        pat = re.compile(r'^[a-zA-Z_0-9]+(\[[x][y]?[z]?[w]?\])?$')
        if not pat.match(res[0]):
            QMessageBox.critical(self, 'Could not add attribute',
                                 'Invalid name or channel pattern given. '
                                 'Please use only alphanumeric characters and undersores;'
                                 'also use only these masks: [x], [xy], [xyz], [xyzw].')
            return
        if '[' not in res[0]:
            channelNames = [res[0]]
        else:
            channelNames = []
            attr, channels = res[0].split('[', 1)
            channels, remainder = channels.split(']')
            for channel in channels:
                channelNames.append('%s.%s' % (attr, channel))

        mdl = self._curveList.model()
        for channelName in channelNames:
            if mdl.findItems(channelName):
                QMessageBox.critical(self, 'Could not add attribute',
                                     'An attribute with name "%s" already exists.\n'
                                     'No attributes were added.' % channelName)
                return

        newCurves = []
        for channelName in channelNames:
            newCurves.append(HermiteCurve(channelName, ELoopMode.Clamp, []))
        if not newCurves:
            return
        self._undoStack.push(CurveModelEdit(mdl, newCurves, []))

    def __deleteChannels(self):
        rows = []
        for index in self._curveList.selectionModel().selectedRows():
            rows.append(index.row())
        if not rows:
            return
        mdl = self._curveList.model()
        self._undoStack.push(CurveModelEdit(mdl, [], rows))

    def __copyCameraPosition(self):
        # TODO
        raise NotImplementedError()

    def __copyCameraAngles(self):
        # TODO
        raise NotImplementedError()

    def __copyKeys(self):
        # TODO
        raise NotImplementedError()


class NamedProxyModel(QSortFilterProxyModel):
    """
    Base model to filter a specific ItemRow subclass
    """

    def __init__(self, source):
        super(NamedProxyModel, self).__init__()
        self.setSourceModel(source)

    def setHorizontalHeaderLabels(self, labels):
        # worked around in headerData
        pass

    def headerData(self, section, orientation, role=None):
        if orientation == Qt.Horizontal:
            if role == Qt.DisplayRole:
                return self.filterClass().properties()[section]
            if role == Qt.TextAlignmentRole:
                return Qt.AlignLeft
        return super(NamedProxyModel, self).headerData(section, orientation, role)

    def appendRow(self, *args):
        self.sourceModel().appendRow(*args)

    def filterAcceptsRow(self, sourceRow, sourceParent):
        return isinstance(self.sourceModel().item(sourceRow).data(), self.filterClass())

    def filterAcceptsColumn(self, sourceColumn, sourceParent):
        return sourceColumn < len(self.filterClass().properties())

    @classmethod
    def filterClass(cls):
        raise NotImplementedError


class ShotModel(NamedProxyModel):
    @classmethod
    def filterClass(cls):
        return Shot


class EventModel(NamedProxyModel):
    @classmethod
    def filterClass(cls):
        return Event


class FilteredView(UndoableSelectionView):
    def __init__(self, undoStack, model, parent=None):
        super(FilteredView, self).__init__(undoStack, parent)
        self.setModel(model)
        model.sourceModel().itemChanged.connect(self.__fwdItemChanged)

    def __fwdItemChanged(self, item):
        self.model().sourceModel().item(item.row()).data().propertyChanged(item.column())

    def updateSections(self):
        if self.model():
            n = len(self.model().filterClass().properties()) - 1
            self.horizontalHeader().setDefaultAlignment(Qt.AlignLeft)
            self.horizontalHeader().setResizeMode(0, QHeaderView.Interactive)
            for i in xrange(1, n):
                self.horizontalHeader().setResizeMode(i, QHeaderView.ResizeToContents)
            self.horizontalHeader().setResizeMode(n, QHeaderView.Stretch)

    def columnNames(self):
        return self.model().filterClass().properties()


class EventView(FilteredView):
    def firstSelectedEventWithClip(self, clip):
        pyObj = None
        for container in self.selectionModel().selectedRows():
            pyObj = container.data(Qt.UserRole + 1)
            if pyObj.clip != clip:
                pyObj = None
            else:
                break
        return pyObj


class ClipManager(UndoableSelectionView):
    def __init__(self, source, undoStack, parent=None):
        super(ClipManager, self).__init__(undoStack, parent)
        self.setModel(QStandardItemModel())
        self._source = source
        source.selectionChange.connect(self._pull)

    def firstSelectedItem(self):
        clip = None
        for container in self.selectionModel().selectedRows():
            clip = container.data(Qt.UserRole + 1)
            break
        return clip

    def _pull(self, *args):
        # get first selected container
        pyObj = None  # empty stub
        for container in self._source.selectionModel().selectedRows():
            pyObj = container.data(Qt.UserRole + 1)
            break
        if pyObj is None:
            return
        items = self.model().findItems(str(pyObj.clip))
        if items:
            index = self.model().indexFromItem(items[0])
            self.selectionModel().select(index, QItemSelectionModel.ClearAndSelect | QItemSelectionModel.Rows)

    @staticmethod
    def columnNames():
        return Clip.properties()


class ClipUI(QWidget):
    def __init__(self, source, undoStack, parent=None):
        super(ClipUI, self).__init__(parent)
        main = vlayout()
        self.setLayout(main)
        hbar = hlayout()
        hbar.addWidget(createToolButton('Add Node-48', 'Create clip', hbar))
        hbar.addWidget(createToolButton('Delete Node-48', 'Delete selected clips', hbar))
        main.addLayout(hbar)
        self.manager = ClipManager(source, undoStack)
        main.addWidget(self.manager)
