import re
import functools
import icons
from experiment.actions import KeyEdit, ModelEdit
from experiment.curvemodel import HermiteCurve, ETangentMode, ELoopMode, HermiteKey, EInsertMode
from experiment.curveview import CurveView
from experiment.delegates import UndoableSelectionView
from experiment.demomodel import CreateShotDialog, CreateEventDialog
from experiment.model import Shot, Clip, Event
from experiment.modelbase import UndoableModel
from qtutil import *


def sign(x): return -1 if x < 0 else 1


class CurveList(UndoableSelectionView):
    def __init__(self, clipManagerSelectionChange, firstSelectedClip, undoStack, parent=None):
        super(CurveList, self).__init__(undoStack, parent)
        self.setModel(None)
        self._firstSelectedItem = firstSelectedClip
        clipManagerSelectionChange.connect(self._pull)

    @staticmethod
    def columnNames():
        return HermiteCurve.properties()

    def keyCamera(self, camera, time):
        curves = self.model()
        if curves is None:
            # no event to key into
            # TODO: alert the user about this?
            return

        cameraData = camera.data().data
        for i, attr in enumerate(('uOrigin.x', 'uOrigin.y', 'uOrigin.z', 'uAngles.x', 'uAngles.y', 'uAngles.z')):
            items = curves.findItems(attr)
            if not items:
                curve = HermiteCurve(attr)
                curves.appendRow(curve.items)
            else:
                curve = items[0].data()
            # TODO: Attempt to get continuity with best tangents and set tangents to custom
            curve.insertKey(HermiteKey(time, cameraData[i], 0.0, 0.0, ETangentMode.Spline, ETangentMode.Spline, curve), EInsertMode.Copy)

    def _pull(self, *__):
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

        def forwardFocus(__):
            self._curveView.setFocus(Qt.MouseFocusReason)

        self._curveList.focusInEvent = forwardFocus

        splitter.addWidget(self._curveList)
        splitter.addWidget(self._curveView)

        self._toolBar = QWidget()
        self._toolBar.setLayout(toolBar)
        self._toolBar.setEnabled(False)

        mainLayout.addWidget(self._toolBar)
        mainLayout.addWidget(splitter)
        mainLayout.setStretch(0, 0)
        mainLayout.setStretch(1, 1)

    def keyCamera(self, camera):
        self.curveList.keyCamera(camera, self._curveView.time)
        self._curveView.repaint()

    @property
    def curveList(self):
        return self._curveList

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
                                 'Please use only alphanumeric characters and underscores;'
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
        self._undoStack.push(ModelEdit(mdl, newCurves, []))

    def __deleteChannels(self):
        rows = []
        for index in self._curveList.selectionModel().selectedRows():
            rows.append(index.row())
        if not rows:
            return
        mdl = self._curveList.model()
        self._undoStack.push(ModelEdit(mdl, [], rows))

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
    # TODO: Can not edit multiple elements at the same time, event when selecting multiple rows and using e.g. F2 to edit the item.
    # Override edit as described here https://stackoverflow.com/questions/14586715/how-can-i-achieve-to-update-multiple-rows-in-a-qtableview ?
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
    # TODO: Move these functions to EventManager
    def firstSelectedEvent(self):
        for container in self.selectionModel().selectedRows():
            return container.data(Qt.UserRole + 1)

    def firstSelectedEventWithClip(self, clip):
        for container in self.selectionModel().selectedRows():
            pyObj = container.data(Qt.UserRole + 1)
            if pyObj.clip == clip:
                return pyObj


class ClipManager(UndoableSelectionView):
    def __init__(self, selectionChange, firstSelectedEvent, undoStack, parent=None):
        super(ClipManager, self).__init__(undoStack, parent)
        self.setModel(UndoableModel(undoStack))
        self._firstSelectedEvent = firstSelectedEvent
        selectionChange.connect(self._pull)

    def firstSelectedItem(self):
        clip = None
        for container in self.selectionModel().selectedRows():
            clip = container.data(Qt.UserRole + 1)
            break
        return clip

    def _pull(self, *__):
        # get first selected container
        pyObj = self._firstSelectedEvent()
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
    requestEvent = pyqtSignal(Clip)

    def __init__(self, selectionChange, firstSelectedEvent, undoStack, parent=None):
        super(ClipUI, self).__init__(parent)
        main = vlayout()
        self.setLayout(main)

        hBar = hlayout()

        btn = createToolButton('Film Reel Create-48', 'Create clip', hBar)
        btn.clicked.connect(self.createClip)
        btn.setIconSize(QSize(24, 24))

        btn = createToolButton('Film Reel Delete-48', 'Delete selected clips', hBar)
        btn.setIconSize(QSize(24, 24))
        btn.clicked.connect(self.__deleteSelectedClips)

        hBar.addStretch(1)

        main.addLayout(hBar)
        self.manager = ClipManager(selectionChange, firstSelectedEvent, undoStack)
        self.manager.setContextMenuPolicy(Qt.CustomContextMenu)
        self.manager.customContextMenuRequested.connect(self.__clipContextMenu)
        main.addWidget(self.manager)

        self.undoStack = undoStack
        self.__contextMenu = QMenu()  # reference to avoid aggressive garbage collection

    def __clipContextMenu(self, pos):
        idx = self.manager.indexAt(pos)
        if not idx.isValid():
            return
        idx = idx.sibling(idx.row(), 0)
        clip = idx.data(Qt.UserRole + 1)
        self.__contextMenu.clear()
        self.__contextMenu.addAction('Create event').triggered.connect(functools.partial(self.requestEvent.emit, clip))
        self.__contextMenu.popup(self.manager.mapToGlobal(pos))

    def createClip(self, defaultUniforms={}):
        result = QInputDialog.getText(self, 'Create clip', 'Clip name')
        if not result[0] or not result[1]:
            return
        name = result[0]
        # ensure name is unique
        if self.manager.model().findItems(name):
            QMessageBox.critical(self, 'Error creating clip', ' A clip named %s already exists' % name)
            return
        clip = Clip(name, self.undoStack)

        for curveName, value in defaultUniforms.iteritems():
            curve = HermiteCurve(curveName, data=[HermiteKey(0.0, value, 0.0, 0.0, ETangentMode.Flat, ETangentMode.Flat)])
            clip.curves.appendRow(curve.items)

        self.undoStack.push(ModelEdit(self.manager.model(), [clip], []))

    def __deleteSelectedClips(self):
        # TODO: Delete adds a selection change to the undo stack as well, should macro it somehow
        # TODO: Delete must delete events using this clip as well
        rows = [idx.row() for idx in self.manager.selectionModel().selectedRows()]
        if not rows:
            return
        self.undoStack.push(ModelEdit(self.manager.model(), [], rows))


class GenericManager(QWidget):
    def __init__(self, undoStack, demoModel, timer, parent=None):
        super(GenericManager, self).__init__(parent)
        self.timer = timer

        layout = vlayout()
        self.setLayout(layout)

        toolBar = hlayout()
        layout.addLayout(toolBar)

        createBtn = QPushButton(icons.get(self._createIcon), '')
        toolBar.addWidget(createBtn)
        createBtn.setToolTip(self._createLabel)
        createBtn.setStatusTip(self._createLabel)

        deleteBtn = QPushButton(icons.get(self._deleteIcon), '')
        toolBar.addWidget(deleteBtn)
        deleteBtn.setToolTip(self._deleteLabel)
        deleteBtn.setStatusTip(self._deleteLabel)

        toolBar.addStretch(1)

        self.undoStack = undoStack
        self.view = self._viewClass(undoStack, self._modelClass(demoModel))
        layout.addWidget(self.view)
        layout.setStretch(1, 1)

        createBtn.clicked.connect(self.create)
        deleteBtn.clicked.connect(self.deleteSelected)

    def create(self):
        itemRow = self._dialog(round(self.timer.time), None, self)
        if itemRow is not None:
            model = self.view.model().sourceModel()
            # TODO: find a vacant track in the current model to set the event track
            self.undoStack.push(ModelEdit(model, [itemRow], []))

    def deleteSelected(self):
        pyObjs = set()
        for idx in self.view.selectionModel().selectedIndexes():
            pyObjs.add(idx.sibling(idx.row(), 0).data(Qt.UserRole + 1))
        for pyObj in pyObjs:
            model = self.view.model().sourceModel()
            self.undoStack.push(ModelEdit(model, [], [pyObj.items[0].row()]))


class ShotManager(GenericManager):
    _createIcon = 'Film Strip Create-48'
    _createLabel = 'Create shot'
    _deleteIcon = 'Film Strip Delete-48'
    _deleteLabel = 'Delete selected shots'
    _modelClass = ShotModel
    _viewClass = FilteredView
    _dialog = CreateShotDialog.run


class EventManager(GenericManager):
    _createIcon = 'Curves Create-48'
    _createLabel = 'Create event'
    _deleteIcon = 'Curves Delete-48'
    _deleteLabel = 'Delete selected events'
    _modelClass = EventModel
    _viewClass = EventView

    def __init__(self, undoStack, demoModel, timer, parent=None):
        super(EventManager, self).__init__(undoStack, demoModel, timer, parent)
        self._dialog = self.runDialog
        self.iterClips = None

    def runDialog(self, *args):
        return CreateEventDialog.run(list(self.iterClips()), *args)
