""" Adds basic Logic to the UI of this componenet, intrdouces use of
    user: Requests = Client API to communicate with the server."""

# Official
from datetime import datetime

# 3rd Party
from PyQt6.QtWidgets import QApplication, QWidget, QListWidgetItem, QInputDialog
from PyQt6.QtCore import pyqtSignal
import qtawesome as qta

# Mine
from UI.Properties_ui import Ui_Form as UI
from RAP import ExtendedFileInfo, FileInfo, BasicResponseSTATUS
from Utilities import ErrorDisplay, error_resolver
from IconGenerator import icon_manager
from Requests import Requests
from Utilities import get_lowercase_extension, convert_size

class PropertiesWidget(QWidget, UI):
    error = pyqtSignal(ErrorDisplay)
    finished = pyqtSignal()
    def __init__(self, data: ExtendedFileInfo, user: Requests,parent=None) -> None:
        super(PropertiesWidget, self).__init__(parent)
        self.setupUi(self)
        self.data = data
        self.user = user

        is_folder =  data.short_info.size == 0
        if is_folder:
            extension = "Folder"
        else:            
            extension = get_lowercase_extension(data.short_info.display_name)

        self.setWindowIcon(icon_manager.get(extension))
        self.setWindowTitle(data.short_info.display_name)
        
        self.nameEdit.setText(data.short_info.display_name)
        self.typeLabel.setText('.' + extension)
        
        if is_folder:
            self.sizeLabel.setText("Doesn't Support Size For Folders")
            self.uploadLabel.setText("Doesn't Support Date For Folders")
        else:
            self.sizeLabel.setText(convert_size(data.short_info.size))
            self.uploadLabel.setText(datetime.fromtimestamp(data.unix_time).isoformat())

        self.ownerLabel.setText(data.owner)

        for friend in data.shared_list:
            self.friendList.addItem(QListWidgetItem(friend))

        self.nameEdit.returnPressed.connect(self.buttonBox.accepted)
        self.buttonBox.accepted.connect(self.graceful_exist)
        self.buttonBox.rejected.connect(self.exist)
        self.friendButton.clicked.connect(self.add_a_friend)
        self.removeButton.clicked.connect(self.remove_a_friend)
        self.tabWidget.setCurrentIndex(0)

    def remove_a_friend(self):
        choices = self.friendList.selectedItems()
        if len(choices) != 1:
            return
        choice = choices[0]
        email = choice.text()
        if self.user.UnshareNode(self.data.short_info.id, email).status == BasicResponseSTATUS.OK:
            self.friendList.takeItem(self.friendList.row(choice))

    def add_a_friend(self):
        holder = QWidget()
        holder.setWindowTitle('Choose Friend Name')
        holder.setWindowIcon(qta.icon('fa5s.user-friends'))
        
        response = self.user.GetFriendList()

        if response.status.status == BasicResponseSTATUS.FAILED: return
        result, __ = QInputDialog.getItem(holder, 'Choose Friend Name', 'Friends: ', response.list.users, editable=False)
        if __:
            if self.user.ShareNode(self.data.short_info.id, result).status == BasicResponseSTATUS.OK:
                self.friendList.addItem(QListWidgetItem(result))

    def graceful_exist(self):
        if self.nameEdit.text() != self.data.short_info.display_name:
            with error_resolver(self.error.emit):
                self.user.RenameNode(self.data.short_info.id, self.nameEdit.text())
        self.exist()
    
    def exist(self):
        self.finished.emit()
        self.close()
