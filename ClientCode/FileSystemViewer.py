""" This module is responsible for implementing most of the features regarding 
    the user's filesystems... It connects GUI to Logic, networking, multi-threading, etc."""
# Official:
import webbrowser
import os
import tempfile
from dataclasses import dataclass
from typing import Union, List, Optional, Dict
from enum import Enum
from PyQt6.QtWidgets import QWidget

# 3rd Party:
from cachetools import cached, TTLCache
from PyQt6 import QtCore, QtGui, QtWidgets
import qtawesome as qta

# Mine
# Networking:
from Requests import Requests
import RAP
from IconGenerator import icon_manager, IconTypes, IMAGE_FILES

# Others:
from ThreadedClasses import FileDownloadThread, FileUploadThread, NodeMovingThread, AlternativeIconRunnable, AlternativeIconThread, NodeCopyingThread, NodeDeletingThread, AsyncBlockingAction, MultiFileUploadThread, FileUploadInfo
from PropertiesWidget import PropertiesWidget
from Utilities import wait_cursor, error_resolver, ErrorDisplay, get_lowercase_extension

SIZE_ROLE = QtCore.Qt.ItemDataRole.UserRole + 1

class LoadingDialog(QtWidgets.QDialog):
    def __init__(self, name: str, parent=None) -> None:
        super().__init__(parent)
        
        layout = QtWidgets.QHBoxLayout()
        label = QtWidgets.QLabel(name)
        font = QtGui.QFont()
        font.setPointSize(12)
        label.setFont(font)
        layout.addWidget(label)
        spin_widget = qta.IconWidget()
        spin_widget.setIconSize(QtCore.QSize(32, 32))
        spin_icon = qta.icon('mdi.loading', color='red',
                            animation=qta.Spin(spin_widget, 4, 1.5))
        spin_widget.setIcon(spin_icon)
        layout.addWidget(spin_widget)

        self.setLayout(layout)

def createItem(name, data: Union[RAP.DirInfo, RAP.FileInfo], is_folder=True, controller: Optional['FileNavigation'] = None) -> 'Item':
    ''' Utility function for creating items of 'Item' types. 
        All items created for the Custom Item Model should be 
        created using this function.

        If you wish to fetch icons pass the current FileNavigation 
        instance as controller.

        It can be argued that I should've implmented this as an override 
        of the Qt Classes, but while Qt heavily relies on OOP, I found it 
        much easier to handle it like this.'''
    contype: Union[IconTypes, str]
    if is_folder:
        contype = IconTypes.Folder
    else:
        contype = get_lowercase_extension(data.display_name)
    icon = icon_manager.get(contype)

    item = Item(icon, name)
    item.setData(0, SIZE_ROLE)
    if isinstance(data, RAP.FileInfo):
        item.setData(data.size, SIZE_ROLE)
    item.setInfo(Info(data))
    if not is_folder: item.setDropEnabled(False)
    item.setToolTip(f'<FONT>{name}</FONT>')
    item.setSizeHint(QtCore.QSize(50,64))
    
    if contype in IMAGE_FILES and contype != 'svg':
        if controller:
            try:
                if data.id in AlternativeIconRunnable.cached_icons:
                    item.set_tumb(AlternativeIconRunnable.cached_icons[data.id])
                else:
                    task = AlternativeIconRunnable(data.id)
                    task.signals.achieved.connect(item.set_tumb)
                    controller.icon_thread.submit(task)
            except RuntimeError:
                pass
    return item

@dataclass
class Info:
    '''Convenience dataclass used to store data about an Item.'''
    data: Union[RAP.DirInfo, RAP.FileInfo]

    def is_folder(self):
        return isinstance(self.data, RAP.DirInfo)

class Item(QtGui.QStandardItem):
    '''Mostly a convenience class that establishes an interface for using 
       Items with the right typing.
       Also defines set_thumb function that is used as a slot for setting 
       an Icon in the Event Loop from a QImage that was fetched in another 
       thread'''
    def parent(self) -> 'Item':
        return super().parent() # type: ignore
    
    def takeRow(self, row: int) -> 'List[Item]': # type: ignore
        return super().takeRow(row) # type: ignore

    def setInfo(self, info: Info):
        self.info = info
    
    def getInfo(self) -> Info:
        return self.info
    
    def set_tumb(self, image):
        try:
            image = QtGui.QImage.fromData(image)
            pixmap = QtGui.QPixmap.fromImage(image)
            icon = QtGui.QIcon(pixmap)
            self.setIcon(icon)
        except RuntimeError:
            pass

class FileView(QtWidgets.QListView):
    '''Custom view with overloaded CTRL C/X/S (copy, cut, paste)
       Also delete and drop signals that will be handled using slots in the main class'''
    ctrl_c_signal = QtCore.pyqtSignal()
    ctrl_x_signal = QtCore.pyqtSignal()
    ctrl_v_signal = QtCore.pyqtSignal()
    delete_signal = QtCore.pyqtSignal()
    move_signal = QtCore.pyqtSignal(tuple)

    def setMode(self, mode: QtWidgets.QListView.ViewMode) -> None:
        super().setViewMode(mode)
        # Other Settings:
        self.setDragDropMode(QtWidgets.QAbstractItemView.DragDropMode.InternalMove) 
       
    def keyPressEvent(self, event: QtGui.QKeyEvent):
        if event.key() == QtCore.Qt.Key.Key_C and event.modifiers() == QtCore.Qt.KeyboardModifier.ControlModifier:
            self.ctrl_c_signal.emit()
            #QtWidgets.QMessageBox.information(self, "Copy", "The Items are copied internally")
        elif event.key() == QtCore.Qt.Key.Key_X and event.modifiers() == QtCore.Qt.KeyboardModifier.ControlModifier: 
            self.ctrl_x_signal.emit()
            #QtWidgets.QMessageBox.information(self, "Cut", "The Items are cut internally")
        elif event.key() == QtCore.Qt.Key.Key_V and event.modifiers() == QtCore.Qt.KeyboardModifier.ControlModifier: 
            self.ctrl_v_signal.emit()
            #QtWidgets.QMessageBox.information(self, "Paste", "The Items are pasted internally")
        elif event.key() == QtCore.Qt.Key.Key_Delete:
            if QtWidgets.QMessageBox.critical(self, 'Are you sure?', 'The selected files will be deleted', \
                                              QtWidgets.QMessageBox.StandardButton.Yes |                   \
                                              QtWidgets.QMessageBox.StandardButton.No)                     \
                                              == QtWidgets.QMessageBox.StandardButton.Yes:
                self.delete_signal.emit()

        else:
            super().keyPressEvent(event)
    
    def dropEvent(self, e: QtGui.QDropEvent) -> None:
        src_indexes = self.selectedIndexes()
        dst_index = self.indexAt(e.position().toPoint())
        self.move_signal.emit((src_indexes, dst_index))

class MenuManager:
    '''Convenience class for creating and managing contextmenus 
       in a clearer way.'''
    def __init__(self) -> None:
        self.menu = QtWidgets.QMenu()
        self.actions: Dict[str, QtGui.QAction] = {}
    
    def register(self, name: str, icon: QtGui.QIcon) -> QtGui.QAction:
        self.actions[name] = QtGui.QAction(icon, name, self.menu)
        self.menu.addAction(self.get(name))
        return self.get(name)
    
    def get(self, name: str) -> QtGui.QAction:
        return self.actions[name]        

class SortProxy(QtCore.QObject):
    '''Holds the current sorting type, 
       and emits a signal on change.
       The Signal should be connected
       to a model-sorting-slot'''
    changed = QtCore.pyqtSignal()
    class Type(Enum):
        Nothing = 1
        Size = 2
        Name = 3
    
    def __init__(self) -> None:
        super().__init__()
        self.__type = SortProxy.Type.Nothing
    
    def set(self, how: Type) -> None:
        self.__type = how
        self.changed.emit()
    
    def get(self) -> Type:
        return self.__type

class ClipboardItemProxy:
    '''Responsible for holding the state of
       copying, cutting etc.'''
    class Action(Enum):
        Copy = 1
        Cut = 2

    def __init__(self) -> None:
        self.items: List[Item] = []
        self.action: ClipboardItemProxy.Action
        self.active = False
    
    def copy(self, items: List[Item]) -> None:
        self.active = True
        self.items = items
        self.action = ClipboardItemProxy.Action.Copy
    
    def cut(self, items: List[Item]) -> None:
        self.active = True
        self.items = items
        self.action = ClipboardItemProxy.Action.Cut
    
    def mode(self) -> 'ClipboardItemProxy.Action':
        return self.action

    def paste(self) -> List[Item]:
        if not self.active:
            return []
        if self.action == ClipboardItemProxy.Action.Cut:
            self.active = False
            return self.items
        else:
            return self.items
    
    def clear(self):
        self.active = False

class ItemModel(QtGui.QStandardItemModel):
    '''For type checking.'''
    def item(self, row: int, column: int = ...) -> Item: # type: ignore
        return super().item(row, column) # type: ignore
    def itemFromIndex(self, index: QtCore.QModelIndex) -> Item:
        return super().itemFromIndex(index) # type: ignore

class Setting(Enum):
    MyFiles = 1
    SharedFiles = 2
    Trash = 3

class FileNavigation(QtCore.QObject):
    """ Most of the FileSystem navigation, actions, features and logic are 
        defined in this class as member functions, that are connected to signals 
        as slots... The function and logic describes themselves, hence no comments."""
    
    def __init__(self, root_name: str = "My Files", parent=None):
        super(FileNavigation, self).__init__(parent)  
        self.windows: List[tuple] = []

        ################################## ToolBar
        self.toolbar = QtWidgets.QToolBar()
        self.toolbar.setFont(QtGui.QFont(self.toolbar.font().family(), 14))

        self.toolbar.actionTriggered.connect(self.on_action_trigger)


        ################################## Model        
        self.model = ItemModel(self)
        self.model.invisibleRootItem().appendRow(createItem(root_name, RAP.DirInfo(), True))
        it = self.model.item(0, 0)
        ix = self.model.indexFromItem(it)
        root_action = self.toolbar.addAction(it.text())
        root_action.setData(QtCore.QPersistentModelIndex(ix))
        


        ################################## Create View
        self.listview = FileView()
        self.listview.activated.connect(self.on_clicked) 
        self.listview.setModel(self.model)
        self.listview.setRootIndex(ix)

        #Settings
        self.listview.setViewMode(QtWidgets.QListView.ViewMode.IconMode)
        self.listview.setDragDropMode(QtWidgets.QAbstractItemView.DragDropMode.InternalMove)
        self.listview.setIconSize(QtCore.QSize(40,40))
        #self.listview.setMovement(QtWidgets.QListView.Movement.Static)
        self.listview.setTextElideMode(QtCore.Qt.TextElideMode.ElideRight)
        self.listview.setUniformItemSizes(True)
        self.listview.setResizeMode(QtWidgets.QListView.ResizeMode.Adjust)
        self.listview.setSpacing(4)
        self.listview.setSelectionMode(QtWidgets.QAbstractItemView.SelectionMode.ExtendedSelection)
        self.listview.setLayoutMode(QtWidgets.QListView.LayoutMode.Batched)
        self.listview.setEditTriggers(QtWidgets.QAbstractItemView.EditTrigger.NoEditTriggers)
        self.listview.setContextMenuPolicy(QtCore.Qt.ContextMenuPolicy.CustomContextMenu)


        ################################# Context Menus
        self.item_menu = MenuManager()
        self.space_menu = MenuManager()
        self.item_menu.register("Copy", qta.icon('fa5s.copy')).triggered.connect(self.copy)
        self.listview.ctrl_c_signal.connect(self.copy)
        self.item_menu.register("Move/Cut", qta.icon('mdi.content-cut')).triggered.connect(self.cut)
        self.listview.ctrl_x_signal.connect(self.cut)
        self.item_menu.register("Download",qta.icon('fa5s.file-download')).triggered.connect(self.download)
        self.item_menu.register("Resume Download", qta.icon('ei.download-alt')\
                                ).triggered.connect(self.resume_download)        
        self.item_menu.register("Properties", qta.icon('msc.symbol-property')).triggered.connect(self.properties)
        self.item_menu.register("Delete", qta.icon('mdi.delete-outline')).triggered.connect(self.delete)
        self.listview.delete_signal.connect(self.delete)
        self.space_menu.register("Create A Folder", qta.icon('fa5s.folder-plus')\
                                 ).triggered.connect(self.create_folder)
        self.space_menu.register("Paste", qta.icon('mdi6.content-paste')).triggered.connect(self.paste)
        self.listview.ctrl_v_signal.connect(self.paste)
        self.space_menu.register("Upload Files", qta.icon('fa5s.file-upload')).triggered.connect(self.upload_files)
        self.listview.customContextMenuRequested.connect(self.context_menu)

        self.shared_item_menu = MenuManager()
        self.shared_item_menu.register("Properties", qta.icon('msc.symbol-property')).triggered.connect(self.properties)
        self.shared_item_menu.register("Download",qta.icon('fa5s.file-download')).triggered.connect(self.download)
        self.shared_item_menu.register("Resume Download", qta.icon('ei.download-alt')).triggered.connect(self.resume_download)
        
        self.folder_menu = MenuManager()
        self.folder_menu.register("Zip Folder", qta.icon('mdi.folder-zip')).triggered.connect(self.zip)
        self.folder_menu.register("Delete", qta.icon('mdi.delete-outline')).triggered.connect(self.delete)
        self.folder_menu.register("Properties", qta.icon('msc.symbol-property')).triggered.connect(self.properties)
        self.folder_menu.register("Copy", qta.icon('fa5s.copy')).triggered.connect(self.copy)
        self.folder_menu.register("Move/Cut", qta.icon('mdi.content-cut')).triggered.connect(self.cut)

        self.trash_menu = MenuManager()
        self.trash_menu.register("Restore File", qta.icon('mdi6.delete-restore')).triggered.connect(self.restore)
        ################################# Stylesheet
        self.listview.setStyleSheet(""" QListView { 
                                                spacing: 10px;}""")
        ################################# 
        self.clipboard = ClipboardItemProxy()
        self.sortProxy = SortProxy()
        self.sortProxy.changed.connect(self.sort)
        ################################
        self.listview.setCurrentIndex(QtCore.QModelIndex()) #Unfocus
        
        self.listview.move_signal.connect(self.drop_items)

    @QtCore.pyqtSlot()
    def properties(self):
        id = self.model.itemFromIndex(self.listview.selectionModel().selectedIndexes()[0]).getInfo().data.id
        with error_resolver(self.error):
            window = PropertiesWidget(self.user.ExtendedInfo(id).info, self.user)
            self.windows.append(window)
            window.show()
            window.error.connect(self.error)
            
            @QtCore.pyqtSlot()
            def done():
                self.fill_dir(self.listview.rootIndex(), True)
            window.finished.connect(done)
        
    @QtCore.pyqtSlot(ErrorDisplay)
    def error(self, error: ErrorDisplay):
        QtWidgets.QMessageBox.critical(self.listview, error.title, error.information)

    @QtCore.pyqtSlot(tuple)
    def drop_items(self, data):
        src_indexes = data[0]
        dst_index = data[1]
        dst_item = self.model.itemFromIndex(dst_index)
        if not dst_item:
            return None
        if self.listview.rootIndex() == dst_index: 
            return None
        items = []
        for index in src_indexes:
            items.append(self.model.itemFromIndex(index))
        self.move_items(items, dst_item)
    
    def move_items(self, what: List[Item], target: Item):
        if not target.getInfo().is_folder():
            return None
        
        window = QtWidgets.QProgressDialog()
        window.setLabelText('Moving Items')
        window.setMaximum(len(what))

        node_ids = []
        for item in what:
            if item.parent() != target:
                node_ids.append(item.getInfo().data.id)

        thread = NodeMovingThread(self.user, node_ids, target.getInfo().data.id)
        thread.progress.connect(window.setValue)
        window.canceled.connect(thread.stop)
        window.show()

        @QtCore.pyqtSlot()
        def done():
            self.fill_dir(self.listview.rootIndex(), force=True) # (Refresh)
            self.listview.model().layoutChanged.emit()
            window.close()
            window.deleteLater()
            thread.deleteLater()
        
        thread.failed.connect(self.error)
        thread.done.connect(done)
        self.windows.append((window, thread))
        thread.start() 
    
    def copy_items(self, what: List[Item], target: Item):
        if not target.getInfo().is_folder():
            return None
        
        window = QtWidgets.QProgressDialog()
        window.setLabelText('Copying Items')
        window.setMaximum(len(what))

        node_ids = []
        for item in what:
            node_ids.append(item.getInfo().data.id)

        thread = NodeCopyingThread(self.user, node_ids, target.getInfo().data.id)
        thread.progress.connect(window.setValue)
        window.canceled.connect(thread.stop)
        window.show()

        @QtCore.pyqtSlot()
        def done():
            self.fill_dir(self.listview.rootIndex(), force=True) # (Refresh)
            self.listview.model().layoutChanged.emit()
            window.close()
            window.deleteLater()
            thread.deleteLater()
        
        thread.failed.connect(self.error)
        thread.done.connect(done)
        self.windows.append((window, thread))
        thread.start() 

    @QtCore.pyqtSlot(str)   
    def search_items(self, keywords: str):
        current = self.model.itemFromIndex(self.listview.rootIndex())
        for row in range(current.rowCount()):
            item = current.child(row)
            if keywords and keywords.lower() not in item.text().lower():
                self.listview.setRowHidden(row, True)
            else:
                self.listview.setRowHidden(row, False)

    def configure_user(self, user: Requests, setting: Setting) -> None:
        self.setting = setting
        self.user = user
        self.icon_thread = AlternativeIconThread(self.user)
        self.icon_thread.start()
        self.icon_thread.error.connect(self.error)

        if setting == Setting.MyFiles:
            with wait_cursor():
                head = self.user.ListDir((RAP.DirInfo(display_name="", id=0)))
            dir = head.dirs[0]
            self.model.item(0, 0).setInfo(Info(dir))
            self.fill_dir(self.model.index(0,0))

        elif setting == Setting.SharedFiles:
            dir = RAP.DirInfo(display_name="", id=1)
            self.model.item(0, 0).setInfo(Info(dir))
            self.model.item(0, 0).setText('Shared Files')
            self.fill_dir(self.model.index(0,0))

        elif setting == Setting.Trash:
            dir = RAP.DirInfo(display_name="", id=2)
            self.model.item(0, 0).setInfo(Info(dir))
            self.model.item(0, 0).setText('Trash')
            self.fill_dir(self.model.index(0,0))

    def create_folder(self) -> None:
        holder = QtWidgets.QWidget()
        name, valid = QtWidgets.QInputDialog.getText(holder, 'Choose Folder Name', 'Name: ')
        if valid:
            cur = self.model.itemFromIndex(self.listview.rootIndex())
            info = cur.getInfo()
            if isinstance(info.data, RAP.FileInfo): return
            with error_resolver(self.error):
                response = self.user.CreateFolder(name, info.data)
                if response.response.status == RAP.BasicResponseSTATUS.FAILED:
                    QtWidgets.QMessageBox.critical(self.listview, "Operation Failed", "...")
                else:
                    item = createItem(name=name, data=RAP.DirInfo(display_name=name, id=response.id))
                    cur.appendRow(item)

    def upload_file(self, file: str):
        d_name = file.split('/')[-1]
        size = os.stat(file).st_size
        window = QtWidgets.QProgressDialog()
        window.setLabelText(d_name)
        cur: Item = self.model.itemFromIndex(self.listview.rootIndex())
        data = cur.getInfo().data
        if not isinstance(data, RAP.DirInfo):
            return QtWidgets.QMessageBox.critical(self.listview, 'Cannot Upload', "This isn't a folder")
        thread = FileUploadThread(self.user, file, data, size)
        thread.progress.connect(window.setValue)
        window.canceled.connect(thread.stop)

        window.show()
        @QtCore.pyqtSlot()
        def done():
            self.fill_dir(self.listview.rootIndex(), True)
            window.close()
            thread.deleteLater()
            
        thread.failed.connect(self.error)
        thread.done.connect(done)
        self.windows.append((window, thread))
        thread.start()
    
    def resume_download(self):
        file_info = self.model.itemFromIndex(self.listview.currentIndex()).getInfo().data
        if isinstance(file_info, RAP.DirInfo): return
        which, _ = QtWidgets.QFileDialog.getOpenFileName(self.listview, 'Choose The Partial File')
        if not which: return

        window = QtWidgets.QProgressDialog()
        file_name = which.split('/')[-1]
        size = os.stat(which).st_size
        window.setLabelText(f'Resuming Download... {file_name}')
        thread = FileDownloadThread(self.user, which, file_info, start=size, end=file_info.size)
        thread.progress.connect(window.setValue)
        window.canceled.connect(thread.stop)
        window.show()
        
        @QtCore.pyqtSlot()
        def done():
            window.close()
            window.deleteLater()
            thread.deleteLater()
        
        thread.failed.connect(self.error)
        thread.done.connect(done)
        self.windows.append((window, thread))
        thread.start()

    def download_a_file(self, file: RAP.FileInfo):
        file_type = file.display_name.split('.')[-1]
        file_types = f"{file_type.upper()} (*.{file_type});; All (*)" 
        where, _ = QtWidgets.QFileDialog.getSaveFileName(self.listview, "Save File", file.display_name, filter=file_types)
        if not where: return

        window = QtWidgets.QProgressDialog()
        window.setLabelText(f'Downloading... {file.display_name}')
        thread = FileDownloadThread(self.user, where, file)
        thread.progress.connect(window.setValue)
        window.canceled.connect(thread.stop)
        window.show()

        @QtCore.pyqtSlot()
        def done():
            window.close()
            window.deleteLater()
            thread.deleteLater()

        thread.failed.connect(self.error)
        thread.done.connect(done)
        self.windows.append((window, thread))
        thread.start()

    def download(self):
        selected = self.listview.selectionModel().selectedIndexes()
        if len(selected) < 1: return
        return self.download_a_file(self.model.itemFromIndex(self.listview.currentIndex()).getInfo().data)
    
    def upload_files(self):
        paths, valid = QtWidgets.QFileDialog.getOpenFileNames(self.listview)
        if not valid: return 
        where = self.model.itemFromIndex(self.listview.rootIndex())
        where_data = where.getInfo().data

        infos: List[FileUploadInfo] = []
        for path in paths:
            infos.append(FileUploadInfo(path, os.stat(path).st_size))
        
        window = QtWidgets.QProgressDialog()
        thread = MultiFileUploadThread(self.user, infos, where_data)

        thread.current_file.connect(lambda s: window.setLabelText(s[: min(len(s), 20)]+"..."))
        thread.progress.connect(window.setValue)
        window.canceled.connect(thread.stop)
        
        thread.failed.connect(self.error)
        
        @QtCore.pyqtSlot()
        def done():
            window.close()
            window.deleteLater()
            thread.deleteLater()

            self.forced_fill_dir(self.listview.rootIndex())
        

        thread.done.connect(done)
        self.windows.append((window, thread))
        thread.start()
        window.show()
        
    def delete(self) -> None:
        self.clipboard.clear()
        selected = self.listview.selectionModel().selectedIndexes()
        selected_ids: List[int] = []
        for index in selected:
            selected_ids.append(self.model.itemFromIndex(index).getInfo().data.id)

        window = QtWidgets.QProgressDialog()
        window.setLabelText("Deleting...")
        thread = NodeDeletingThread(self.user, selected_ids)
        window.setMaximum(len(selected_ids))
        thread.progress.connect(window.setValue)
        window.canceled.connect(thread.stop)
        window.show()

        @QtCore.pyqtSlot()
        def done():
            window.close()
            window.deleteLater()
            thread.deleteLater()
            self.fill_dir(self.listview.rootIndex(), force=True)

        thread.failed.connect(self.error)
        thread.done.connect(done)
        self.windows.append((window, thread))
        thread.start()

    def copy(self) -> None:
        selected = self.listview.selectionModel().selectedIndexes()
        items: List[Item] = []
        for index in selected:
            item = self.model.itemFromIndex(index)
            items.append(item)
        self.clipboard.copy(items)

    def restore(self):
        selected = self.listview.selectionModel().selectedIndexes()
        items: List[Item] = []
        for index in selected:
            item = self.model.itemFromIndex(index)
            items.append(item)
        to = Item()
        to.setInfo(Info(RAP.DirInfo(id=0)))
        self.move_items(items, to)

    def cut(self) -> None:
        if self.setting.MyFiles:
            selected = self.listview.selectionModel().selectedIndexes()
            selectedItems: List[Item] = []
            for index in selected:
                selectedItems.append(self.model.itemFromIndex(index))
            
            items: List[Item] = []
            for item in selectedItems:
                item = item.parent().takeRow(item.row())[0]
                items.append(item)
            
            self.clipboard.cut(items)
            self.listview.setCurrentIndex(QtCore.QModelIndex())
            self.listview.model().layoutChanged.emit()

    def paste(self):
        cur = self.model.itemFromIndex(self.listview.rootIndex())
        
        to_paste = self.clipboard.paste()
        if len(to_paste) == 0:
            return None

        with wait_cursor():
           with error_resolver(self.error):
                if self.clipboard.mode() == ClipboardItemProxy.Action.Cut:
                    self.move_items(to_paste, cur)
                else:
                    self.copy_items(to_paste, cur)

        self.listview.model().layoutChanged.emit()

    def zip(self):
        selected = self.listview.selectionModel().selectedIndexes()
        if len(selected) < 1:
            return
        selected = selected[0]
        item: Item = self.model.itemFromIndex(selected)
        thread = AsyncBlockingAction(self.user.ZipFolder, item.getInfo().data.id)
        thread.failed.connect(self.error)

        window = LoadingDialog(f"Zipping {item.text()}")
        window.show()
        @QtCore.pyqtSlot()
        def done():
            window.close()
            window.deleteLater()
            thread.deleteLater()

        thread.failed.connect(self.error)
        thread.done.connect(done)
        self.windows.append((window, thread))
        thread.start()
        thread.done.connect(done)

    def unzip(self):
        selected = self.listview.selectionModel().selectedIndexes()
        if len(selected) < 1:
            return
        selected = selected[0]
        item: Item = self.model.itemFromIndex(selected)

        thread = AsyncBlockingAction(self.user.UnzipFolder, item.getInfo().data.id)
        thread.failed.connect(self.error)       
        window = LoadingDialog(f"Unzipping {item.text()}")
        window.show()

        @QtCore.pyqtSlot()
        def done():
            window.close()
            window.deleteLater()
            thread.deleteLater()

        thread.failed.connect(self.error)
        thread.done.connect(done)
        self.windows.append((window, thread))
        thread.start()
        thread.done.connect(done)

    def context_menu(self, place):
        index = self.listview.indexAt(place)
        if index.isValid():
            item = self.model.itemFromIndex(index)
            if self.setting == Setting.Trash:
                self.trash_menu.menu.exec(self.listview.mapToGlobal(place))
            elif item.getInfo().is_folder():
                self.folder_menu.menu.exec(self.listview.mapToGlobal(place))
            else:
                info = item.getInfo().data
                if info.display_name.split('.')[-1] == 'zip':
                    action = QtGui.QAction(qta.icon('fa.folder-open'), 'Unzip')
                    if self.setting == Setting.MyFiles:
                        menu = self.item_menu.menu
                    elif self.setting == Setting.SharedFiles:
                        menu = self.shared_item_menu.menu
                    menu.addAction(action)
                    action.triggered.connect(self.unzip)
                    menu.exec(self.listview.mapToGlobal(place))
                else:
                    if self.setting == Setting.MyFiles:
                        self.item_menu.menu.exec(self.listview.mapToGlobal(place))
                    elif self.setting == Setting.SharedFiles:
                        self.shared_item_menu.menu.exec(self.listview.mapToGlobal(place))
        else:
            if self.setting == Setting.MyFiles or self.setting == Setting.SharedFiles:
                self.space_menu.menu.exec(self.listview.mapToGlobal(place))

    def fill_dir(self, index: QtCore.QModelIndex, force=False):
        if force or not self.model.itemFromIndex(index).hasChildren(): # if forced or doesn't have children == new
            self.forced_fill_dir(index)
        else:
            self.cached_fill_dir(index)
        
    def forced_fill_dir(self, index: QtCore.QModelIndex):
        parent: Item = self.model.itemFromIndex(index)
        with wait_cursor():
            data = parent.getInfo().data
            if isinstance(data, RAP.DirInfo):
                with error_resolver(self.error):
                    answer = self.user.ListDir(data) 
                    parent.removeRows(0, parent.rowCount()) # Clear Dir
                    # Fill with data:
                    for folder in answer.dirs:
                        parent.appendRow(createItem(folder.display_name, folder, True))
                    for file in answer.files:
                        parent.appendRow(createItem(file.display_name, file, False, controller=self))
        
        what = self.sortProxy.get()
        if what == SortProxy.Type.Nothing:
            pass
        elif what == SortProxy.Type.Name:
            self.model.setSortRole(QtCore.Qt.ItemDataRole.DisplayRole)
            self.model.sort(0, QtCore.Qt.SortOrder.AscendingOrder)
        elif what == SortProxy.Type.Size:
            self.model.setSortRole(SIZE_ROLE)
            self.model.sort(0, QtCore.Qt.SortOrder.AscendingOrder)
        self.listview.model().layoutChanged.emit()
    
    @QtCore.pyqtSlot()
    def sort(self):
        what = self.sortProxy.get()
        if what == SortProxy.Type.Nothing:
            self.fill_dir(self.listview.rootIndex(), force=True)
        elif what == SortProxy.Type.Name:
            self.model.setSortRole(QtCore.Qt.ItemDataRole.DisplayRole)
            self.model.sort(0, QtCore.Qt.SortOrder.AscendingOrder)
        elif what == SortProxy.Type.Size:
            self.model.setSortRole(SIZE_ROLE)
            self.model.sort(0, QtCore.Qt.SortOrder.AscendingOrder)
        self.listview.model().layoutChanged.emit()

    @cached(cache=TTLCache(maxsize=1024, ttl=7)) # results are valid for half a minute
    def cached_fill_dir(self, index: QtCore.QModelIndex):
        return self.forced_fill_dir(index)
                
    @QtCore.pyqtSlot(QtCore.QModelIndex)
    def on_clicked(self, index) -> None:
        item = self.model.itemFromIndex(index)
        info = item.getInfo()
        extension = get_lowercase_extension(item.text())

        if info.is_folder():
            action = self.toolbar.addAction(index.data())
            action.setData(QtCore.QPersistentModelIndex(index))
            self.listview.setRootIndex(index)
            self.model.layoutChanged.emit()
            self.fill_dir(index)

        elif extension == 'mp4':
            with wait_cursor():
                with error_resolver(self.error):
                    response = self.user.AskForStreamUrl(info.data) # type: ignore
                    if response.response.status == RAP.BasicResponseSTATUS.FAILED: return
                    webbrowser.open(response.url)

        elif extension in IMAGE_FILES:
            with tempfile.TemporaryFile() as file:
                with error_resolver(self.error):
                    _data = QtCore.QByteArray()
                    with wait_cursor():
                        self.user.singleton.download_into(file, RAP.FileDownload(info.data)) # type: ignore
                    file.seek(0)
                    while n := file.read():
                        _data.append(n)
                    
                    image = QtGui.QImage()
                    result = image.loadFromData(_data, extension)
                    if not result:
                        QtWidgets.QMessageBox.critical(self.listview, 'Invalid Image', f'This Is Not .{extension}')
                        return None
                    if image == None:
                        QtWidgets.QMessageBox.critical(self.listview, 'Invalid Image', 'Cannot Load This Image')
                        return None
                    
                    if image.size().height() > 720//2:
                        image = image.scaledToHeight(720//2, QtCore.Qt.TransformationMode.SmoothTransformation)
                    if image.size().width() > 1280//2:
                        image = image.scaledToWidth(1280//2, QtCore.Qt.TransformationMode.SmoothTransformation)
                    
                    dlg = QtWidgets.QDialog()
                    image_layout = QtWidgets.QHBoxLayout()
                    dlg.setLayout(image_layout)
                    image_holder = QtWidgets.QLabel()
                    image_holder.setPixmap(QtGui.QPixmap().fromImage(image))
                    image_layout.addWidget(image_holder)
                    dlg.exec()
                    
    @QtCore.pyqtSlot(QtGui.QAction)
    def on_action_trigger(self, action):
        """ Responsible for navigating between depths in the filesystems..."""
        ix = action.data()
        self.listview.setRootIndex(QtCore.QModelIndex(ix))
        self.fill_dir(QtCore.QModelIndex(ix)) # refreshing!
        self.toolbar.clear()
        ixs = []
        while  ix.isValid():
            ixs.append(ix)
            ix = ix.parent()
        for ix in reversed(ixs):
            action = self.toolbar.addAction(ix.data())
            action.setData(ix)

class FileNavigationWidget(QtWidgets.QFrame):
    """ Encapsulates the navigator into an easy to use Widget, 
        in a frame that can be mounted into a layout, easily,
        almost without any extra complexity than adding a
        label to your layout. """
    def __init__(self, setting: Setting, parent=None):
        super(FileNavigationWidget, self).__init__(parent)
        self.setting = setting
        if setting == Setting.MyFiles:
            name = "My Files"
        elif setting == Setting.SharedFiles:
            name = "Shared Files"
        elif setting == Setting.Trash:
            name = "Trash"
        self.navigation = FileNavigation(root_name=name, parent=self)
        
        layout = QtWidgets.QVBoxLayout()
        upper_layout = QtWidgets.QHBoxLayout()
        upper_layout.addWidget(self.navigation.toolbar) 
        upper_layout.setContentsMargins(0,0,0,0)
        search_bar = QtWidgets.QLineEdit()
        search_bar.setPlaceholderText('Search')
        search_bar.setFixedWidth(250)
        toggle_icon = QtWidgets.QPushButton(qta.icon('fa.navicon'),'')
        toggle_icon.setSizePolicy(QtWidgets.QSizePolicy.Policy.Fixed, QtWidgets.QSizePolicy.Policy.Fixed)
        self.icon_mode = True

        sort_button = QtWidgets.QPushButton(qta.icon('fa.sort-amount-asc'),'')
        sort_button.setSizePolicy(QtWidgets.QSizePolicy.Policy.Fixed, QtWidgets.QSizePolicy.Policy.Fixed)
        
        upper_layout.addWidget(sort_button)
        upper_layout.addWidget(toggle_icon)
        upper_layout.addWidget(search_bar)
        upper_container = QtWidgets.QWidget()
        upper_container.setLayout(upper_layout)
        layout.addWidget(upper_container)
        layout.addWidget(self.navigation.listview)
        self.setLayout(layout)

        sort_button.clicked.connect(self.sort_request)
        search_bar.textChanged.connect(self.navigation.search_items)
        toggle_icon.clicked.connect(self.toggle_icon_view)

        self.configured = False

    def sort_request(self):
        holder = QtWidgets.QWidget()
        result, __ = QtWidgets.QInputDialog.getItem(holder, 'Choose Sort Role', 'Options ', \
                                                    ['None', 'Size', 'Name'], editable=False)
        if __:
            if result == 'None':
                self.navigation.sortProxy.set(SortProxy.Type.Nothing)
            elif result == 'Size':
                self.navigation.sortProxy.set(SortProxy.Type.Size)
            elif result == 'Name':
                self.navigation.sortProxy.set(SortProxy.Type.Name)

    def toggle_icon_view(self):
        if self.icon_mode:
            self.navigation.listview.setViewMode(QtWidgets.QListView.ViewMode.ListMode) # Add toggle
        else:
            self.navigation.listview.setViewMode(QtWidgets.QListView.ViewMode.IconMode) # Add toggle
        self.icon_mode = not self.icon_mode

    def configure(self, user: Requests):
        if self.setting == Setting.MyFiles:
            self.navigation.configure_user(user, Setting.MyFiles)
        elif self.setting == Setting.SharedFiles:
            self.navigation.configure_user(user, Setting.SharedFiles)
        elif self.setting == Setting.Trash:
            self.navigation.configure_user(user, Setting.Trash)
        self.configured = True
    
    def close(self):
        if self.configured:
            self.navigation.icon_thread.stop()
