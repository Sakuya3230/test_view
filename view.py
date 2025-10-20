try:
    from PySide6 import QtWidgets, QtGui, QtCore
except ImportError:
    from PySide2 import QtWidgets, QtGui, QtCore
    
import maya.cmds as cmds
import os 


def save_view_sequence(output_dir, camera=None, width=1280, height=720, quality=90):
    """
    現在のビューをスライダー範囲で JPG シーケンスとして保存
    """
    # 出力フォルダを準備
    if not os.path.exists(output_dir):
        os.makedirs(output_dir)

    # タイムスライダーの範囲を取得
    start = int(cmds.playbackOptions(q=True, min=True))
    end   = int(cmds.playbackOptions(q=True, max=True))
    
    # カレントビューまたは指定カメラを使用
    if camera is None:
        panel = cmds.getPanel(withFocus=True)
        camera = cmds.modelEditor(panel, q=True, camera=True)
        print("Using current camera:", camera)

    # フレームごとにレンダリング
    for frame in range(start, end + 1):
        cmds.currentTime(frame, edit=True)
        cmds.refresh()  # ビュー更新

        # 保存ファイルパス
        filename = os.path.join(output_dir, f"frame_{frame:04d}.jpg")
        
        # playblastでビューキャプチャ
        cmds.playblast(
            frame=[frame],
            format='image',
            filename=filename,
            sequenceTime=False,
            clearCache=True,
            viewer=False,
            showOrnaments=False,
            fp=4,  # フル解像度
            percent=100,
            compression='jpg',
            widthHeight=(width, height),
            quality=quality
        )
        print("Saved:", filename)

    print("✅ 完了: ", output_dir)

# # 使用例:
# save_view_sequence(r"C:\temp\maya_view_seq", width=960, height=540)


class ImageSequenceWidget(QtWidgets.QLabel):
    """
    マウスオーバーで再生する JPG シーケンスプレイヤー
    """
    def __init__(self, folder, fps=24, parent=None):
        super().__init__(parent)
        self.setAlignment(QtCore.Qt.AlignCenter)
        self.setScaledContents(True)
        self.setMouseTracking(True)

        # シーケンス画像のロード
        self.frames = []
        for f in sorted(os.listdir(folder)):
            if f.lower().endswith(".jpg"):
                path = os.path.join(folder, f)
                pixmap = QtGui.QPixmap(path)
                if not pixmap.isNull():
                    self.frames.append(pixmap)

        self.index = 0
        self.fps = fps
        self.timer = QtCore.QTimer(self)
        self.timer.timeout.connect(self.nextFrame)

        # 最初のフレームを表示
        if self.frames:
            self.setPixmap(self.frames[0])

    # --- マウスイベント ---
    def enterEvent(self, event):
        """マウスが乗った時に再生開始"""
        if self.frames:
            self.timer.start(int(1000 / self.fps))
        super().enterEvent(event)

    def leaveEvent(self, event):
        """マウスが離れたら停止して最初に戻す"""
        self.timer.stop()
        self.index = 0
        if self.frames:
            self.setPixmap(self.frames[0])
        super().leaveEvent(event)

    # --- 再生処理 ---
    def nextFrame(self):
        if not self.frames:
            return
        self.index = (self.index + 1) % len(self.frames)
        self.setPixmap(self.frames[self.index])


# -*- coding: utf-8 -*-
from PySide2 import QtWidgets, QtCore, QtGui
import random

# ---------------------------
# FlowLayout（横折り返し）
# ---------------------------
class FlowLayout(QtWidgets.QLayout):
    def __init__(self, parent=None, margin=0, spacing=10):
        super(FlowLayout, self).__init__(parent)
        self._items = []
        self.setContentsMargins(margin, margin, margin, margin)
        self.setSpacing(spacing)

    def addItem(self, item):
        self._items.append(item)

    def count(self):
        return len(self._items)

    def itemAt(self, index):
        if 0 <= index < len(self._items):
            return self._items[index]
        return None

    def takeAt(self, index):
        if 0 <= index < len(self._items):
            return self._items.pop(index)
        return None

    def insertItem(self, index, item):
        """QLayoutItem を指定位置に挿入"""
        if index < 0:
            index = 0
        elif index > len(self._items):
            index = len(self._items)
        self._items.insert(index, item)

    # insertWidget 用のラッパー
    def insertWidget(self, index, widget):
        self.insertItem(index, QtWidgets.QWidgetItem(widget))
        self.update()  # レイアウトを再描画

    # --- 以下既存のメソッド ---
    def expandingDirections(self):
        return QtCore.Qt.Orientations(QtCore.Qt.Orientation(0))

    def hasHeightForWidth(self):
        return True

    def heightForWidth(self, width):
        return self._doLayout(QtCore.QRect(0, 0, width, 0), True)

    def setGeometry(self, rect):
        super(FlowLayout, self).setGeometry(rect)
        self._doLayout(rect, False)

    def sizeHint(self):
        return self.minimumSize()

    def minimumSize(self):
        size = QtCore.QSize()
        for item in self._items:
            size = size.expandedTo(item.minimumSize())
        margins = self.contentsMargins()
        size += QtCore.QSize(margins.left() + margins.right(),
                             margins.top() + margins.bottom())
        return size

    def _doLayout(self, rect, testOnly):
        x, y = rect.x(), rect.y()
        lineHeight = 0
        for item in self._items:
            nextX = x + item.sizeHint().width() + self.spacing()
            if nextX - self.spacing() > rect.right() and lineHeight > 0:
                x = rect.x()
                y += lineHeight + self.spacing()
                nextX = x + item.sizeHint().width() + self.spacing()
                lineHeight = 0
            if not testOnly:
                item.setGeometry(QtCore.QRect(QtCore.QPoint(x, y), item.sizeHint()))
            x = nextX
            lineHeight = max(lineHeight, item.sizeHint().height())
        return y + lineHeight - rect.y()

# ---------------------------
# 色アイテム
# ---------------------------
class ColorItem(QtWidgets.QWidget):
    clicked = QtCore.Signal(object)

    def __init__(self, color, index, name=None, parent=None):
        super(ColorItem, self).__init__(parent)
        self.color = color
        self.index = index
        self.alias = name or f"Item {index}"
        self._size = 300
        self.setFixedSize(self._size, self._size)
        self._hover = False
        self._selected = False
        self.setMouseTracking(True)

    def setItemSize(self, size):
        self._size = size
        self.setFixedSize(size, size)
        self.update()

    def paintEvent(self, event):
        painter = QtGui.QPainter(self)
        painter.setRenderHint(QtGui.QPainter.Antialiasing)

        # 文字用スペースを確保
        label_height = max(20, int(self._size * 0.15))
        margin = int(self._size * 0.05)
        rect_size = self._size - 2*margin - label_height

        # 上部に色矩形
        rect = QtCore.QRect(margin, margin, rect_size, rect_size)
        painter.setBrush(QtGui.QBrush(QtGui.QColor(*self.color)))
        painter.setPen(QtCore.Qt.NoPen)
        painter.drawRect(rect)

        # 下部に文字描画（中央揃え、長すぎる場合は省略）
        font_size = max(10, int(self._size * 0.08))
        font = QtGui.QFont("Arial", font_size)
        painter.setFont(font)
        painter.setPen(QtGui.QColor(255, 255, 255))

        text_rect = QtCore.QRect(rect.x(), rect.bottom(), rect.width(), label_height)

        # テキスト省略対応
        metrics = painter.fontMetrics()
        elided_text = metrics.elidedText(self.alias, QtCore.Qt.ElideRight, text_rect.width())
        painter.drawText(text_rect, QtCore.Qt.AlignCenter, elided_text)

        # ホバー・選択枠
        pen_width = max(2, int(self._size*0.013))
        if self._selected:
            pen = QtGui.QPen(QtGui.QColor(0, 255, 255), pen_width)
            painter.setPen(pen)
            painter.drawRect(self.rect().adjusted(2, 2, -2, -2))
        elif self._hover:
            pen = QtGui.QPen(QtGui.QColor(0, 255, 255, 120), pen_width)
            painter.setPen(pen)
            painter.drawRect(self.rect().adjusted(2, 2, -2, -2))

    def enterEvent(self, event):
        self._hover = True
        self.update()

    def leaveEvent(self, event):
        self._hover = False
        self.update()

    def mousePressEvent(self, event):
        self._selected = not self._selected
        self.clicked.emit(self)
        self.update()



# ---------------------------
# カラー追加ダイアログ
# ---------------------------
class AddColorDialog(QtWidgets.QDialog):
    def __init__(self, parent=None):
        super(AddColorDialog, self).__init__(parent)
        self.setWindowTitle("Add Color")
        self.setFixedSize(300, 220)
        layout = QtWidgets.QVBoxLayout(self)
        layout.setSpacing(10)
        layout.setContentsMargins(10, 10, 10, 10)

        # 名前入力
        self.name_edit = QtWidgets.QLineEdit()
        self.name_edit.setPlaceholderText("Item Name")
        layout.addWidget(QtWidgets.QLabel("Name:"))
        layout.addWidget(self.name_edit)

        # RGB入力
        self.r_spin = QtWidgets.QSpinBox(); self.r_spin.setRange(0, 255)
        self.g_spin = QtWidgets.QSpinBox(); self.g_spin.setRange(0, 255)
        self.b_spin = QtWidgets.QSpinBox(); self.b_spin.setRange(0, 255)

        rgb_layout = QtWidgets.QHBoxLayout()
        rgb_layout.addWidget(QtWidgets.QLabel("R:")); rgb_layout.addWidget(self.r_spin)
        rgb_layout.addWidget(QtWidgets.QLabel("G:")); rgb_layout.addWidget(self.g_spin)
        rgb_layout.addWidget(QtWidgets.QLabel("B:")); rgb_layout.addWidget(self.b_spin)
        layout.addWidget(QtWidgets.QLabel("RGB:"))
        layout.addLayout(rgb_layout)

        # カラーサンプル
        self.color_sample = QtWidgets.QLabel()
        self.color_sample.setFixedSize(50, 50)
        self.color_sample.setStyleSheet("background-color: rgb(0,0,0); border: 1px solid black;")
        layout.addWidget(QtWidgets.QLabel("Color Preview:"))
        layout.addWidget(self.color_sample)

        # 数値変化でリアルタイム更新
        self.r_spin.valueChanged.connect(self.updateColorSample)
        self.g_spin.valueChanged.connect(self.updateColorSample)
        self.b_spin.valueChanged.connect(self.updateColorSample)

        # クリックで QColorDialog
        self.color_sample.setCursor(QtCore.Qt.PointingHandCursor)
        self.color_sample.mousePressEvent = self.openColorDialog

        # OK / Cancel
        button_box = QtWidgets.QDialogButtonBox(QtWidgets.QDialogButtonBox.Ok | QtWidgets.QDialogButtonBox.Cancel)
        layout.addWidget(button_box)
        button_box.accepted.connect(self.accept)
        button_box.rejected.connect(self.reject)

    def updateColorSample(self):
        r, g, b = self.r_spin.value(), self.g_spin.value(), self.b_spin.value()
        self.color_sample.setStyleSheet(f"background-color: rgb({r},{g},{b}); border: 1px solid black;")

    def openColorDialog(self, event):
        current_color = QtGui.QColor(self.r_spin.value(), self.g_spin.value(), self.b_spin.value())
        color = QtWidgets.QColorDialog.getColor(current_color, self, "Select Color")
        if color.isValid():
            self.r_spin.setValue(color.red())
            self.g_spin.setValue(color.green())
            self.b_spin.setValue(color.blue())
            self.updateColorSample()

    def getValues(self):
        name = self.name_edit.text() or "New Item"
        color = (self.r_spin.value(), self.g_spin.value(), self.b_spin.value())
        return name, color

# ---------------------------
# GroupWidget 修正（右クリックメニュー追加）
# ---------------------------
class GroupWidget(QtWidgets.QWidget):
    colorSelected = QtCore.Signal(tuple)  # RGBタプル

    def __init__(self, name, colors, parent=None):
        super(GroupWidget, self).__init__(parent)
        self._collapsed = False
        layout = QtWidgets.QVBoxLayout(self)
        layout.setSpacing(5)
        layout.setContentsMargins(0, 0, 0, 0)

        # ヘッダ
        self.header = QtWidgets.QWidget()
        self.header.setFixedHeight(30)
        self.header.setCursor(QtCore.Qt.PointingHandCursor)
        header_layout = QtWidgets.QHBoxLayout(self.header)
        header_layout.setContentsMargins(10, 0, 10, 0)
        
        self.label = QtWidgets.QLabel(name)
        font = QtGui.QFont()
        font.setPointSize(18)
        font.setBold(True)
        self.label.setFont(font)
        
        line = QtWidgets.QFrame()
        line.setFrameShape(QtWidgets.QFrame.HLine)
        line.setStyleSheet("color: white; background-color: white;")
        header_layout.addWidget(self.label)
        header_layout.addWidget(line)
        layout.addWidget(self.header)

        # アイテムコンテナ
        self.container = QtWidgets.QWidget()
        self.flow = FlowLayout(self.container)
        for i, color in enumerate(colors):
            item = ColorItem(color, i)
            item.clicked.connect(self._onItemClicked)
            self.flow.addWidget(item)
        layout.addWidget(self.container)

        self.header.mousePressEvent = self._onHeaderClicked

        # 右クリックメニュー
        self.setContextMenuPolicy(QtCore.Qt.CustomContextMenu)
        self.customContextMenuRequested.connect(self._showContextMenu)

    def _onHeaderClicked(self, event):
        self._collapsed = not self._collapsed
        self.container.setVisible(not self._collapsed)

    def _onItemClicked(self, item):
        # 単一選択
        for i in range(self.flow.count()):
            other = self.flow.itemAt(i).widget()
            if other != item:
                other._selected = False
                other.update()
        self.colorSelected.emit(item.color)

    # GroupWidget の右クリックメニュー修正
    def _showContextMenu(self, pos):
        menu = QtWidgets.QMenu(self)
        add_action = menu.addAction("Add Color")
        rename_action = menu.addAction("Rename Color")
        action = menu.exec_(self.mapToGlobal(pos))
        
        if action == add_action:
            self._addColorDialog()
        elif action == rename_action:
            self._renameItem()
    
    # リネーム処理
    def _renameItem(self):
        # 選択中の ColorItem を取得
        selected_item = None
        for i in range(self.flow.count()):
            item = self.flow.itemAt(i).widget()
            if item._selected:
                selected_item = item
                break
        if selected_item is None:
            QtWidgets.QMessageBox.information(self, "Info", "Please select an item to rename.")
            return

        # ダイアログで新しい名前入力
        text, ok = QtWidgets.QInputDialog.getText(self, "Rename Color", "New Name:", text=selected_item.alias)
        if ok and text:
            selected_item.alias = text
            selected_item.update()  # 再描画
            
    def _addColorDialog(self):
        dialog = AddColorDialog(self)
        if dialog.exec_():
            name, color = dialog.getValues()
            index = self.flow.count()  # 内部ID
            item = ColorItem(color, index, name=name)  # aliasとしてユーザー名を表示
            item.clicked.connect(self._onItemClicked)
            self.flow.addWidget(item)
            self.container.update()
            
    def setHeaderFontSize(self, item_size):
        """
        ColorItem サイズに応じてグループ名ラベルのフォントサイズを変更
        """
        # item_size の比率で文字サイズを調整
        font_size = max(12, int(item_size * 0.06))  # 例: 300px -> 18pt
        font = QtGui.QFont()
        font.setPointSize(font_size)
        font.setBold(True)
        self.label.setFont(font)

class ColorDetails(QtWidgets.QWidget):
    def __init__(self):
        super(ColorDetails, self).__init__()
        self.setStyleSheet("background-color: #222222; color: white;")
        layout = QtWidgets.QVBoxLayout(self)
        layout.setContentsMargins(10,10,10,10)
        layout.setSpacing(10)

        # 大きい色サンプル
        self.color_sample = QtWidgets.QLabel()
        self.color_sample.setFixedSize(150,150)
        self.color_sample.setStyleSheet("background-color: #000000; border: 1px solid white;")
        layout.addWidget(self.color_sample, alignment=QtCore.Qt.AlignHCenter)

        # グリッドで詳細情報
        self.info_grid = QtWidgets.QGridLayout()
        self.info_grid.setSpacing(5)
        layout.addLayout(self.info_grid)

        row = 0
        # 名前
        self.name_edit = QtWidgets.QLineEdit()
        self.info_grid.addWidget(QtWidgets.QLabel("Name:"), row, 0)
        self.info_grid.addWidget(self.name_edit, row, 1)
        row += 1

        # RGB
        self.r_spin = QtWidgets.QSpinBox(); self.r_spin.setRange(0,255)
        self.g_spin = QtWidgets.QSpinBox(); self.g_spin.setRange(0,255)
        self.b_spin = QtWidgets.QSpinBox(); self.b_spin.setRange(0,255)

        self.info_grid.addWidget(QtWidgets.QLabel("R:"), row, 0)
        self.info_grid.addWidget(self.r_spin, row, 1)
        row+=1
        self.info_grid.addWidget(QtWidgets.QLabel("G:"), row, 0)
        self.info_grid.addWidget(self.g_spin, row, 1)
        row+=1
        self.info_grid.addWidget(QtWidgets.QLabel("B:"), row, 0)
        self.info_grid.addWidget(self.b_spin, row, 1)
        row+=1

        # カラーパレット
        self.color_button = QtWidgets.QPushButton()
        self.color_button.setFixedSize(50,50)
        self.color_button.setStyleSheet("background-color: #000000; border: 1px solid white;")
        self.info_grid.addWidget(QtWidgets.QLabel("Color:"), row, 0)
        self.info_grid.addWidget(self.color_button, row,1)
        row+=1

        # グループ名
        self.group_edit = QtWidgets.QLineEdit()
        self.info_grid.addWidget(QtWidgets.QLabel("Group:"), row, 0)
        self.info_grid.addWidget(self.group_edit, row,1)
        row+=1

        # インデックス
        self.index_spin = QtWidgets.QSpinBox()
        self.index_spin.setMinimum(0)
        self.index_spin.setMaximum(0)  # 後で更新
        self.info_grid.addWidget(QtWidgets.QLabel("Index:"), row, 0)
        self.info_grid.addWidget(self.index_spin, row,1)
        row+=1

        # 現在編集中の ColorItem と GroupWidget
        self.current_item = None
        self.current_group = None

        # シグナル
        self.name_edit.textChanged.connect(self._onNameChanged)
        self.r_spin.valueChanged.connect(self._onColorChanged)
        self.g_spin.valueChanged.connect(self._onColorChanged)
        self.b_spin.valueChanged.connect(self._onColorChanged)
        self.color_button.clicked.connect(self._openColorDialog)
        self.group_edit.textChanged.connect(self._onGroupChanged)
        self.index_spin.valueChanged.connect(self._onIndexChanged)

    def updateColor(self, color_item, group_widget):
        """ColorItem 選択時にエディタに反映"""
        self.current_item = color_item
        self.current_group = group_widget

        r,g,b = color_item.color
        self.color_sample.setStyleSheet(f"background-color: rgb({r},{g},{b}); border: 1px solid white;")
        self.color_button.setStyleSheet(f"background-color: rgb({r},{g},{b}); border: 1px solid white;")
        self.name_edit.setText(color_item.alias)
        self.r_spin.setValue(r)
        self.g_spin.setValue(g)
        self.b_spin.setValue(b)

        self.group_edit.setText(group_widget.label.text())
        max_index = group_widget.flow.count() - 1
        self.index_spin.setMaximum(max_index)
        self.index_spin.setValue(group_widget.flow.indexOf(color_item))

    # --- シグナルハンドラ ---
    def _onNameChanged(self, text):
        if self.current_item:
            self.current_item.alias = text
            self.current_item.update()

    def _onColorChanged(self):
        if self.current_item:
            r,g,b = self.r_spin.value(), self.g_spin.value(), self.b_spin.value()
            self.current_item.color = (r,g,b)
            self.current_item.update()
            self.color_sample.setStyleSheet(f"background-color: rgb({r},{g},{b}); border: 1px solid white;")
            self.color_button.setStyleSheet(f"background-color: rgb({r},{g},{b}); border: 1px solid white;")

    def _openColorDialog(self):
        if self.current_item:
            current_color = QtGui.QColor(*self.current_item.color)
            color = QtWidgets.QColorDialog.getColor(current_color, self, "Select Color")
            if color.isValid():
                self.r_spin.setValue(color.red())
                self.g_spin.setValue(color.green())
                self.b_spin.setValue(color.blue())

    def _onGroupChanged(self, text):
        """グループ名をリアルタイムに更新"""
        if self.current_group:
            self.current_group.label.setText(text)

    def _onIndexChanged(self, value):
        """FlowLayout 内の順序をリアルタイムに更新"""
        if not self.current_group or not self.current_item:
            return

        flow = self.current_group.flow
        max_index = flow.count() - 1
        value = min(max_index, max(0, value))  # 0～最大に制限

        old_index = flow.indexOf(self.current_item)
        if old_index == -1 or old_index == value:
            return

        # FlowLayout 内で移動
        flow.takeAt(old_index)
        flow.insertWidget(value, self.current_item)

        # インデックスを再設定
        for i in range(flow.count()):
            w = flow.itemAt(i).widget()
            if w:
                w.index = i



# ---------------------------
# メイン
# ---------------------------
class ColorPalette(QtWidgets.QWidget):
    def __init__(self):
        super(ColorPalette, self).__init__()
        self.setWindowTitle("Color Palette")
        self.resize(1200, 950)
        self.setStyleSheet("background-color: #333333;")

        main_layout = QtWidgets.QHBoxLayout(self)
        main_layout.setContentsMargins(10, 10, 10, 10)
        main_layout.setSpacing(10)

        # ------------------------
        # 左側（縦に2つ）
        # ------------------------
        left_widget = QtWidgets.QWidget()
        left_layout = QtWidgets.QVBoxLayout(left_widget)
        left_layout.setContentsMargins(0,0,0,0)
        left_layout.setSpacing(10)

        # ここにスライダー追加（上部）
        self.size_slider = QtWidgets.QSlider(QtCore.Qt.Horizontal)
        self.size_slider.setRange(100, 500)  # サイズ 100~500
        self.size_slider.setValue(300)
        self.size_slider.setStyleSheet("QSlider::handle {background: #00ffff;}")
        left_layout.addWidget(self.size_slider)

        # カラーグリッドビュー
        self.scroll = QtWidgets.QScrollArea()
        self.scroll.setWidgetResizable(True)
        self.scroll.setStyleSheet("border: none;")
        content = QtWidgets.QWidget()
        scroll_layout = QtWidgets.QVBoxLayout(content)
        scroll_layout.setContentsMargins(0,0,0,0)
        scroll_layout.setSpacing(25)

        self.groups = []
        for g in range(3):
            colors = [(random.randint(0,255), random.randint(0,255), random.randint(0,255)) for _ in range(10)]
            group = GroupWidget(f"Group {g+1}", colors)
            group.colorSelected.connect(lambda c, grp=group: self.updateSelectedColor(c, grp))
            scroll_layout.addWidget(group)
            self.groups.append(group)
        scroll_layout.addStretch()
        content.setLayout(scroll_layout)
        self.scroll.setWidget(content)

        left_layout.addWidget(self.scroll)

        # 選択カラープレビュー
        self.selection_preview = QtWidgets.QWidget()
        preview_layout = QtWidgets.QHBoxLayout(self.selection_preview)
        preview_layout.setContentsMargins(10,5,10,5)
        preview_layout.setSpacing(10)
        self.color_sample = QtWidgets.QLabel()
        self.color_sample.setFixedSize(50,50)
        self.color_sample.setStyleSheet("background-color: #000000; border: 1px solid white;")
        self.color_label = QtWidgets.QLabel("RGB: -")
        self.color_label.setStyleSheet("color: white; font-size: 14px;")
        preview_layout.addWidget(self.color_sample)
        preview_layout.addWidget(self.color_label)
        preview_layout.addStretch()
        left_layout.addWidget(self.selection_preview)

        # ------------------------
        # 右側詳細エディタ
        # ------------------------
        self.details = ColorDetails()

        # ------------------------
        # スプリッターで左右分割
        # ------------------------
        splitter = QtWidgets.QSplitter(QtCore.Qt.Horizontal)
        splitter.addWidget(left_widget)
        splitter.addWidget(self.details)
        splitter.setSizes([600, 400])

        main_layout.addWidget(splitter)

        # ------------------------
        # スライダーシグナル
        # ------------------------
        self.size_slider.valueChanged.connect(self._onSizeChanged)

    def _onSizeChanged(self, value):
        """スライダーで全アイテムのサイズを変更"""
        for group in self.groups:
            # ColorItem サイズ変更
            for i in range(group.flow.count()):
                item = group.flow.itemAt(i).widget()
                if isinstance(item, ColorItem):
                    item.setItemSize(value)
            # グループ名ラベルのサイズも変更
            group.setHeaderFontSize(value)

    def updateSelectedColor(self, color, group_widget):
        # 左側下部プレビュー更新
        r, g, b = color
        self.color_label.setText(f"RGB: ({r}, {g}, {b})")
        self.color_sample.setStyleSheet(f"background-color: rgb({r},{g},{b}); border: 1px solid white;")

        # 右側詳細エディタ更新
        selected_item = None
        for i in range(group_widget.flow.count()):
            item = group_widget.flow.itemAt(i).widget()
            if item._selected:
                selected_item = item
                break
        if selected_item:
            self.details.updateColor(selected_item, group_widget)





# ---------------------------
# Maya起動用
# ---------------------------
def show_palette():
    import maya.OpenMayaUI as omui
    from shiboken2 import wrapInstance

    main_win_ptr = omui.MQtUtil.mainWindow()
    main_win = wrapInstance(int(main_win_ptr), QtWidgets.QWidget)

    # 既に開いているウィンドウを閉じる
    for w in main_win.findChildren(QtWidgets.QWidget, "ColorPaletteWindow"):
        w.close()

    win = ColorPalette()
    
    win.setObjectName("ColorPaletteWindow")
    win.setParent(main_win)
    win.setWindowFlags(QtCore.Qt.Window)
    win.show()
    return win


# if __name__ == "__main__":
#     show_palette()


def show_dock_window():
    # 既存のものがあれば削除
    if cmds.workspaceControl(MyDockWindow.UI_NAME + "WorkspaceControl", q=True, exists=True):
        cmds.deleteUI(MyDockWindow.UI_NAME + "WorkspaceControl", control=True)

    # Mayaのメインウィンドウを親に
    main_window_ptr = omui.MQtUtil.mainWindow()
    main_window = wrapInstance(int(main_window_ptr), QtWidgets.QWidget)

    # インスタンス生成
    ui = MyDockWindow(parent=main_window)

    # ドッキング可能として表示
    ui.show(dockable=True,
            area='right',                   # ドッキング位置 (left, right, top, bottom)
            floating=False,
            allowedArea='all',
            retain=False)                   # retain=True にすると再起動時にも保持される

    return ui

shortcut = QtWidgets.QShortcut(QtGui.QKeySequence("Ctrl+D"), self)
shortcut.setContext(QtCore.Qt.WidgetShortcut)  # ←ここが重要！
shortcut.activated.connect(self.onShortcut)

def keyPressEvent(self, event):
    if event.key() == QtCore.Qt.Key_Space:
        print("Space pressed in tool")
        event.accept()  # ←このイベントだけ自前処理
    else:
        event.ignore()  # ←Mayaに渡す！
        super(MyDockWindow, self).keyPressEvent(event)
        
def show_dock_window():
    ui_name = MyDockWindow.UI_NAME
    workspace_name = ui_name + "WorkspaceControl"

    # 既にDockが存在する場合は削除
    if cmds.workspaceControl(workspace_name, q=True, exists=True):
        cmds.deleteUI(workspace_name, control=True)

    # Mayaメインウィンドウを親に
    from maya import OpenMayaUI as omui
    from shiboken2 import wrapInstance
    main_window = wrapInstance(int(omui.MQtUtil.mainWindow()), QtWidgets.QWidget)

    # ウィンドウ生成
    ui = MyDockWindow(parent=main_window)

    # Dock表示
    ui.show(dockable=True,
            area='right',
            floating=False,
            allowedArea='all',
            retain=False)

    return ui


# 再利用法
workspace_name = MyDockWindow.UI_NAME + "WorkspaceControl"

if cmds.workspaceControl(workspace_name, q=True, exists=True):
    cmds.workspaceControl(workspace_name, e=True, restore=True)
else:
    ui = MyDockWindow()
    ui.show(dockable=True, area='right', floating=False)

# 親を明示的に
main_window = wrapInstance(int(omui.MQtUtil.mainWindow()), QtWidgets.QWidget)
ui = MyDockWindow(parent=main_window)
ui.show(dockable=True, floating=True)