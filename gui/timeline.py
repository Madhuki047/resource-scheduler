from PyQt5.QtWidgets import QWidget
from PyQt5.QtGui import QPainter, QColor, QPen, QFont
from PyQt5.QtCore import Qt

from src.algorithms.scheduler import DAY_START_HOUR, DAY_END_HOUR   # you already have these
from src.algorithms.scheduler import BookingScheduler   # only if you need the type hint


class DayTimelineWidget(QWidget):
    """
    Simple visual timeline for one day:
    - X axis: hours (DAY_START_HOUR..DAY_END_HOUR)
    - Y axis: one row per room
    - Coloured blocks for each booking.
    """

    def __init__(self, scheduler, booking_date, parent=None):
        super().__init__(parent)
        self.scheduler = scheduler
        self.booking_date = booking_date
        self.setMinimumHeight(260)
        self.room_colors = {
            "Meeting Room A": QColor("#e74c3c"),
            "Meeting Room B": QColor("#3498db"),
            "Meeting Room C": QColor("#2ecc71"),
            "Meeting Room D": QColor("#f39c12"),
            "Meeting Room E": QColor("#9b59b6"),
        }

    def set_day(self, booking_date):
        """Change day and redraw."""
        self.booking_date = booking_date
        self.update()

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing)

        w = self.width()
        h = self.height()

        left_margin = 180
        right_margin = 50
        top_margin = 20
        bottom_margin = 40

        # Background
        painter.fillRect(self.rect(), QColor("#f5f7fb"))

        day_len = DAY_END_HOUR - DAY_START_HOUR
        if day_len <= 0:
            return

        # Rooms and vertical spacing
        rooms = self.scheduler.rooms
        n_rooms = len(rooms)
        if n_rooms == 0:
            return

        usable_height = h - top_margin - bottom_margin
        row_height = usable_height / n_rooms

        # Time grid (every 2 hours)
        painter.setPen(QPen(QColor("#d0d3da"), 1, Qt.DashLine))
        for half in range(0, (DAY_END_HOUR - DAY_START_HOUR) * 2 + 1):
            hour = DAY_START_HOUR + half * 0.5
            x = left_margin + (hour - DAY_START_HOUR) / day_len * (w - left_margin - right_margin)

            painter.drawLine(int(x), top_margin, int(x), h - bottom_margin)

            painter.setPen(QPen(QColor("#555"), 1))
            painter.setFont(QFont("Segoe UI", 8))

            # Label only full hours
            if hour.is_integer():
                painter.drawText(int(x - 12), int(h - bottom_margin + 15), f"{hour}:00")

            painter.setPen(QPen(QColor("#d0d3da"), 1, Qt.DashLine))

        # Draw each room row
        for i, room in enumerate(rooms):
            y_center = top_margin + i * row_height + row_height / 2

            # Room label
            painter.setPen(QPen(QColor("#555"), 1))
            painter.setFont(QFont("Segoe UI", 9, QFont.Bold))
            painter.drawText(10, int(y_center + 4), room)

            # Horizontal baseline
            painter.setPen(QPen(QColor("#e0e3eb"), 2))
            painter.drawLine(left_margin, int(y_center), w - right_margin, int(y_center))

            # Bookings for this room on this day
            bookings = self.scheduler.get_bookings_for_room_on_day(room, self.booking_date)
            color = self.room_colors.get(room, QColor("#95a5a6"))

            for b in bookings:
                start = max(b.start_hour, DAY_START_HOUR)
                end = min(b.end_hour, DAY_END_HOUR)
                if start >= end:
                    continue

                x1 = left_margin + (start - DAY_START_HOUR) / day_len * (w - left_margin - right_margin)
                x2 = left_margin + (end - DAY_START_HOUR) / day_len * (w - left_margin - right_margin)

                rect_height = row_height * 0.5
                y_top = y_center - rect_height / 2

                painter.setPen(Qt.NoPen)
                painter.setBrush(color)
                painter.drawRoundedRect(int(x1), int(y_top), int(x2 - x1), int(rect_height), 6, 6)

                # Booking name (if there is space)
                painter.setPen(Qt.white)
                painter.setFont(QFont("Segoe UI", 8, QFont.Bold))
                if x2 - x1 > 40:
                    painter.drawText(int(x1 + 4), int(y_center + 3), b.name)

        painter.end()

    def mousePressEvent(self, event):
        x = event.x()
        w = self.width()
        left_margin = 80
        right_margin = 20

        # Ignore clicks outside the timeline area
        if x < left_margin or x > w - right_margin:
            return

        # Convert x → hour
        day_len = DAY_END_HOUR - DAY_START_HOUR
        fraction = (x - left_margin) / (w - left_margin - right_margin)
        hour_float = DAY_START_HOUR + fraction * day_len

        # Snap to nearest 30 minutes
        snapped = round(hour_float * 2) / 2

        # Emit signal to parent dialog
        if hasattr(self.parent(), "on_timeline_clicked"):
            self.parent().on_timeline_clicked(snapped)