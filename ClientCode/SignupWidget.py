from PyQt6 import QtCore, QtGui, QtWidgets
from UI.SignupWidget_ui import Ui_Form as UI

class SignupWidget(QtWidgets.QWidget, UI):
    email_signal = QtCore.pyqtSignal(str)
    verfication_code_signal = QtCore.pyqtSignal(str)
    complete_signal = QtCore.pyqtSignal(tuple)

    def __init__(self, parent=None) -> None:
        super(SignupWidget, self).__init__(parent)
        self.setupUi(self)
        self.alertLabel.setWordWrap(True)
        self.emailEdit.setMaxLength(100)

        self.emailEdit.returnPressed.connect(lambda: self.emailButton.click())
        self.verificationEdit.returnPressed.connect(lambda: self.verificationButton.click())
        self.passwordEdit.returnPressed.connect(lambda: self.passwordButton.click())


        self.emailButton.clicked.connect(lambda: self.email_signal.emit(self.emailEdit.text()))
        self.verificationButton.clicked.connect(lambda: self.verfication_code_signal.emit(self.verificationEdit.text()))
        self.passwordButton.clicked.connect(lambda: self.complete_signal.emit((self.emailEdit.text(),
                                                                               self.passwordEdit.text(),
                                                                               self.verificationEdit.text())))

    def nextPage(self):
        self.alert("")
        self.stackedWidget.slideInNext()
    
    def alert(self, text: str):
        self.alertLabel.setText(text)
    
    def reset(self):
        self.stackedWidget.setCurrentIndex(0)
        for inputEdit in [self.emailEdit, self.verificationEdit, self.passwordEdit]: 
            inputEdit.clear()
        self.alert("")
