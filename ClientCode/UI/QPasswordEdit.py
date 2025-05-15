import sys
import qtawesome as qta # type: ignore
from PyQt6.QtWidgets import (QApplication, QLineEdit)
from PyQt6.QtGui import QIcon, QAction, QFont, QPalette
from PyQt6.QtCore import QSize
class QPasswordEdit(QLineEdit):
    def __init__(self, parent=None):
        super(QPasswordEdit, self).__init__(parent)

        # Create the eye action and set the icon
        self.open_eye_icon = qta.icon('ei.eye-open')
        self.closed_eye_icon = qta.icon('ei.eye-close')
        self.eye_action = QAction(self.closed_eye_icon, '', self)
        self.eye_action.triggered.connect(self.toggle_password_visibility)
        #self.eye_action.setCheckable(True)
        self.addAction(self.eye_action, QLineEdit.ActionPosition.TrailingPosition)
        # Set the initial state to password masking
        self.setEchoMode(QLineEdit.EchoMode.Password)

    def toggle_password_visibility(self): #checked
        if self.echoMode() == QLineEdit.EchoMode.Password:
            self.setEchoMode(QLineEdit.EchoMode.Normal)
            self.eye_action.setIcon(self.open_eye_icon)
        else:
            self.setEchoMode(QLineEdit.EchoMode.Password)
            self.eye_action.setIcon(self.closed_eye_icon)

if __name__ == '__main__':
    app = QApplication(sys.argv)
    app.setStyle('Fusion')
    password_edit = QPasswordEdit()
    password_edit.setMaxLength(20)
    password_edit.resize(QSize(30,30))
    password_edit.setFont(QFont('Times', 20))
    password_edit.show()
    sys.exit(app.exec())
