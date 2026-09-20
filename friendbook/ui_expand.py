"""Height animation for the management toolbar; the containing layout moves the list."""
from PySide6.QtCore import Qt, QEasingCurve, QVariantAnimation
from PySide6.QtWidgets import QSizePolicy, QWidget
from .ui_motion import motion_enabled


class AnimatedExpansion(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.expanded = False
        self.setAttribute(Qt.WidgetAttribute.WA_StyledBackground)
        self.setSizePolicy(QSizePolicy.Policy.Preferred, QSizePolicy.Policy.Fixed)
        self.animation = QVariantAnimation(self)
        self.animation.setDuration(260)
        self.animation.setEasingCurve(QEasingCurve.Type.OutCubic)
        self.animation.valueChanged.connect(lambda value: self.setMaximumHeight(round(value)))
        self.animation.finished.connect(self.finish_motion)
        self.setMaximumHeight(0)
        self.hide()

    def set_expanded(self, expanded):
        changed = self.expanded != expanded
        self.expanded = expanded
        self.animation.stop()
        if not changed or not motion_enabled(self) or not self.window().isVisible():
            self.finish_motion()
            return
        start = self.height() if self.isVisible() else 0
        self.show()
        self.setMaximumHeight(start)
        self.animation.setStartValue(float(start))
        self.animation.setEndValue(float(self.sizeHint().height() if expanded else 0))
        self.animation.start()

    def finish_motion(self):
        self.animation.stop()
        self.setMaximumHeight(16777215 if self.expanded else 0)
        self.setVisible(self.expanded)
