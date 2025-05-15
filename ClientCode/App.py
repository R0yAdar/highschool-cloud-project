""" This is the main App Module. It connects all of the different parts to 
    assemble the Client, Logic + GUI, the main screen is basically defined here."""

# Official
from typing import List

# Third Party 
from PyQt6 import QtCore, QtGui, QtWidgets
from email_validator import validate_email, EmailNotValidError
from password_validator import PasswordValidator
import qdarktheme
import qtawesome as qta

# Mine - UI
from SignupWidget import SignupWidget
from LoginWidget import LoginWidget
from Navbar import NavbarWidget
from UI.SlidingStackedWidget import SlidingStackedWidget

# Mine - Logic
from FileSystemViewer import FileNavigationWidget, Setting
from Utilities import wait_cursor, error_resolver, ErrorDisplay
from Requests import Requests
import RAP as RAP
from UI.Friendlist_ui import Ui_Dialog as FriendListUI
from UI.Notificationslist_ui import Ui_Dialog as NotificationUI

class FriendList(QtWidgets.QDialog, FriendListUI):
    def __init__(self, friends: List[str], parent=None) -> None:
        super(FriendList, self).__init__(parent)
        self.setupUi(self)

        for friend in friends:
            self.FriendList.addItem(QtWidgets.QListWidgetItem(friend))

class NotificationList(QtWidgets.QDialog, NotificationUI):
    def __init__(self, pending: List[str], parent=None) -> None:
        super(NotificationList, self).__init__(parent)
        self.setupUi(self)
        for friend in pending:
            self.PendingList.addItem(QtWidgets.QListWidgetItem(friend))


class MainWindow(QtWidgets.QMainWindow):
    def __init__(self, parent=None) -> None:
        super(MainWindow, self).__init__(parent)
        self.user = Requests() # User Proxy

        # GUI Settings
        # Signup
        self.cw = QtWidgets.QWidget()
        self.setCentralWidget(self.cw)
        self.main_layout = QtWidgets.QVBoxLayout()
        self.main_layout.setContentsMargins(0, 1, 0, 0)
        
        self.stackedScreen = SlidingStackedWidget()
        
        self.navbar = NavbarWidget()
        
        self.main_layout.addWidget(self.navbar)
        self.main_layout.addWidget(self.stackedScreen)

        self.cw.setLayout(self.main_layout)
        
        self.signupWidget = SignupWidget()

        self.signupWidget.email_signal.connect(self.handleSignupEmail)
        self.signupWidget.verfication_code_signal.connect(self.handleSignupVerfication)
        self.signupWidget.complete_signal.connect(self.handleSignupComplete)
        self.signupWidget.setFixedSize(465, 560)

        self.signupWidgetContainer = QtWidgets.QWidget()
        self.signupWidgetLayout = QtWidgets.QVBoxLayout()
        self.signupWidgetContainer.setLayout(self.signupWidgetLayout)
        self.signupWidgetLayout.addWidget(self.signupWidget, alignment=QtCore.Qt.AlignmentFlag.AlignCenter)

        # LoginWidget

        self.loginWidget = LoginWidget()
        self.loginWidget.auth_email_password_signal.connect(self.handleLoginAuth)
        self.loginWidget.setFixedSize(465, 560)

        self.loginWidgetContainer = QtWidgets.QWidget()
        self.loginWidgetLayout = QtWidgets.QVBoxLayout()
        self.loginWidgetContainer.setLayout(self.loginWidgetLayout)
        self.loginWidgetLayout.addWidget(self.loginWidget, alignment=QtCore.Qt.AlignmentFlag.AlignCenter)

        # FileSystems
        
        self.homeWidgetContainer = QtWidgets.QWidget()

        self.homeWidgetLayout = QtWidgets.QHBoxLayout()
        self.homeWidgetContainer.setLayout(self.homeWidgetLayout)

        self.homeFileSystem = SlidingStackedWidget(direction=QtCore.Qt.Orientation.Vertical)

        self.homeWidgetButtonsContainer = QtWidgets.QWidget()
        self.homeWidgetButtons = QtWidgets.QVBoxLayout()
        self.homeWidgetButtonsContainer.setLayout(self.homeWidgetButtons)
        
        self.homeWidgetButtons.addItem(QtWidgets.QSpacerItem(20, 37))

        self.buttonGroup = QtWidgets.QButtonGroup()
        
        self.homeMyFilesButton = QtWidgets.QPushButton("My Files")
        self.homeMyFilesButton.setCheckable(True)
        self.homeSharedFilesButton = QtWidgets.QPushButton("Shared With\n Me")
        self.homeSharedFilesButton.setCheckable(True)
        self.homeTrashButton = QtWidgets.QPushButton("Trash")
        self.homeTrashButton.setCheckable(True)
        
        self.buttonGroup.addButton(self.homeMyFilesButton)
        self.buttonGroup.addButton(self.homeSharedFilesButton)
        self.buttonGroup.addButton(self.homeTrashButton)

        self.homeMyFilesButton.setSizePolicy(QtWidgets.QSizePolicy.Policy.Minimum, QtWidgets.QSizePolicy.Policy.Expanding)
        self.homeSharedFilesButton.setSizePolicy(QtWidgets.QSizePolicy.Policy.Minimum, QtWidgets.QSizePolicy.Policy.Expanding)
        self.homeTrashButton.setSizePolicy(QtWidgets.QSizePolicy.Policy.Minimum, QtWidgets.QSizePolicy.Policy.Expanding)
        
        self.homeMyFilesButton.setFont(QtGui.QFont('arial', pointSize=14))
        self.homeSharedFilesButton.setFont(QtGui.QFont('arial', pointSize=14))
        self.homeTrashButton.setFont(QtGui.QFont('arial', pointSize=14))


        self.homeWidgetButtons.addWidget(self.homeMyFilesButton)
        self.homeWidgetButtons.addWidget(self.homeSharedFilesButton)
        self.homeWidgetButtons.addWidget(self.homeTrashButton)
        self.homeWidgetButtons.addItem(QtWidgets.QSpacerItem(20, 2))

        self.homeWidgetLayout.addWidget(self.homeWidgetButtonsContainer)
        self.homeWidgetLayout.addWidget(self.homeFileSystem)

        self.myFiles = FileNavigationWidget(Setting.MyFiles)
        self.sharedFiles = FileNavigationWidget(Setting.SharedFiles)
        self.trashFiles = FileNavigationWidget(Setting.Trash)

        self.homeFileSystem.addWidget(self.myFiles)
        self.homeFileSystem.addWidget(self.sharedFiles)
        self.homeFileSystem.addWidget(self.trashFiles)

        self.homeMyFilesButton.clicked.connect(lambda: self.homeFileSystem.slideInIdx(0))
        self.homeSharedFilesButton.clicked.connect(lambda: self.homeFileSystem.slideInIdx(1))
        self.homeTrashButton.clicked.connect(lambda: self.homeFileSystem.slideInIdx(2))

        self.homeFileSystem.setStyleSheet("""QToolTip { 
                           background-color: black; 
                           color: white; 
                           border: black solid 1px
                           }""")

        # Connect Singnals & Slots to implement logic
        self.navbar.LoginButton.clicked.connect(lambda: self.stackedScreen.slideInWgt(self.loginWidgetContainer))
        self.navbar.HomeButton.setDisabled(True)
        self.navbar.HomeButton.clicked.connect(lambda: self.stackedScreen.slideInWgt(self.homeWidgetContainer))
        self.navbar.SignupButton.clicked.connect(lambda: self.stackedScreen.slideInWgt(self.signupWidgetContainer))
        self.navbar.FullScreenButton.clicked.connect(lambda: self.showMaximized() if self.isFullScreen() else self.showFullScreen())
        
        self.is_dark = False
        self.navbar.ToggleThemeButton.clicked.connect(self.toggle_darkmode)
        self.navbar.setStyleSheet("border-radius: 0px;")        
        
        # Finish Settings and Initing.
        self.InitTools()
        
        self.stackedScreen.addWidget(self.loginWidgetContainer)
        self.stackedScreen.addWidget(self.signupWidgetContainer)
        self.stackedScreen.addWidget(self.homeWidgetContainer)

        self.stackedScreen.setCurrentWidget(self.loginWidgetContainer)

        self.navbar.FriendsButton.clicked.connect(self.handle_friends_dialog)
        self.navbar.NotificationButton.clicked.connect(self.handle_friend_requests)
        self.navbar.NotificationButton.setDisabled(True)
        self.navbar.FriendsButton.setDisabled(True)

        self.homeMyFilesButton.click()

    @QtCore.pyqtSlot()
    def handle_friends_dialog(self):
        dialog = FriendList(self.user.GetFriendList().list.users)
        dialog.setWindowTitle('Friends')
        
        def handle_sending():
            email, _ = QtWidgets.QInputDialog.getText(dialog, "Enter Friend's Email", 'Email: ')
            if _:
                self.user.SendFriendRequest(email)
        
        def handle_removing():
            choices = dialog.FriendList.selectedItems()
            if len(choices) != 1:
                return
            choice = choices[0]
            email = choice.text()
            if self.user.RemoveFriend(email).status == RAP.BasicResponseSTATUS.OK:
                dialog.FriendList.takeItem(dialog.FriendList.row(choice))

        dialog.SendButton.clicked.connect(handle_sending)
        dialog.RemoveButton.clicked.connect(handle_removing)
        dialog.exec()

    @QtCore.pyqtSlot()
    def handle_friend_requests(self):
        dialog = NotificationList(self.user.GetPendingList().list.users)
        dialog.setWindowTitle('Notifications')

        def handle_accept():
            choices = dialog.PendingList.selectedItems()
            if len(choices) != 1:
                return
            choice = choices[0]
            email = choice.text()
            if self.user.AcceptFriendRequest(email).status == RAP.BasicResponseSTATUS.OK:
                dialog.PendingList.takeItem(dialog.PendingList.row(choice))
        
        def handle_reject():
            choices = dialog.PendingList.selectedItems()
            if len(choices) != 1:
                return
            choice = choices[0]
            email = choice.text()
            if self.user.RejectFriendRequest(email).status == RAP.BasicResponseSTATUS.OK:
                dialog.PendingList.takeItem(dialog.PendingList.row(choice))

        dialog.AcceptButton.clicked.connect(handle_accept)
        dialog.RejectButton.clicked.connect(handle_reject)
        dialog.exec()

    def toggle_darkmode(self):
        self.is_dark = not self.is_dark
        if self.is_dark:
            qdarktheme.setup_theme('dark')
        else:
             qdarktheme.setup_theme('light')
    
    def InitTools(self) -> None:
        self.passValidator = PasswordValidator()
        self.passValidator.min(8)
        self.passValidator.has().uppercase()
        self.passValidator.has().lowercase()
        self.passValidator.has().digits()
        self.passValidator.has().no().spaces()

    @QtCore.pyqtSlot(ErrorDisplay)
    def error(self, error: ErrorDisplay):
        QtWidgets.QMessageBox.critical(self, error.title, error.information)

    @QtCore.pyqtSlot(tuple)
    def handleSignupComplete(self, info):
        email, password, code = info
        if(self.passValidator.validate(password)):
            with error_resolver(self.error):
                with wait_cursor():
                    res = self.user.SignupFull(email, password, code)
                if res.status == RAP.BasicResponseSTATUS.FAILED:
                    self.signupWidget.reset()
                    return QtWidgets.QMessageBox.critical(self, "Signup Failed", "This Email Is Already Assigned")
                
                elif res.status ==  RAP.BasicResponseSTATUS.OK:
                    self.signupWidget.nextPage()
                # GUI
                self.navbar.HomeButton.setDisabled(False)
                self.navbar.SignupButton.setDisabled(True)
                self.navbar.LoginButton.setDisabled(True)
                self.navbar.NotificationButton.setDisabled(False)
                self.navbar.FriendsButton.setDisabled(False)
                self.stackedScreen.slideInWgt(self.homeWidgetContainer)
                # logic
                self.myFiles.configure(self.user)
                self.sharedFiles.configure(self.user)
                self.trashFiles.configure(self.user)
        else:
            self.signupWidget.alert("See The Requirements")

    @QtCore.pyqtSlot(str)
    def handleSignupVerfication(self, code):
        with wait_cursor():
            with error_resolver(self.error):
                res: RAP.BasicResponse = self.user.SignupVerifyCode(self.email, code)
            if res.status == RAP.BasicResponseSTATUS.FAILED:
                self.signupWidget.alert("Wrong Code")
            elif res.status ==  RAP.BasicResponseSTATUS.OK:
                self.signupWidget.nextPage()

    @QtCore.pyqtSlot(str)
    def handleSignupEmail(self, email):
        print(email)
        try:
            validation = validate_email(email, check_deliverability=False)
            self.email = validation.email
            with wait_cursor():
                with error_resolver(self.error):
                    self.user.SignupSendCode(self.email)                        
                    self.signupWidget.nextPage()
        except EmailNotValidError as e:
            self.signupWidget.alert(str(e))

    @QtCore.pyqtSlot(tuple)
    def handleLoginAuth(self, info: tuple) -> None:
        email, password = info
        try:
            validation = validate_email(email, check_deliverability=False)
            self.email = validation.email
        except EmailNotValidError as e:
            return self.loginWidget.alert(str(e))

        if(self.passValidator.validate(password)):
            with wait_cursor():
                with error_resolver(self.error):
                    succ, code = self.user.Login(RAP.Login(email, password)) #zaqWSX123#
                    if succ:
                        self.stackedScreen.slideInWgt(self.homeWidgetContainer)
                        self.navbar.HomeButton.setDisabled(False)
                        self.navbar.LoginButton.setDisabled(True)
                        self.navbar.SignupButton.setDisabled(True)
                        self.navbar.NotificationButton.setDisabled(False)
                        self.navbar.FriendsButton.setDisabled(False)
                        self.myFiles.configure(self.user)
                        self.sharedFiles.configure(self.user)
                        self.trashFiles.configure(self.user)
                        return print(self.email, password)
        self.loginWidget.alert("Try Again")

    def closeEvent(self, event) -> None:
        dlg = QtWidgets.QMessageBox(self)
        dlg.setWindowTitle("Close App")
        dlg.setText("You are about to close the app.")
        dlg.setStandardButtons(QtWidgets.QMessageBox.StandardButton.Yes | QtWidgets.QMessageBox.StandardButton.No)
        dlg.setIcon(QtWidgets.QMessageBox.Icon.Question)
        result = dlg.exec()

        self.myFiles.close()
        self.sharedFiles.close()
        self.trashFiles.close()

        if result == QtWidgets.QMessageBox.StandardButton.Yes:
            self.user.close()
            event.accept()
     
        else:
            event.ignore()

if __name__ == '__main__':
    import sys
    import ctypes
    from IconGenerator import icon_manager

    myappid = 'mycompany.myproduct.subproduct.version' # arbitrary string
    ctypes.windll.shell32.SetCurrentProcessExplicitAppUserModelID(myappid)

    app = QtWidgets.QApplication(sys.argv)
    qdarktheme.setup_theme('auto')    #app.setStyle('Fusion')
    icon_manager.init()
    
    app.setApplicationName("Cloud Storage & Streaming")
    app.setWindowIcon(qta.icon('ei.soundcloud'))
    
    Form = MainWindow()
    Form.show()
    sys.exit(app.exec())