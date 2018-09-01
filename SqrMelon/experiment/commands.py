from qtutil import *
from typing import Dict


def unpackModelIndex(qIndex):
    """
    We had some problems retaining model indices for a long time,
    so here they get deconstructed to their most basic part:
    a row, column, parent where parent is recursively unpacked.
    """
    x = qIndex.column()
    y = qIndex.row()
    p = qIndex.parent()
    if p.isValid():
        return x, y, unpackModelIndex(p)
    return x, y, None


def constructModelIndex(model, unpacked):
    """
    We had some problems retaining model indices for a long time,
    so here they get reconstructed from their most basic part:
    a row, column, parent where parent is recursively constructed.
    """
    if unpacked[2] is not None:
        parent = constructModelIndex(model, unpacked[2])
    else:
        parent = QModelIndex()
    return model.index(unpacked[1], unpacked[0], parent)


class RecursiveCommandError(Exception):
    pass


class NestedCommand(QUndoCommand):
    """
    Utility to avoid reo() and undo() of a command creating additional commands.

    The idea is to:
    - use only NestedCommand objects when this problem occurs
    - catch RecursiveCommandError exceptions and then avoid doing the action
    - check if canPush is True so that these commands are pushed only at the right times

    NestedCommand without a parent is implicitly parented if it is created during redo() of another NestedCommand.
    """
    stack = []
    isUndo = False

    def __init__(self, label, parent=None):
        # if signal responses to undo() create additional commands we avoid creation
        if NestedCommand.isUndo:
            raise RecursiveCommandError()
        # if signal responses to redo() create additional commands we group them
        if NestedCommand.stack and parent is None:
            parent = NestedCommand.stack[-1]
        self.canPush = parent is None
        super(NestedCommand, self).__init__(label, parent)

    def _redoInternal(self):
        raise NotImplementedError()

    def _undoInternal(self):
        raise NotImplementedError()

    def redo(self):
        NestedCommand.stack.append(self)
        super(NestedCommand, self).redo()
        self._redoInternal()
        NestedCommand.stack.pop(-1)

    def undo(self):
        NestedCommand.isUndo = True
        self._undoInternal()
        super(NestedCommand, self).undo()
        NestedCommand.isUndo = False


class SelectionModelEdit(NestedCommand):
    """
    Assumes the selection is already changed,
    so only after an undo() will redo() do anything.

    Very basic selection model edit,
    create & push on e.g. QItemSelectionModel.selectionChanged
    to make changes inherently undoable.
    """

    def __init__(self, model, selected, deselected, emit, parent=None):
        # we can not create new undo commands during undo or redo
        super(SelectionModelEdit, self).__init__('Selection model change', parent)
        self.__model = model
        self.__emit = emit
        self.__selected = [unpackModelIndex(idx) for idx in selected.indexes()]
        self.__deselected = [unpackModelIndex(idx) for idx in deselected.indexes()]
        self.__isApplied = True  # the selection has already happened

    def _redoInternal(self):
        model = self.__model.model()

        added = QItemSelection()
        for index in self.__selected:
            mdlIndex = constructModelIndex(model, index)
            added.select(mdlIndex, mdlIndex)

        removed = QItemSelection()
        for index in self.__deselected:
            mdlIndex = constructModelIndex(model, index)
            removed.select(mdlIndex, mdlIndex)

        if not self.__isApplied:
            self.__model.select(added, QItemSelectionModel.Select)
            self.__model.select(removed, QItemSelectionModel.Deselect)

        self.__emit(added, removed)

    def _undoInternal(self):
        self.__isApplied = False

        model = self.__model.model()

        added = QItemSelection()
        for index in self.__selected:
            mdlIndex = constructModelIndex(model, index)
            added.select(mdlIndex, mdlIndex)

        removed = QItemSelection()
        for index in self.__deselected:
            mdlIndex = constructModelIndex(model, index)
            removed.select(mdlIndex, mdlIndex)

        self.__model.select(removed, QItemSelectionModel.Select)
        self.__model.select(added, QItemSelectionModel.Deselect)

        self.__emit(removed, added)


class ModelEdit(QUndoCommand):
    """
    A command to handle undoable row creation and deletion.
    Row indices are current model indices, removed before the new rows are appended.
    """

    def __init__(self, model, pyObjsToAppend, rowIndicesToRemove, parent=None):
        super(ModelEdit, self).__init__('Create / delete model items', parent)
        self.model = model
        self.pyObjsToAppend = pyObjsToAppend
        self.rowIndicesToRemove = sorted(rowIndicesToRemove)
        self.removedRows = []
        self.modelSizeAfterRemoval = None

    def redo(self):
        # remove rows at inidices, starting at the highest index
        self.removedRows = []
        for row in reversed(self.rowIndicesToRemove):
            self.removedRows.append(self.model.takeRow(row))

        # append additional rows
        self.modelSizeAfterRemoval = self.model.rowCount()
        for row in self.pyObjsToAppend:
            self.model.appendRow(row.items)

    def undo(self):
        # remove appended items, before reinserting
        while self.model.rowCount() > self.modelSizeAfterRemoval:
            self.model.takeRow(self.model.rowCount() - 1)

        # reinsert removed rows
        for row in self.rowIndicesToRemove:
            self.model.insertRow(row, self.removedRows.pop(0))


class ModelChange(QUndoCommand):
    """
    A command to use QModelIndex.setData with undo.
    Caches the current data for undo().
    """

    def __init__(self, index, value, role):
        super(ModelChange, self).__init__('Model change')
        self.__model = index.model()
        self.__index = unpackModelIndex(index)
        self.__restore = index.data(role)
        self.__apply = value
        self.__role = role

    def redo(self):
        self.__model.active = True
        index = constructModelIndex(self.__model, self.__index)
        self.__model.setData(index, self.__apply, self.__role)
        self.__model.active = False

    def undo(self):
        self.__model.active = True
        index = constructModelIndex(self.__model, self.__index)
        self.__model.setData(index, self.__restore, self.__role)
        self.__model.active = False


class EventEdit(QUndoCommand):
    """
    Assumes the events are already changed and we are passing in the undo state.
    Caches current state during construction as redo state.

    first redo() will do nothing
    undo() will apply given state
    redo() will apply state cached during construction
    """

    def __init__(self, restore, parent=None):
        super(EventEdit, self).__init__('Event edit', parent)
        self._apply = {event: (event.start, event.end, event.track) for event in restore.iterkeys()}
        self._restore = restore.copy()
        self.applied = True

    def redo(self):
        if self.applied:
            return
        self.applied = True
        for event, value in self._apply.iteritems():
            event.start, event.end, event.track = value

    def undo(self):
        self.applied = False
        for event, value in self._restore.iteritems():
            event.start, event.end, event.track = value


class KeyEdit(QUndoCommand):
    """
    Assumes the keys are already changed and we are passing in the undo state.
    Caches current state during construction as redo state.

    first redo() will do nothing
    undo() will apply given state
    redo() will apply state cached during construction
    """

    def __init__(self, restore, triggerRepaint, parent=None):
        # type: (Dict['HermiteKey', (float, float, float, float)], (), QUndoCommand) -> None
        super(KeyEdit, self).__init__('Key edit', parent)
        self.restore = restore
        self.triggerRepaint = triggerRepaint
        self.apply = {key: key.copyData() for key in restore}
        self.curves = {key.parent for key in restore}
        self.applied = True

    def redo(self):
        if self.applied:
            return
        self.applied = True
        for key, value in self.apply.iteritems():
            key.setData(*value)
        for curve in self.curves:
            curve.sort()
        self.triggerRepaint()

    def undo(self):
        self.applied = False
        for key, value in self.restore.iteritems():
            key.setData(*value)
        for curve in self.curves:
            curve.sort()
        self.triggerRepaint()


class TimeEdit(QUndoCommand):
    """ Undoable timer.Time changes """

    def __init__(self, originalTime, newTime, setTime, parent=None):
        super(TimeEdit, self).__init__('Time changed', parent)
        self.originalTime = originalTime
        self.newTime = newTime
        self.setTime = setTime
        self.applied = True

    def redo(self):
        if self.applied:
            return
        self.applied = True
        self.setTime(self.newTime)

    def undo(self):
        self.applied = False
        self.setTime(self.originalTime)


class DeleteKeys(QUndoCommand):
    """
    Given a list of keys removes them from the curve with undo support.
    """

    def __init__(self, keysToRemove, triggerRepaint, parent=None):
        super(DeleteKeys, self).__init__('Delete keys', parent)
        self.apply = keysToRemove
        self.triggerRepaint = triggerRepaint

    def redo(self):
        for curve, keys in self.apply.iteritems():
            curve.removeKeys(keys)
        self.triggerRepaint()

    def undo(self):
        for curve, keys in self.apply.iteritems():
            curve.insertKeys(keys)
        self.triggerRepaint()


class InsertKeys(QUndoCommand):
    """
    Given a list of keys adds them to the curve with undo support.
    If a key to insert overlaps with an existing key it is ignored.
    """

    def __init__(self, keysToInsert, triggerRepaint, parent=None):
        super(InsertKeys, self).__init__('Insert keys', parent)
        self.apply = keysToInsert
        self.triggerRepaint = triggerRepaint
        self.alteredKeys = {}

    def redo(self):
        from experiment.curvemodel import EInsertMode
        for curve, key in self.apply.iteritems():
            other = curve.insertKey(key, EInsertMode.Passive)
            if other is not None:
                self.alteredKeys[curve] = other
        self.triggerRepaint()

    def undo(self):
        for curve, key in self.apply.iteritems():
            if curve in self.alteredKeys:
                self.alteredKeys[curve][0].setData(*self.alteredKeys[curve][1])
            else:
                curve.removeKeys([key])
        self.triggerRepaint()


class KeySelectionEdit(NestedCommand):
    """
    Given a KeySelection instance and a dict of {HermiteKey: state} to apply
    this will will cache current state and support redo() and undo() to apply the proposed change.
    """
    # TODO: Is there a reason this is not using _redoInternal and _undoInternal? Should it be a NestedCommand at all?

    def __init__(self, selectionDict, keyStateDict, parent=None):
        super(KeySelectionEdit, self).__init__('Key selection change', parent)
        self.__selectionModel = selectionDict
        self.__apply = (keyStateDict.copy(), [])

        # move addOrModify actions to remove if we are modifying to '0'
        for key, value in self.__apply[0].iteritems():
            if value == 0:
                # all elements deselected, register for removal
                assert key in self.__selectionModel, "Attempting to deselect key that wasn't selected."
                self.__apply[1].append(key)

        for key in self.__apply[1]:
            del self.__apply[0][key]

        # cache restore state
        self.__restore = ({}, [])
        for addOrModify in self.__apply[0]:
            if addOrModify in self.__selectionModel:
                # is modification
                self.__restore[0][addOrModify] = self.__selectionModel[addOrModify]
            else:
                self.__restore[1].append(addOrModify)

        for remove in self.__apply[1]:
            self.__restore[0][remove] = self.__selectionModel[remove]

    def redo(self):
        oldState = self.__selectionModel.blockSignals(True)

        self.__selectionModel.update(self.__apply[0])
        for remove in self.__apply[1]:
            del self.__selectionModel[remove]

        self.__selectionModel.blockSignals(oldState)
        if not oldState:
            self.__selectionModel.changed.emit()

    def undo(self):
        oldState = self.__selectionModel.blockSignals(True)

        self.__selectionModel.update(self.__restore[0])
        for remove in self.__restore[1]:
            del self.__selectionModel[remove]

        self.__selectionModel.blockSignals(oldState)
        if not oldState:
            self.__selectionModel.changed.emit()
