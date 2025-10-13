# -*- coding: utf-8 -*-

import maya.cmds as cmds
import maya.OpenMayaUI as OpenMayaUI
import maya.api.OpenMaya as om2
from maya.app.general.mayaMixin import MayaQWidgetBaseMixin, MayaQWidgetDockableMixin

import os

try:
    from PySide6 import QtWidgets, QtGui, QtCore
except ImportError:
    from PySide2 import QtWidgets, QtGui, QtCore
    
import importlib

from . import utils
importlib.reload(utils)
from . import treeView
importlib.reload(treeView)
from . import view
importlib.reload(view)

class Editor(MayaQWidgetBaseMixin, utils.RunOnlyMixin, QtWidgets.QMainWindow):
    def __init__(self, parent=None):
        super(Editor, self).__init__(parent)
        
        self.setWindowTitle("Editor")
        self.resize(500, 500)
        # ----------------------------------------------------------------------------------
        # CENTRAL WIDGET
        # ----------------------------------------------------------------------------------
        self.centralWidget = QtWidgets.QWidget(self)
        self.verticalLayout_central = QtWidgets.QVBoxLayout(self.centralWidget)
        self.verticalLayout_central.setSpacing(5)
        self.verticalLayout_central.setContentsMargins(0, 0, 0, 0)

        """---LAYOUT------------------------------------------------------------------------"""
        self.setCentralWidget(self.centralWidget)
        
        # ----------------------------------------------------------------------------------
        # INIT METHOD
        # ----------------------------------------------------------------------------------    
        self._layout_temp()
        
    # ----------------------------------------------------------------------------------
    # SIGNAL/SLOT CONNECT
    # ----------------------------------------------------------------------------------    
    def _connect_slot(self):
        pass
    # ----------------------------------------------------------------------------------
    # LAYOUT
    # ----------------------------------------------------------------------------------
    def _layout_menu(self):
        pass
    
    def _layout_temp(self):
        line_edit = QtWidgets.QLineEdit()
        
        self.view = treeView.CustomTreeView()
        
        root = treeView.Item("Root")
        for i in range(3):
            parent = treeView.Item("Group_{}".format(i), root)
            for x in range(3):
                child = treeView.Item("{}_{}_Item".format(i+5, x), parent)
        #         for y in range(3):
        #             mago = treeView.Item("Hoge_{}_{}_{}".format(i, x, y), child)
                
        model = treeView.CustomItemModel(root)
        self.proxy_model = treeView.CustomSortFilterProxyModel()
        self.proxy_model.setSourceModel(model)
        
        self.view.setModel(self.proxy_model)
        self.view.expandAll()
        
        self.verticalLayout_central.addWidget(line_edit)
        self.verticalLayout_central.addWidget(self.view)
        
        line_edit.textChanged.connect(self.set_filter)
        
        # folder = r"D:\temp\seq01"  # シーケンス画像があるフォルダ
        # player = view.ImageSequenceWidget(folder, fps=24)
        # player.resize(500, 500)
        
        # self.verticalLayout_central.addWidget(player)
        
    # ----------------------------------------------------------------------------------
    # EVENT
    # ----------------------------------------------------------------------------------
    
    # ----------------------------------------------------------------------------------
    # METHOD
    # ----------------------------------------------------------------------------------
    def set_filter(self, text):
        self.proxy_model.setFilterRegExp(QtCore.QRegExp(text, QtCore.Qt.CaseInsensitive, QtCore.QRegExp.Wildcard))
        self.view.expandAll()
        
        # self._items()
            
    def _items(self, parent=QtCore.QModelIndex()):
        model = self.view.model()
        for row in range(model.rowCount(parent)):
            index = model.index(row, 0, parent)
            print(index.data(), index)
            self._items(index)

def main():
    app = QtWidgets.QApplication.instance()
    win = Editor()
    win.show()
    app.exec_()







def select_items_by_name(tree_view, model, target_names):
    """
    TreeView上で、指定された名前のアイテムを最速で選択状態にする。
    """
    sel_model = tree_view.selectionModel()
    if not sel_model:
        sel_model = QtCore.QItemSelectionModel(model)
        tree_view.setSelectionModel(sel_model)

    # 更新停止
    tree_view.setUpdatesEnabled(False)
    sel_model.blockSignals(True)

    try:
        # 一括選択用オブジェクト
        selection = QtCore.QItemSelection()

        # 非再帰で全アイテム走査
        stack = [QtCore.QModelIndex()]
        while stack:
            parent = stack.pop()
            for row in range(model.rowCount(parent)):
                idx = model.index(row, 0, parent)
                name = model.data(idx)
                if name in target_names:
                    selection.select(idx, idx)
                stack.append(idx)

        # 一括選択を適用（1回だけ）
        sel_model.clearSelection()
        sel_model.select(selection, QtCore.QItemSelectionModel.Select)
        sel_model.setCurrentIndex(selection.indexes()[0], QtCore.QItemSelectionModel.Current)

    finally:
        # 更新再開
        sel_model.blockSignals(False)
        tree_view.setUpdatesEnabled(True)
        tree_view.viewport().update()
    