from experiment.enum import Enum
from qtutil import *
from util import randomColor
from experiment.actions import ModelChange


class Label(object):
    """ Utiliy to display a non-editable string in the ItemRow system. """

    def __init__(self, text):
        self.text = str(text)

    def __str__(self):
        return self.text


class ItemRow(object):
    """ Represent a row of QStandardItems """

    def __init__(self, name, *args):
        items = [QStandardItem(name)]
        items[0].setData(self)
        self.__dict__['items'] = items
        self.__dict__['color'] = QColor(*randomColor())

        for value in args:
            self.items.append(QStandardItem(str(value)))
            # implicitly cast simple types when getting their values
            # allows direct UI editing as well
            if isinstance(value, (float, int, bool, basestring, Enum)):
                value = type(value)
            # else:
            #    items[-1].setEditable(False)
            items[-1].setData(value)

    @property
    def name(self):
        return self.items[0].text()

    def __getitem__(self, index):
        item = self.items[index]
        if index == 0:
            return item.text()

        data = item.data()

        if isinstance(data, type):
            return data(item.text())

        return data

    def __setitem__(self, index, value):
        item = self.items[index]
        if index == 0:
            item.setText(value)
            return

        item.setText(str(value))

        data = item.data()
        if isinstance(data, type):
            return

        item.setData(value)

    def __str__(self):
        return str(self.items[0].text())

    @classmethod
    def properties(cls):
        raise NotImplementedError()

    def __getattr__(self, attr):
        try:
            i = self.__class__.properties().index(attr)
        except ValueError:
            raise AttributeError(attr)
        return self[i]

    def __setattr__(self, attr, value):
        try:
            i = self.__class__.properties().index(attr)
        except ValueError:
            raise AttributeError(attr)
        self[i] = value


class UndoableModel(QStandardItemModel):
    def __init__(self, undoStack):
        super(UndoableModel, self).__init__()
        self.undoStack = undoStack
        self.active = False  # set to True if an undo action is currently running

    def setData(self, index, value, role=Qt.EditRole):
        # change is not a change, ignore
        if self.data(index, role) == value:
            return False

        if self.active:
            return super(UndoableModel, self).setData(index, value, role)
        else:
            # change is not happening from the undostack, push it there
            self.undoStack.push(ModelChange(index, value, role))
            return True
