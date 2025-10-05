try:
    from PySide6 import QtWidgets, QtGui, QtCore
except ImportError:
    from PySide2 import QtWidgets, QtGui, QtCore
    
import maya.cmds as cmds
    
class CustomTreeView(QtWidgets.QTreeView):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setSelectionMode(QtWidgets.QAbstractItemView.ExtendedSelection)
        self.setHeaderHidden(True)
        
        self.setAcceptDrops(True)
        self.setDragDropMode(QtWidgets.QAbstractItemView.DropOnly)
        self.setDefaultDropAction(QtCore.Qt.CopyAction)
        
    def dragEnterEvent(self, event):
        if event.mimeData().hasText():
            event.acceptProposedAction()
        else:
            event.ignore()
            
    def dragMoveEvent(self, event):
        event.acceptProposedAction()
        
    # def dropEvent(self, event):
    #     mime = event.mimeData()
    #     if not mime.hasText():
    #         event.ignore()
    #         return
        
    #     node_names = [i for i in mime.text().splitlines() if i]
    #     # print("Dropped nodes:", node_names)

    #     # モデルに追加処理
    #     model = self.model().sourceModel()
    #     model.insertItemRow(node_names)

    #     event.acceptProposedAction()
        
class CustomItemModel(QtCore.QAbstractItemModel):
    def __init__(self, root, parent=None):
        super().__init__(parent)
        self._root_item = root
        
    def columnCount(self, parent=QtCore.QModelIndex()):
        return 1
    
    def rowCount(self, parent=QtCore.QModelIndex()):
        if not parent.isValid():
            parent_item = self._root_item
        else:
            parent_item = parent.internalPointer()
        return parent_item.childCount()
    
    def data(self, index, role=QtCore.Qt.DisplayRole):
        if not index.isValid():
            return None
        
        item = index.internalPointer()
        if role == QtCore.Qt.DisplayRole:
            return item.name()
        
    def hasChildren(self, parent=QtCore.QModelIndex()):
        if not parent.isValid():
            parent_item = self._root_item
        else:
            parent_item = parent.internalPointer()
        return parent_item.hasChildren()
    
    def parent(self, index):
        if not index.isValid():
            return QtCore.QModelIndex()
        
        item = index.internalPointer()
        parent_item = item.parent()
        
        if parent_item == self._root_item:
            return QtCore.QModelIndex()
        
        return self.createIndex(parent_item.row(), 0, parent_item)
    
    def index(self, row, column, parent=QtCore.QModelIndex()):
        if not parent.isValid():
            parent_item = self._root_item
        else:
            parent_item = parent.internalPointer()
            
        child_item = parent_item.child(row)
        if child_item:
            return self.createIndex(row, column, child_item)
        return QtCore.QModelIndex()
    
    def flags(self, index):
        flags = QtCore.Qt.ItemIsEnabled | QtCore.Qt.ItemIsSelectable
        if index.isValid():
            return flags | QtCore.Qt.ItemIsDragEnabled | QtCore.Qt.ItemIsDropEnabled
        return flags | QtCore.Qt.ItemIsDropEnabled
    
    def supportedDropActions(self):
        return QtCore.Qt.CopyAction | QtCore.Qt.MoveAction
    
    def mimeTypes(self):
        return ["application/x-maya-node"]
    
    def dropMimeData(self, data, action, row, column, parent):
        if not data.hasText():
            return False
        
        text = data.text().strip()
        if not text:
            return False
        
        nodes = [p.strip() for p in text.splitlines() if p.strip()]
        parent_item = self._root_item if not parent.isValid() else parent.internalPointer()

        # ノード追加
        for node in nodes:
            self.insertPath(node, parent_item)

        return True

    def insertPath(self, parts, parent_item):
        """
        階層パスを分解して順にアイテムを追加。
        既存ノードは再利用。新規ノードは beginInsertRows / endInsertRows で通知。
        """
        current_parent = parent_item
        for part in parts:
            # 既存の子アイテムに同名があれば再利用
            existing = next((c for c in current_parent.children() if c.name() == part), None)
            if existing:
                current_parent = existing
            else:
                row = current_parent.childCount()
                self.beginInsertRows(self.createIndex(current_parent.row(), 0, current_parent), row, row)
                new_item = Item(part, current_parent)
                self.endInsertRows()
                current_parent = new_item
                
    
                
    
    def insertItemRow(self, nodes):
        row = self._root_item.childCount()
        count = len(nodes)
        print(row, count)
        self.beginInsertRows(QtCore.QModelIndex(), row, row + count - 1)
        for i in nodes:
            print(i)
            Item(i.split("|")[-1], self._root_item)
        self.endInsertRows()
            
          
class ProxyItem(object):
    def __init__(self, index=None, parent=None):
        self._source_index = index
        self._parent = parent
        self._children = []
        
        if self._parent is not None:
            self._parent.addChild(self)
         
    def sourceIndex(self):
        return self._source_index
         
    def parent(self):
        return self._parent
         
    def children(self):
        return self._children
    
    def child(self, row):
        return self.children()[row]
    
    def childCount(self):
        return len(self.children())
    
    def hasChildren(self):
        return len(self.children()) > 0
    
    def addChild(self, child):
        self.children().append(child)
        
    def row(self):
        if self.parent():
            return self.parent().children().index(self)
        return 0
     
class CustomProxyModel(QtCore.QSortFilterProxyModel):
    def __init__(self, parent=None):
        super().__init__(parent)
        self._proxy_root = ProxyItem()
        self._source_index_map = {}
        
    def setSourceModel(self, model):
        old_model = self.sourceModel()
        if old_model:
            try:
                old_model.dataChanged.disconnect(self._on_source_changed)
                old_model.rowsInserted.disconnect(self._on_source_changed)
                old_model.rowsRemoved.disconnect(self._on_source_changed)
                old_model.modelReset.disconnect(self._on_source_changed)
            except:
                pass
        
        super().setSourceModel(model)
        
        try:
            model.dataChanged.connect(self._on_source_changed)
            model.rowsInserted.connect(self._on_source_changed)
            model.rowsRemoved.connect(self._on_source_changed)
            model.modelReset.connect(self._on_source_changed)
        except:
            pass
        
        self.invalidateFilter()

    def columnCount(self, parent=QtCore.QModelIndex()):
        source = self.sourceModel()
        return source.columnCount(QtCore.QModelIndex()) if source else 0

    def rowCount(self, parent=QtCore.QModelIndex()):
        if not parent.isValid():
            parent_item = self._proxy_root
        else:
            parent_item = parent.internalPointer()

        return parent_item.childCount()
    
    def index(self, row, column, parent=QtCore.QModelIndex()):
        if not self.hasIndex(row, column, parent):
            return QtCore.QModelIndex()
        
        if not parent.isValid():
            parent_item = self._proxy_root
        else:
            parent_item = parent.internalPointer()
            
        child_item = parent_item.child(row)

        if child_item:
            return self.createIndex(row, column, child_item)
        
        return QtCore.QModelIndex()
    
    def parent(self, index):
        if not index.isValid():
            return QtCore.QModelIndex()
        
        item = index.internalPointer()
        parent_item = item.parent()
        
        if parent_item == self._proxy_root:
            return QtCore.QModelIndex()
        
        return self.createIndex(parent_item.row(), 0, parent_item)
        
    def hasChildren(self, parent=QtCore.QModelIndex()):
        if not parent.isValid():
            parent_item = self._proxy_root
        else:
            parent_item = parent.internalPointer()
        return parent_item.hasChildren()
        
    def data(self, index, role=QtCore.Qt.DisplayRole):
        if not index.isValid():
            return None
        
        item = index.internalPointer()
        return self.sourceModel().data(item.sourceIndex(), role)
        
    def mapToSource(self, proxyIndex):
        if not proxyIndex.isValid():
            return QtCore.QModelIndex()
        item = proxyIndex.internalPointer()
        return item.sourceIndex()
    
    def mapFromSource(self, sourceIndex):
        if not sourceIndex.isValid():
            return QtCore.QModelIndex()
        return self._source_index_map.get(sourceIndex, QtCore.QModelIndex())
    
    def setFilterRegExp(self, regExp):
        super().setFilterRegExp(regExp)
        self.invalidateFilter()
        
    def invalidateFilter(self):
        self.beginResetModel()
        self._proxy_root = ProxyItem()
        self._source_index_map.clear()
        source_model = self.sourceModel()
        if source_model:
            self.__rebuild_tree(self._proxy_root)
        self.endResetModel()
        
        self.__set_source_index_map()
        
    def filterAcceptsRow(self, source_row, source_parent):
        model = self.sourceModel()
        index = model.index(source_row, 0, source_parent)
        if not index.isValid():
            return False

        # 文字列のフィルタリング
        if self.filterRegExp().indexIn(model.data(index)) >= 0:
            return True
        
        # 子孫が受け入れられていたらフィルタリング
        for row in range(model.rowCount(index)):
            if self.filterAcceptsRow(row, index):
                return True
                
        return False

    def __set_source_index_map(self, parent=QtCore.QModelIndex()):
        # ソースインデックスをキャッシュ
        for row in range(self.rowCount(parent)):
            index = self.index(row, 0, parent)
            source_index = self.mapToSource(index)
            self._source_index_map[source_index] = index
            self.__set_source_index_map(index)
            
    def __rebuild_tree(self, parent_item=None, parent=QtCore.QModelIndex()):
        # フィルターにヒットしたアイテムのみで構築
        source_model = self.sourceModel()
        for row in range(source_model.rowCount(parent)):
            index = source_model.index(row, 0, parent)

            if self._filter_accepts_row(row, parent):
                item = ProxyItem(index, parent_item)
                self.__rebuild_tree(item, index)
            else:
                self.__rebuild_tree(parent_item, index)
      
    def _filter_accepts_row(self, source_row, source_parent):
        # 受け入れるアイテムを判定
        model = self.sourceModel()
        index = model.index(source_row, 0, source_parent)
        if not index.isValid():
            return False

        if self.filterRegExp().indexIn(model.data(index)) >= 0:
            return True
                        
        return False
    
    def _on_source_changed(self, *args, **kwargs):
        self.invalidateFilter()
    
class Item(object):
    def __init__(self, name, parent=None):
        self._name = name
        self._parent = parent
        self._children = []
        
        if parent is not None:
            parent.addChild(self)
            
    def name(self):
        return self._name
    
    def addChild(self, child):
        self._children.append(child)
        
    def childCount(self):
        return len(self._children)
    
    def hasChildren(self):
        return self.childCount() > 0
    
    def children(self):
        return self._children
    
    def child(self, row):
        return self.children()[row]
    
    def row(self):
        if self.parent() is not None:
            return self.parent().children().index(self)
    
    def setParent(self, parent):
        self._parent = parent
        
    def parent(self):
        return self._parent

