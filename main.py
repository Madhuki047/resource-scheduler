import sys
from PyQt5.QtWidgets import QApplication

from gui.window import MainWindow
from src.algorithms.scheduler import BookingScheduler


def main():
    app = QApplication(sys.argv)

    # Make all fonts a bit bigger
    font = app.font()
    font.setPointSize(font.pointSize() + 2)   # +1 or +2 as you like
    app.setFont(font)

    scheduler = BookingScheduler()
    window = MainWindow(scheduler)
    window.show()

    sys.exit(app.exec_())

if __name__ == "__main__":
    main()