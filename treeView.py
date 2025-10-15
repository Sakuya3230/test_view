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


class HybridSortFilterProxyModel(QtCore.QSortFilterProxyModel):
    """階層モード／フラットモードを切り替えられる SortFilterProxyModel"""

    def __init__(self, parent=None):
        super().__init__(parent)
        self._flatSorting = False
        self._flatIndexes = []
        self._sortColumn = 0
        self._sortOrder = QtCore.Qt.AscendingOrder

    # ---------------------------------
    # モード切り替え
    # ---------------------------------
    def setFlatSortingEnabled(self, enabled: bool):
        """Trueなら階層無視ソート"""
        if self._flatSorting == enabled:
            return
        self._flatSorting = enabled
        self.invalidate()

    def isFlatSortingEnabled(self) -> bool:
        return self._flatSorting

    # ---------------------------------
    # 再構築
    # ---------------------------------
    def invalidate(self):
        if not self._flatSorting:
            super().invalidate()
            return

        # フラット構築
        self.beginResetModel()
        self._flatIndexes = self._collect_all_indexes()
        self._sort_flat_indexes()
        self.endResetModel()

    def _collect_all_indexes(self):
        """階層を無視して全ノード収集"""
        model = self.sourceModel()
        if not model:
            return []
        result = []

        def recurse(parent_index):
            rows = model.rowCount(parent_index)
            for row in range(rows):
                index = model.index(row, self._sortColumn, parent_index)
                result.append(index)
                recurse(index)

        recurse(QtCore.QModelIndex())
        return result

    def _sort_flat_indexes(self):
        """指定カラムでソート"""
        if not self._flatIndexes:
            return
        model = self.sourceModel()

        def key_func(index):
            return str(model.data(index, QtCore.Qt.DisplayRole))

        reverse = self._sortOrder == QtCore.Qt.DescendingOrder
        self._flatIndexes.sort(key=key_func, reverse=reverse)

    # ---------------------------------
    # ソート
    # ---------------------------------
    def sort(self, column, order=QtCore.Qt.AscendingOrder):
        self._sortColumn = column
        self._sortOrder = order
        self.invalidate()
        if not self._flatSorting:
            super().sort(column, order)

    # ---------------------------------
    # フラットモード用（モデル構造）
    # ---------------------------------
    def rowCount(self, parent=QtCore.QModelIndex()):
        if not self._flatSorting:
            return super().rowCount(parent)
        if parent.isValid():
            return 0
        return len(self._flatIndexes)

    def columnCount(self, parent=QtCore.QModelIndex()):
        model = self.sourceModel()
        return model.columnCount(parent) if model else 0

    def index(self, row, column, parent=QtCore.QModelIndex()):
        if not self._flatSorting:
            return super().index(row, column, parent)
        if not self.hasIndex(row, column, parent):
            return QtCore.QModelIndex()
        return self.createIndex(row, column)

    def parent(self, index):
        if not self._flatSorting:
            return super().parent(index)
        return QtCore.QModelIndex()  # フラット時は親なし

    def mapToSource(self, proxyIndex):
        if not self._flatSorting:
            return super().mapToSource(proxyIndex)
        if not proxyIndex.isValid() or proxyIndex.row() >= len(self._flatIndexes):
            return QtCore.QModelIndex()
        sourceIndex = self._flatIndexes[proxyIndex.row()]
        return self.sourceModel().index(sourceIndex.row(), proxyIndex.column(), sourceIndex.parent())

    def mapFromSource(self, sourceIndex):
        if not self._flatSorting:
            return super().mapFromSource(sourceIndex)
        try:
            row = self._flatIndexes.index(sourceIndex.sibling(sourceIndex.row(), self._sortColumn))
            return self.index(row, sourceIndex.column())
        except ValueError:
            return QtCore.QModelIndex()

    def data(self, index, role=QtCore.Qt.DisplayRole):
        if not self._flatSorting:
            return super().data(index, role)
        if not index.isValid():
            return None
        sourceIndex = self.mapToSource(index)
        return self.sourceModel().data(sourceIndex, role)


# ---------------------------------
# デモ
# ---------------------------------
# if __name__ == "__main__":
#     app = QtWidgets.QApplication([])

#     # ソースモデル（階層あり）
#     model = QtGui.QStandardItemModel()
#     model.setHorizontalHeaderLabels(["Name", "Value"])

#     parentA = QtGui.QStandardItem("Parent A")
#     parentA.appendRow([QtGui.QStandardItem("Child A1"), QtGui.QStandardItem("300")])
#     parentA.appendRow([QtGui.QStandardItem("Child A2"), QtGui.QStandardItem("100")])

#     parentB = QtGui.QStandardItem("Parent B")
#     parentB.appendRow([QtGui.QStandardItem("Child B1"), QtGui.QStandardItem("200")])

#     model.appendRow([parentA, QtGui.QStandardItem("")])
#     model.appendRow([parentB, QtGui.QStandardItem("")])

#     # プロキシモデル
#     proxy = HybridSortFilterProxyModel()
#     proxy.setSourceModel(model)

#     # TreeView
#     view = QtWidgets.QTreeView()
#     view.setModel(proxy)
#     view.setSortingEnabled(True)
#     view.setAlternatingRowColors(True)
#     view.setRootIsDecorated(True)
#     view.setWindowTitle("Hybrid Sort (Flat / Hierarchy Toggle)")
#     view.resize(400, 250)

#     # トグルボタン
#     toggle_btn = QtWidgets.QPushButton("Toggle Flat / Hierarchy")
#     toggle_btn.setCheckable(True)
#     toggle_btn.toggled.connect(lambda checked: (
#         proxy.setFlatSortingEnabled(checked),
#         view.setRootIsDecorated(not checked)
#     ))

#     layout = QtWidgets.QVBoxLayout()
#     layout.addWidget(toggle_btn)
#     layout.addWidget(view)

#     w = QtWidgets.QWidget()
#     w.setLayout(layout)
#     w.show()

#     app.exec_()


class FlatSortProxyModel(QtCore.QAbstractProxyModel):
    """階層を無視してフラットにソートするプロキシモデル"""
    def __init__(self, parent=None):
        super().__init__(parent)
        self._sourceModel = None
        self._flatIndexes = []
        self._sortColumn = 0
        self._sortOrder = QtCore.Qt.AscendingOrder

    # ---------------------------------
    # 基本メソッド
    # ---------------------------------
    def setSourceModel(self, model):
        if self._sourceModel:
            self._sourceModel.dataChanged.disconnect(self.invalidate)
            self._sourceModel.modelReset.disconnect(self.invalidate)
            self._sourceModel.rowsInserted.disconnect(self.invalidate)
            self._sourceModel.rowsRemoved.disconnect(self.invalidate)

        self._sourceModel = model
        if model:
            model.dataChanged.connect(self.invalidate)
            model.modelReset.connect(self.invalidate)
            model.rowsInserted.connect(self.invalidate)
            model.rowsRemoved.connect(self.invalidate)

        self.invalidate()
        super().setSourceModel(model)

    def invalidate(self):
        self.beginResetModel()
        self._flatIndexes = self._collect_all_indexes()
        self._sort_flat_indexes()
        self.endResetModel()

    def _collect_all_indexes(self):
        """ソースモデル全体をフラット化"""
        if not self._sourceModel:
            return []
        result = []

        def recurse(parent_index):
            rows = self._sourceModel.rowCount(parent_index)
            for row in range(rows):
                index = self._sourceModel.index(row, self._sortColumn, parent_index)
                result.append(index)
                recurse(index)

        recurse(QtCore.QModelIndex())
        return result

    def _sort_flat_indexes(self):
        """指定カラムでソート"""
        if not self._flatIndexes:
            return

        def key_func(index):
            return str(self._sourceModel.data(index, QtCore.Qt.DisplayRole))

        self._flatIndexes.sort(key=key_func, reverse=(self._sortOrder == QtCore.Qt.DescendingOrder))

    # ---------------------------------
    # QAbstractProxyModel 必須実装
    # ---------------------------------
    def rowCount(self, parent=QtCore.QModelIndex()):
        if parent.isValid():
            return 0
        return len(self._flatIndexes)

    def columnCount(self, parent=QtCore.QModelIndex()):
        return self._sourceModel.columnCount() if self._sourceModel else 0

    def index(self, row, column, parent=QtCore.QModelIndex()):
        if not self.hasIndex(row, column, parent):
            return QtCore.QModelIndex()
        return self.createIndex(row, column)

    def parent(self, index):
        return QtCore.QModelIndex()  # 常にフラット

    def mapToSource(self, proxyIndex):
        if not proxyIndex.isValid():
            return QtCore.QModelIndex()
        row = proxyIndex.row()
        if row < 0 or row >= len(self._flatIndexes):
            return QtCore.QModelIndex()
        sourceIndex = self._flatIndexes[row]
        return self._sourceModel.index(sourceIndex.row(), proxyIndex.column(), sourceIndex.parent())

    def mapFromSource(self, sourceIndex):
        if not sourceIndex.isValid():
            return QtCore.QModelIndex()
        try:
            row = self._flatIndexes.index(sourceIndex.sibling(sourceIndex.row(), self._sortColumn))
            return self.index(row, sourceIndex.column())
        except ValueError:
            return QtCore.QModelIndex()

    def data(self, index, role=QtCore.Qt.DisplayRole):
        if not index.isValid():
            return None
        sourceIndex = self.mapToSource(index)
        return self._sourceModel.data(sourceIndex, role)

    # ---------------------------------
    # ソート呼び出し
    # ---------------------------------
    def sort(self, column, order=QtCore.Qt.AscendingOrder):
        self._sortColumn = column
        self._sortOrder = order
        self.invalidate()


# # ---------------------------------
# # デモ用
# # ---------------------------------
# if __name__ == "__main__":
#     app = QtWidgets.QApplication([])

#     model = QtGui.QStandardItemModel()
#     model.setHorizontalHeaderLabels(["Name", "Value"])

#     # 階層構造データ
#     parentA = QtGui.QStandardItem("Parent A")
#     parentA.appendRow([QtGui.QStandardItem("Child A1"), QtGui.QStandardItem("100")])
#     parentA.appendRow([QtGui.QStandardItem("Child A2"), QtGui.QStandardItem("300")])

#     parentB = QtGui.QStandardItem("Parent B")
#     parentB.appendRow([QtGui.QStandardItem("Child B1"), QtGui.QStandardItem("200")])

#     model.appendRow([parentA, QtGui.QStandardItem("")])
#     model.appendRow([parentB, QtGui.QStandardItem("")])

#     # プロキシモデル
#     proxy = FlatSortProxyModel()
#     proxy.setSourceModel(model)
#     proxy.sort(0, QtCore.Qt.AscendingOrder)

#     # TreeView（フラット表示）
#     view = QtWidgets.QTreeView()
#     view.setModel(proxy)
#     view.setRootIsDecorated(False)
#     view.setAlternatingRowColors(True)
#     view.setSortingEnabled(True)
#     view.setWindowTitle("Flat Sort Proxy Model (Hierarchy Ignored)")
#     view.resize(400, 250)
#     view.show()

#     app.exec_()


def iter_model(model, parent=QtCore.QModelIndex(), filter_func=None):
    """
    QAbstractItemModelを深さ優先で探索するジェネレータ。
    
    Parameters
    ----------
    model : QAbstractItemModel
        対象モデル
    parent : QModelIndex
        開始位置（通常は空の QModelIndex）
    filter_func : callable or None
        indexを受け取り、Trueを返す場合のみyieldされる関数
        例: lambda model, index: "Target" in model.data(index)
    
    Yields
    ------
    QModelIndex
        条件に一致したインデックス
    """
    stack = [parent]
    while stack:
        parent = stack.pop()
        # 子ノードをスタックに追加（逆順にして正しい順序に）
        for row in reversed(range(model.rowCount(parent))):
            child = model.index(row, 0, parent)
            stack.append(child)
        if parent.isValid():
            if filter_func is None or filter_func(model, parent):
                yield parent
                
for index in iter_model(self.model()):
    print(self.model().data(index))
    
for index in iter_model(self.model(),
                        filter_func=lambda m, i: "bone" in m.data(i).lower()):
    print("Found:", self.model().data(index))


def iter_descendants(model, parent_index, filter_func=None):
    """
    指定した親インデックス以下の全ての子孫を深さ優先で探索するジェネレータ。

    Parameters
    ----------
    model : QAbstractItemModel
        探索対象のモデル
    parent_index : QModelIndex
        探索を開始する親インデックス
    filter_func : callable or None
        indexを受け取り、Trueを返す場合のみyieldされる関数
        例: lambda model, index: "bone" in model.data(index).lower()

    Yields
    ------
    QModelIndex
        条件に一致した子孫インデックス
    """
    stack = [parent_index]
    while stack:
        parent = stack.pop()
        row_count = model.rowCount(parent)
        for row in reversed(range(row_count)):
            child = model.index(row, 0, parent)
            stack.append(child)
            if filter_func is None or filter_func(model, child):
                yield child
                
for index in tree.selectedIndexes():
    print(f"=== {model.data(index)} の子孫 ===")
    for child in iter_descendants(model, index):
        print(" └", model.data(child))  
        
        
def iter_ancestors(model, index, include_self=False, filter_func=None):
    """
    指定したインデックスから親方向へ祖先ノードをたどるジェネレータ。
    ルートノードまで遡る。

    Parameters
    ----------
    model : QAbstractItemModel
        探索対象のモデル
    index : QModelIndex
        探索を開始するインデックス
    include_self : bool
        Trueの場合、最初に自身もyieldする
    filter_func : callable or None
        indexを受け取り、Trueを返す場合のみyieldされる関数

    Yields
    ------
    QModelIndex
        条件に一致した祖先インデックス
    """
    current = index if include_self else index.parent()

    while current.isValid():
        if filter_func is None or filter_func(model, current):
            yield current
        current = current.parent()
        
for index in tree.selectedIndexes():
    print(f"=== {model.data(index)} の祖先 ===")
    for parent in iter_ancestors(model, index):
        print(" ↑", model.data(parent))
        



# -*- coding: utf-8 -*-
from PySide2 import QtCore

class TreeModelIterator:
    DEPTH_FIRST = 0
    BREADTH_FIRST = 1

    def __init__(self, model, parent=QtCore.QModelIndex(), mode=DEPTH_FIRST, forward=True):
        """
        model : QAbstractItemModel
        parent : 起点となる QModelIndex
        mode : DEPTH_FIRST または BREADTH_FIRST
        forward : True=順方向, False=逆方向
        """
        self._model = model
        self._parent = parent
        self._mode = mode
        self._forward = forward

    def __iter__(self):
        """
        幅優先・深さ優先探索を切り替えて反復
        """
        if self._mode == self.DEPTH_FIRST:
            yield from self._iter_depth_first(self._parent)
        else:
            yield from self._iter_breadth_first(self._parent)

    # -----------------------------
    # 深さ優先探索（stackベース）
    # -----------------------------
    def _iter_depth_first(self, parent):
        stack = []
        rows = range(self._model.rowCount(parent))
        if not self._forward:
            rows = reversed(list(rows))

        for row in rows:
            stack.append(self._model.index(row, 0, parent))

        while stack:
            index = stack.pop()
            yield index

            # 子を追加
            rows = range(self._model.rowCount(index))
            if not self._forward:
                rows = reversed(list(rows))

            for row in rows:
                stack.append(self._model.index(row, 0, index))

    # -----------------------------
    # 幅優先探索（queueベース）
    # -----------------------------
    def _iter_breadth_first(self, parent):
        queue = []
        rows = range(self._model.rowCount(parent))
        if not self._forward:
            rows = reversed(list(rows))

        for row in rows:
            queue.append(self._model.index(row, 0, parent))

        while queue:
            index = queue.pop(0)
            yield index

            rows = range(self._model.rowCount(index))
            if not self._forward:
                rows = reversed(list(rows))

            for row in rows:
                queue.append(self._model.index(row, 0, index))


# model が QTreeView に設定されていると仮定
model = treeView.model()

# 深さ優先探索（順方向）
for index in TreeModelIterator(model, mode=TreeModelIterator.DEPTH_FIRST):
    print(model.data(index))

# 幅優先探索（逆方向）
for index in TreeModelIterator(model, mode=TreeModelIterator.BREADTH_FIRST, forward=False):
    print(model.data(index))







def iter_model(model, parent=QtCore.QModelIndex()):
    stack = [parent]
    while stack:
        parent = stack.pop()
        for row in reversed(range(model.rowCount(parent))):
            child = model.index(row, 0, parent)
            stack.append(child)
        if parent.isValid():
            yield parent


from collections import deque
from PySide2 import QtCore  # モデルが必要な場合

def iter_model_bfs(model, parent=QtCore.QModelIndex()):
    """
    幅優先探索 BFS
    """
    queue = deque([parent])  # dequeで先頭から取り出す
    while queue:
        parent = queue.popleft()  # 先頭を取り出す
        for row in range(model.rowCount(parent)):  # 子を順番通りに追加
            child = model.index(row, 0, parent)
            queue.append(child)
        if parent.isValid():
            yield parent
            



import sys
from collections import deque

PY2 = sys.version_info[0] == 2

class TreeIterator(object):
    """
    Python2/3 両対応のMaya風ツリーイテレータ
    DFS/BFS切替、深さ制限、prune対応
    """
    def __init__(self, roots, tree, mode="DFS", max_depth=None):
        """
        roots : list of root nodes
        tree : dict(parent -> list of children)
        mode : "DFS" or "BFS"
        max_depth : 深さ制限（Noneで無制限）
        """
        self.tree = tree
        self.roots = list(roots)
        self.mode = mode.upper()
        self.max_depth = max_depth
        self.reset()

    # -----------------------------
    # イテレータプロトコル
    # -----------------------------
    if PY2:
        def next(self):
            return self._next()
    else:
        def __next__(self):
            return self._next()

    def _next(self):
        if not self.stack:
            self._done = True
            raise StopIteration

        node, depth = self.stack.pop() if self.mode=="DFS" else self.stack.popleft()
        self._current = node
        self._current_depth = depth

        if self.max_depth is None or depth < self.max_depth:
            children = self.tree.get(node, [])
            entries = [(c, depth+1) for c in children]
            if self.mode == "DFS":
                # DFSは逆順で積む
                self.stack.extend(reversed(entries))
            else:
                self.stack.extend(entries)

        return node

    def __iter__(self):
        return self

    # -----------------------------
    # Maya風メソッド
    # -----------------------------
    def reset(self):
        """
        最初に戻す
        """
        entries = [(r, 0) for r in self.roots]
        self.stack = list(reversed(entries)) if self.mode=="DFS" else deque(entries)
        self._current = None
        self._current_depth = 0
        self._done = False

    def isDone(self):
        return self._done

    def currentItem(self):
        return self._current

    def currentDepth(self):
        return self._current_depth

    def prune(self):
        """
        現在ノードの子ノードを探索対象から削除
        """
        if self._current is None:
            return
        children = self.tree.get(self._current, [])
        if self.mode=="DFS":
            self.stack = [(n,d) for n,d in self.stack if n not in children]
        else:
            self.stack = deque([(n,d) for n,d in self.stack if n not in children])




from PySide2 import QtCore, QtWidgets
from collections import deque

# ----------------------------
# TreeIterator（DFS/BFS切替、深さ制限）
# ----------------------------
class TreeIterator(object):
    def __init__(self, roots, model, mode="DFS", max_depth=None):
        self.model = model
        self.roots = list(roots)
        self.mode = mode.upper()
        self.max_depth = max_depth
        self.reset()

    def __iter__(self):
        return self

    def _next(self):
        if not self.stack:
            raise StopIteration
        index, depth = self.stack.pop() if self.mode=="DFS" else self.stack.popleft()
        self._current = index
        self._current_depth = depth

        if self.max_depth is None or depth < self.max_depth:
            rows = self.model.rowCount(index)
            children = [self.model.index(r, 0, index) for r in range(rows)]
            entries = [(c, depth+1) for c in children]
            if self.mode=="DFS":
                self.stack.extend(reversed(entries))
            else:
                self.stack.extend(entries)
        return index

    if QtCore.__version__[0] == "2":
        next = _next
    else:
        __next__ = _next

    def reset(self):
        entries = [(r, 0) for r in self.roots]
        self.stack = list(reversed(entries)) if self.mode=="DFS" else deque(entries)
        self._current = None
        self._current_depth = 0

    def currentItem(self):
        return self._current

    def currentDepth(self):
        return self._current_depth


# ----------------------------
# サンプルモデル
# ----------------------------
class SimpleTreeModel(QtCore.QAbstractItemModel):
    def __init__(self, data, parent=None):
        super(SimpleTreeModel, self).__init__(parent)
        self._data = data  # dict: parent -> [children]
        self._root = QtCore.QModelIndex()

    def rowCount(self, parent):
        if not parent.isValid():
            return len(self._data.get("Root", []))
        node = parent.internalPointer()
        return len(self._data.get(node, []))

    def columnCount(self, parent):
        return 1

    def index(self, row, column, parent):
        if not parent.isValid():
            node = self._data["Root"][row]
        else:
            node = self._data[parent.internalPointer()][row]
        idx = self.createIndex(row, column, node)
        return idx

    def parent(self, index):
        for parent, children in self._data.items():
            if index.internalPointer() in children:
                if parent == "Root":
                    return QtCore.QModelIndex()
                row = 0
                return self.createIndex(row, 0, parent)
        return QtCore.QModelIndex()

    def data(self, index, role=QtCore.Qt.DisplayRole):
        if role == QtCore.Qt.DisplayRole and index.isValid():
            return index.internalPointer()
        return None

# ----------------------------
# ビューでメソッドごとにイテレータを使用
# ----------------------------
def method_a(model, tree_view):
    print("Method A: 展開中のTargetを表示")
    it = TreeIterator([QtCore.QModelIndex()], model, mode="DFS")
    for idx in it:
        name = model.data(idx)
        if name.startswith("A") and tree_view.isExpanded(idx):
            print("A展開中:", name)

def method_b(model):
    print("Method B: 名前でフィルタ")
    it = TreeIterator([QtCore.QModelIndex()], model, mode="DFS")
    for idx in it:
        name = model.data(idx)
        if name.startswith("B"):
            print("Bフィルタ:", name)

# ----------------------------
# 実行例
# ----------------------------
if __name__ == "__main__":
    import sys

    app = QtWidgets.QApplication(sys.argv)

    # データ構造
    tree_data = {
        "Root": ["A", "B"],
        "A": ["A1", "A2"],
        "B": ["B1"],
        "A1": [], "A2": [], "B1": []
    }

    model = SimpleTreeModel(tree_data)
    view = QtWidgets.QTreeView()
    view.setModel(model)
    view.show()

    # メソッドごとにイテレータを作成
    method_a(model, view)
    method_b(model)

    sys.exit(app.exec_())



# -*- coding: utf-8 -*-
from PySide2 import QtWidgets, QtCore, QtGui

class HoverTreeView(QtWidgets.QTreeView):
    def __init__(self, parent=None):
        super(HoverTreeView, self).__init__(parent)
        self._hover_index = QtCore.QModelIndex()
        self.setMouseTracking(True)  # ホバー検知を有効化

    def mouseMoveEvent(self, event):
        """マウスホバーしているインデックスを追跡"""
        index = self.indexAt(event.pos())
        if index != self._hover_index:
            self._hover_index = index
            self.viewport().update()  # 再描画
        super(HoverTreeView, self).mouseMoveEvent(event)

    def leaveEvent(self, event):
        """マウスがビュー外に出たらリセット"""
        self._hover_index = QtCore.QModelIndex()
        self.viewport().update()
        super(HoverTreeView, self).leaveEvent(event)

    def drawBranches(self, painter, rect, index):
        """ブランチ（インデント部分）の描画をカスタマイズ"""
        if index == self._hover_index:
            color = QtGui.QColor(80, 100, 180, 50)  # 半透明のホバー色
            painter.save()
            painter.fillRect(rect, color)
            painter.restore()
        # 既定のブランチ描画も呼ぶ（枝線など）
        super(HoverTreeView, self).drawBranches(painter, rect, index)


# -------------------------------------------------------------
# 動作サンプル
# -------------------------------------------------------------
if __name__ == "__main__":
    import sys
    app = QtWidgets.QApplication(sys.argv)

    model = QtGui.QStandardItemModel()
    model.setHorizontalHeaderLabels(["Items"])
    parent = model.invisibleRootItem()
    for i in range(10):
        p = QtGui.QStandardItem(f"Parent {i}")
        for j in range(3):
            p.appendRow(QtGui.QStandardItem(f"Child {i}-{j}"))
        parent.appendRow(p)

    view = HoverTreeView()
    view.setModel(model)
    view.expandAll()
    view.resize(400, 400)
    view.show()

    sys.exit(app.exec_())

# -*- coding: utf-8 -*-
from PySide2 import QtWidgets, QtCore, QtGui

class HoverTreeView(QtWidgets.QTreeView):
    def __init__(self, parent=None):
        super(HoverTreeView, self).__init__(parent)
        self._hover_index = QtCore.QModelIndex()
        self.setMouseTracking(True)

    def _update_hover_index(self):
        """現在のマウス位置からホバーインデックスを更新"""
        pos = self.viewport().mapFromGlobal(QtGui.QCursor.pos())
        index = self.indexAt(pos)
        if index != self._hover_index:
            self._hover_index = index
            self.viewport().update()

    def mouseMoveEvent(self, event):
        self._update_hover_index()
        super(HoverTreeView, self).mouseMoveEvent(event)

    def leaveEvent(self, event):
        self._hover_index = QtCore.QModelIndex()
        self.viewport().update()
        super(HoverTreeView, self).leaveEvent(event)

    def scrollContentsBy(self, dx, dy):
        """スクロール操作でもホバー更新"""
        super(HoverTreeView, self).scrollContentsBy(dx, dy)
        self._update_hover_index()

    def drawBranches(self, painter, rect, index):
        if index == self._hover_index:
            color = QtGui.QColor(80, 100, 180, 50)
            painter.save()
            painter.fillRect(rect, color)
            painter.restore()
        super(HoverTreeView, self).drawBranches(painter, rect, index)
