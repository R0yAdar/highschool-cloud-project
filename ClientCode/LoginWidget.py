""" Adds basic Logic to the UI of this componenet"""
from PyQt6 import QtCore, QtGui, QtWidgets
from UI.LoginWidget_ui import Ui_Form as UI

class LoginWidget(QtWidgets.QWidget, UI):
    auth_email_password_signal = QtCore.pyqtSignal(tuple)

    def __init__(self, parent=None) -> None:
        super(LoginWidget, self).__init__(parent)
        self.setupUi(self)
        self.alertLabel.setWordWrap(True)
        self.emailEdit.setMaxLength(100)

        self.emailEdit.returnPressed.connect(lambda: self.confirmButton.click())
        self.passwordEdit.returnPressed.connect(lambda: self.confirmButton.click())

        self.confirmButton.clicked.connect(lambda: self.auth_email_password_signal.emit((self.emailEdit.text(), self.passwordEdit.text())))
    
    def alert(self, text: str):
        self.alertLabel.setText(text)
   