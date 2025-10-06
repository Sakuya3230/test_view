try:
    from PySide6 import QtWidgets, QtGui, QtCore
except ImportError:
    from PySide2 import QtWidgets, QtGui, QtCore
    
import maya.cmds as cmds

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
        
    def selectionChanged(self, selected, deselected):
        # 選択が変更されたときに Qt が内部でアクセス違反に行くのを防ぐため、
        # Python レイヤで保護してログを残す。
        try:
            # デバッグ用：問題のある index をチェックしてログ出力
            for sel_range in selected:
                for idx in sel_range.indexes():
                    # proxy モデルを使っているなら mapToSource を試す
                    try:
                        if self.model() is not None:
                            # Safely attempt to map to source (if proxy)
                            src = self.model().mapToSource(idx) if hasattr(self.model(), 'mapToSource') else None
                    except Exception:
                        pass
            super().selectionChanged(selected, deselected)
        except Exception as e:
            # ここで例外を握ることで Qt の C++ 側へ伝播してクラッシュするのを避ける
            import traceback, sys
            tb = traceback.format_exc()
            print("selectionChanged: caught exception:", e)
            print(tb)
            # さらに詳細ログを残したければここに追加
            # NOTE: return して Qt の元の処理をスキップ（ただし UI の状態に若干の不整合が残る可能性あり）
            return
        
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
 
class CustomProxyModel(QtCore.QSortFilterProxyModel):
    def __init__(self, parent=None):
        super().__init__(parent)
        self._proxy_root = ProxyItem()
        self._source_index_map = {}
        
    def setSourceModel(self, model):
        # old_model = self.sourceModel()
        # if old_model:
        #     try:
        #         old_model.dataChanged.disconnect(self._on_source_changed)
        #         old_model.rowsInserted.disconnect(self._on_source_changed)
        #         old_model.rowsRemoved.disconnect(self._on_source_changed)
        #         old_model.modelReset.disconnect(self._on_source_changed)
        #     except:
        #         pass
        
        super().setSourceModel(model)
        
        # try:
        #     model.dataChanged.connect(self._on_source_changed)
        #     model.rowsInserted.connect(self._on_source_changed)
        #     model.rowsRemoved.connect(self._on_source_changed)
        #     model.modelReset.connect(self._on_source_changed)
        # except:
        #     pass
        
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
    


try:
    from PySide6 import QtWidgets, QtCore, QtGui
    PYSIDE_VERSION = 6
except ImportError:
    from PySide2 import QtWidgets, QtCore, QtGui
    PYSIDE_VERSION = 2

# -----------------------------
# 正規表現ラッパー関数
# -----------------------------
def regex_match(rx, text):
    """マッチするかどうか判定"""
    text = str(text)
    if PYSIDE_VERSION == 6:
        match = rx.match(text)
        return match.hasMatch()
    else:
        return rx.indexIn(text) != -1

def regex_capture(rx, text, group=0):
    """マッチした場合にキャプチャを取得"""
    text = str(text)
    if PYSIDE_VERSION == 6:
        match = rx.match(text)
        if match.hasMatch():
            return match.captured(group)
        return None
    else:
        if rx.indexIn(text) != -1:
            return rx.cap(group)
        return None


# -----------------------------
# ProxyItem は以前と同じ
# -----------------------------
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
        return len(self.children())

    def addChild(self, child):
        self.children().append(child)

    def removeChild(self, child):
        if child in self._children:
            self._children.remove(child)

    def row(self):
        parent = self.parent()
        if parent:
            try:
                return parent.children().index(self)
            except:
                return 0
        return 0


# -----------------------------
# 拡張 CustomSortFilterProxyModel
# -----------------------------
class CustomSortFilterProxyModel(QtCore.QAbstractProxyModel):
    def __init__(self, parent=None):
        super().__init__(parent)
        self._root_item = ProxyItem()
        self._source_connections = []

        # フィルタ設定
        self._filter_text = ""
        self._filter_regexp = None
        self._filter_columns = []
        self._filter_role = QtCore.Qt.DisplayRole
        self._case_sensitive = False
        self._exact_match = False

        # 親を残すかどうか
        self._keep_parent_if_child_matches = False

        # キャプチャを使ったカスタム判定
        self._capture_filter_callback = None  # 関数: f(captured_text) -> bool

    # --------------------------
    # 親保持フラグ操作
    # --------------------------
    def setKeepParentIfChildMatches(self, flag: bool):
        self._keep_parent_if_child_matches = flag
        self.rebuildTree()

    # --------------------------
    # キャプチャフィルタを設定
    # --------------------------
    def setCaptureFilter(self, callback):
        """callback(captured_text) -> True/False"""
        self._capture_filter_callback = callback
        self.rebuildTree()

    # --------------------------
    # フィルタ設定
    # --------------------------
    def setFilterText(self, text, caseSensitive=False, exactMatch=False):
        self._filter_text = text or ""
        self._filter_regexp = None
        self._case_sensitive = caseSensitive
        self._exact_match = exactMatch
        self.rebuildTree()

    def setFilterRegExp(self, regexp):
        self._filter_regexp = regexp
        self.rebuildTree()

    def setFilterColumns(self, columns):
        self._filter_columns = columns or []
        self.rebuildTree()

    def setFilterRole(self, role):
        self._filter_role = role
        self.rebuildTree()

    # --------------------------
    # 基本モデル
    # --------------------------
    def columnCount(self, parent):
        if not self.sourceModel():
            return 0
        return self.sourceModel().columnCount(self.mapToSource(parent))

    def rowCount(self, parent):
        item = self.getItem(parent)
        return item.childCount()

    def index(self, row, column, parent):
        if not self.hasIndex(row, column, parent):
            return QtCore.QModelIndex()
        parent_item = self.getItem(parent)
        child_item = parent_item.child(row)
        if child_item:
            return self.createIndex(row, column, child_item)
        return QtCore.QModelIndex()

    def parent(self, index):
        if not index.isValid():
            return QtCore.QModelIndex()
        item = index.internalPointer()
        parent_item = item.parent()
        if parent_item is None or parent_item == self._root_item:
            return QtCore.QModelIndex()
        return self.createIndex(parent_item.row(), 0, parent_item)

    # --------------------------
    # ソースモデルとの対応
    # --------------------------
    def mapToSource(self, proxyIndex):
        if not proxyIndex.isValid():
            return QtCore.QModelIndex()
        item = proxyIndex.internalPointer()
        return item.sourceIndex()

    def mapFromSource(self, sourceIndex):
        if not sourceIndex.isValid():
            return QtCore.QModelIndex()
        def findItemBySource(item):
            if item.sourceIndex() == sourceIndex:
                return item
            for c in item.children():
                res = findItemBySource(c)
                if res:
                    return res
            return None
        proxy_item = findItemBySource(self._root_item)
        if proxy_item:
            return self.createIndex(proxy_item.row(), sourceIndex.column(), proxy_item)
        return QtCore.QModelIndex()

    # --------------------------
    # ヘルパー
    # --------------------------
    def getItem(self, index):
        if index.isValid():
            item = index.internalPointer()
            if item:
                return item
        return self._root_item

    # --------------------------
    # ソースモデル監視
    # --------------------------
    def setSourceModel(self, sourceModel):
        for conn in self._source_connections:
            try:
                conn.disconnect()
            except Exception:
                pass
        self._source_connections = []

        super().setSourceModel(sourceModel)
        if sourceModel is None:
            self._root_item = ProxyItem()
            return

        # シグナル接続
        sourceModel.rowsInserted.connect(self._onRowsInserted)
        sourceModel.rowsRemoved.connect(self._onRowsRemoved)
        sourceModel.dataChanged.connect(self._onDataChanged)
        sourceModel.modelReset.connect(self.rebuildTree)
        sourceModel.layoutChanged.connect(self.rebuildTree)

        self._source_connections = [
            sourceModel.rowsInserted,
            sourceModel.rowsRemoved,
            sourceModel.dataChanged,
            sourceModel.modelReset,
            sourceModel.layoutChanged,
        ]

        self.rebuildTree()

    # --------------------------
    # フィルタ判定
    # --------------------------
    def filterAcceptsRow(self, sourceIndex):
        if not sourceIndex.isValid():
            return False
        model = self.sourceModel()
        if not model:
            return False

        column_indices = (
            self._filter_columns
            if self._filter_columns
            else range(model.columnCount(sourceIndex))
        )

        # 正規表現優先
        if self._filter_regexp:
            for col in column_indices:
                idx = model.index(sourceIndex.row(), col, sourceIndex.parent())
                data = model.data(idx, self._filter_role)
                if data and regex_match(self._filter_regexp, data):
                    # キャプチャフィルタがあれば判定
                    if self._capture_filter_callback:
                        captured = regex_capture(self._filter_regexp, data, 1)
                        if not self._capture_filter_callback(captured):
                            continue
                    return True
            return False

        # 通常文字列検索
        if not self._filter_text:
            return True

        text = self._filter_text
        if not self._case_sensitive:
            text = text.lower()

        for col in column_indices:
            idx = model.index(sourceIndex.row(), col, sourceIndex.parent())
            data = model.data(idx, self._filter_role)
            if not data:
                continue
            value = str(data)
            if not self._case_sensitive:
                value = value.lower()
            if self._exact_match:
                if value == text:
                    return True
            else:
                if text in value:
                    return True
        return False

    def _isRowAcceptedRecursively(self, sourceIndex):
        if self.filterAcceptsRow(sourceIndex):
            return True
        model = self.sourceModel()
        for row in range(model.rowCount(sourceIndex)):
            child = model.index(row, 0, sourceIndex)
            if self._isRowAcceptedRecursively(child):
                return True
        return False

    # --------------------------
    # ツリー再構築
    # --------------------------
    def rebuildTree(self):
        self.beginResetModel()
        self._root_item = ProxyItem()
        source_model = self.sourceModel()
        if not source_model:
            self.endResetModel()
            return

        def build(parent_proxy_item, source_parent_index):
            for row in range(source_model.rowCount(source_parent_index)):
                src_idx = source_model.index(row, 0, source_parent_index)
                if self.filterAcceptsRow(src_idx):
                    proxy_item = ProxyItem(src_idx, parent_proxy_item)
                    build(proxy_item, src_idx)
                else:
                    if self._keep_parent_if_child_matches:
                        for child_row in range(source_model.rowCount(src_idx)):
                            child_idx = source_model.index(child_row, 0, src_idx)
                            if self._isRowAcceptedRecursively(child_idx):
                                proxy_item = ProxyItem(src_idx, parent_proxy_item)
                                build(proxy_item, src_idx)
                                break
                    else:
                        for child_row in range(source_model.rowCount(src_idx)):
                            child_idx = source_model.index(child_row, 0, src_idx)
                            if self._isRowAcceptedRecursively(child_idx):
                                proxy_item = ProxyItem(child_idx, parent_proxy_item)
                                build(proxy_item, child_idx)

        build(self._root_item, QtCore.QModelIndex())
        self.endResetModel()

    # --------------------------
    # 部分更新対応
    # --------------------------
    def _onRowsInserted(self, parent, start, end):
        parent_proxy_index = self.mapFromSource(parent)
        parent_item = self.getItem(parent_proxy_index)
        model = self.sourceModel()
        for row in range(start, end + 1):
            src_idx = model.index(row, 0, parent)
            if self._isRowAcceptedRecursively(src_idx):
                self.beginInsertRows(parent_proxy_index, row, row)
                ProxyItem(src_idx, parent_item)
                self.endInsertRows()

    def _onRowsRemoved(self, parent, start, end):
        parent_proxy_index = self.mapFromSource(parent)
        parent_item = self.getItem(parent_proxy_index)
        for row in reversed(range(start, end + 1)):
            if row < len(parent_item._children):
                self.beginRemoveRows(parent_proxy_index, row, row)
                del parent_item._children[row]
                self.endRemoveRows()

    def _onDataChanged(self, topLeft, bottomRight, roles=[]):
        for row in range(topLeft.row(), bottomRight.row() + 1):
            for col in range(topLeft.column(), bottomRight.column() + 1):
                src_idx = self.sourceModel().index(row, col, topLeft.parent())
                proxy_idx = self.mapFromSource(src_idx)
                if proxy_idx.isValid():
                    self.dataChanged.emit(proxy_idx, proxy_idx, roles)

# # 正規表現 + キャプチャ
# if PYSIDE_VERSION == 6:
#     rx = QtCore.QRegularExpression(r"bone_(\w+)(?=_L$)")  # _L で終わるbone_XXX
# else:
#     rx = QtCore.QRegExp(r"bone_(\w+)_L$")

# proxy.setFilterRegExp(rx)

# # キャプチャで条件をさらに絞る
# proxy.setCaptureFilter(lambda captured: captured and captured.startswith("spine"))

# # 親を残す／子だけ繰り上げ
# proxy.setKeepParentIfChildMatches(False)