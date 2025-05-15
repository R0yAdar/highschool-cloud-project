""" Sets up the NavBar componenet..."""
# 3rd Party
from PyQt6.QtWidgets import QApplication, QWidget
from PyQt6.QtCore import QSize, Qt
import qtawesome as qta

# Mine
from UI.Navbar_ui import Ui_Form as UI


class NavbarWidget(QWidget, UI):
    def __init__(self, parent=None) -> None:
        super(NavbarWidget, self).__init__(parent)
        self.setupUi(self)
        self.icon_label = qta.IconWidget()
        self.icon_label.setIconSize(QSize(64, 64))
        self.icon_label.setIcon(qta.icon('ei.soundcloud'))
        self.ToggleThemeButton.setText('')
        self.ToggleThemeButton.setIcon(qta.icon('mdi6.theme-light-dark'))
        self.ToggleThemeButton.setIconSize(QSize(40, 50))
        self.ToggleThemeButton.setContentsMargins(0,0,0,0)
        
        self.FriendsButton.setText('')
        self.FriendsButton.setIcon(qta.icon('ph.users-three-fill', color=('blue', 180), color_active='blue'))
        self.FriendsButton.setIconSize(QSize(40, 50))
        self.FriendsButton.setContentsMargins(0,0,0,0)
        self.FriendsButton.setCursor(Qt.CursorShape.PointingHandCursor)

        self.NotificationButton.setText('')
        self.NotificationButton.setIcon(qta.icon('ph.notification-bold', color=('blue', 180), color_active='blue'))
        self.NotificationButton.setIconSize(QSize(40, 50))
        self.NotificationButton.setContentsMargins(0,0,0,0)
        self.NotificationButton.setCursor(Qt.CursorShape.PointingHandCursor)


        self.horizontalLayout.insertWidget(len(self.horizontalLayout) - 1, self.icon_label)
        