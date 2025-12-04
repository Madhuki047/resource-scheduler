from calendar import month_name
from datetime import date
import os

from PyQt5.QtCore import Qt, pyqtSignal, QTimer
from PyQt5.QtGui import QPainter, QPen, QFont, QColor, QPixmap
from PyQt5.QtWidgets import (
    QMainWindow,
    QWidget,
    QTabWidget,
    QTableWidget,
    QTableWidgetItem,
    QHBoxLayout,
    QVBoxLayout,
    QLabel,
    QPushButton,
    QGridLayout,
    QComboBox,
    QDateEdit,
    QGroupBox,
    QDialog,
    QLineEdit,
    QSpinBox,
    QListWidget,
    QListWidgetItem,
    QRadioButton,
    QMessageBox,
    QProgressBar,
    QFrame,
)

from src.algorithms.scheduler import BookingScheduler
from matplotlib.backends.backend_qt5agg import FigureCanvasQTAgg as FigureCanvas
from matplotlib.figure import Figure

from src.utils.benchmark import benchmark_searches, compare_search_algorithms

from src.models.booking import Booking

from gui.timeline import DayTimelineWidget



class CircularGauge(QWidget):
    # Circular percentage gauge with smooth animation and colour thresholds.

    def __init__(self, diameter: int = 140, parent=None):
        super().__init__(parent)
        self._value = 0           # current animated value (0–100)
        self._target = 0          # where we want to go
        self._diameter = diameter

        self.setMinimumSize(diameter, diameter)
        self.setMaximumSize(diameter, diameter)

        # timer to drive smooth animation (~60fps)
        self._timer = QTimer(self)
        self._timer.setInterval(16)  # ~16 ms
        self._timer.timeout.connect(self._animate_step)

    # ---- public API ----

    def setValue(self, value: int):
        """Set instantly without animation (used at startup)."""
        self._value = max(0, min(100, int(value)))
        self._target = self._value
        self.update()

    def animate_to(self, value: int):
        """Animate smoothly from current value to new value."""
        self._target = max(0, min(100, int(value)))
        if not self._timer.isActive():
            self._timer.start()

    # ---- animation step ----

    def _animate_step(self):
        if self._value == self._target:
            self._timer.stop()
            return

        step = 2  # change per frame; smaller = smoother/slower
        if abs(self._target - self._value) <= step:
            self._value = self._target
        else:
            self._value += step if self._target > self._value else -step

        self.update()

    # ---- painting ----

    def paintEvent(self, event):
        side = min(self.width(), self.height())

        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing)

        painter.translate(self.width() / 2, self.height() / 2)
        painter.scale(side / 200.0, side / 200.0)  # normalise to 200x200

        # background circle
        pen_bg = QPen(QColor("#e0e4ea"), 14)
        painter.setPen(pen_bg)
        painter.drawEllipse(-80, -80, 160, 160)

        # choose colour based on utilisation
        if self._value < 60:
            arc_color = QColor("#27ae60")   # green
        elif self._value < 80:
            arc_color = QColor("#f39c12")   # orange
        else:
            arc_color = QColor("#e74c3c")   # red

        # foreground arc
        span_angle = int(-360 * self._value / 100)  # negative = clockwise
        pen_fg = QPen(arc_color, 14)
        painter.setPen(pen_fg)
        painter.drawArc(-80, -80, 160, 160, 90 * 16, span_angle * 16)

        # percentage text
        painter.setPen(QColor("#2c3e50"))
        font = QFont()
        font.setPointSize(18)
        font.setBold(True)
        painter.setFont(font)
        painter.drawText(-60, -10, 120, 40, Qt.AlignCenter, f"{self._value}%")

        # subtitle
        font_small = QFont()
        font_small.setPointSize(9)
        painter.setFont(font_small)
        painter.drawText(-60, 25, 120, 30, Qt.AlignCenter, "today utilised")



class DayCell(QWidget):
    dayClicked = pyqtSignal(int)

    def __init__(self, day: int, utilisation: int, parent=None):
        super().__init__(parent)
        self.day = day

        layout = QVBoxLayout()
        layout.setContentsMargins(6, 6, 6, 6)
        layout.setSpacing(4)
        self.setLayout(layout)

        self.day_label = QLabel(str(day))
        self.day_label.setAlignment(Qt.AlignLeft | Qt.AlignVCenter)
        self.day_label.setStyleSheet("font-weight: 600; color: #34495e;")
        layout.addWidget(self.day_label)

        self.bar = QProgressBar()
        self.bar.setRange(0, 100)
        self.bar.setTextVisible(True)  # 🔹 show text
        self.bar.setFormat("%p%")
        self.bar.setAlignment(Qt.AlignCenter)  # 🔹 center it
        self.bar.setFixedHeight(15)  # a little taller so text fits
        self.bar.setStyleSheet("""
            QProgressBar {
                background-color: #ecf0f1;
                border-radius: 6px;
                padding: 0px 2px;
                font-size: 10px;
                color: #2c3e50;
            }
            QProgressBar::chunk {
                border-radius: 6px;
            }
        """)
        layout.addWidget(self.bar)

        # make it feel like a button tile
        self.setMinimumSize(80, 60)
        self.setCursor(Qt.PointingHandCursor)
        self.setStyleSheet("""
            DayCell {
                background-color: rgba(255, 255, 255, 0.95);
                border-radius: 10px;
                border: 1px solid #e1e5ee;
            }
        """)

        self.set_utilisation(utilisation)

    def set_utilisation(self, value: int):
        self.bar.setValue(value)

        if value < 60:
            color = "#27ae60"
        elif value < 80:
            color = "#f39c12"
        else:
            color = "#e74c3c"

        self.bar.setStyleSheet(f"""
            QProgressBar {{
                background-color: #ecf0f1;
                border-radius: 6px;
                padding: 0px 2px;
                font-size: 10px;
                color: #2c3e50;
            }}
            QProgressBar::chunk {{
                border-radius: 6px;
                background-color: {color};
            }}
        """)

    def mousePressEvent(self, event):
        self.dayClicked.emit(self.day)
        super().mousePressEvent(event)



class MplCanvas(FigureCanvas):
    def __init__(self, parent=None):
        fig = Figure(figsize=(4, 3), tight_layout=True)
        self.ax = fig.add_subplot(111)
        super().__init__(fig)
        self.setParent(parent)


class AlgorithmComparisonTab(QWidget):
    def __init__(self, scheduler: BookingScheduler, parent=None):
        super().__init__(parent)
        self.scheduler = scheduler

        # === MAIN LAYOUT ======================================================
        layout = QVBoxLayout()
        layout.setContentsMargins(16, 16, 16, 16)
        layout.setSpacing(12)
        self.setLayout(layout)

        # ======================================================================
        #                        THEORETICAL COMPLEXITY
        # ======================================================================
        theory_box = QGroupBox("Theoretical Complexity")
        t_layout = QGridLayout()
        theory_box.setLayout(t_layout)

        # Headers
        t_layout.addWidget(QLabel("<b>Algorithm</b>"), 0, 0)
        t_layout.addWidget(QLabel("<b>Time (worst)</b>"), 0, 1)
        t_layout.addWidget(QLabel("<b>Time (best)</b>"), 0, 2)
        t_layout.addWidget(QLabel("<b>Space</b>"), 0, 3)

        # Linear row
        t_layout.addWidget(QLabel("Linear search"), 1, 0)
        t_layout.addWidget(QLabel("O(n)"), 1, 1)
        t_layout.addWidget(QLabel("O(1)"), 1, 2)
        t_layout.addWidget(QLabel("O(1)"), 1, 3)

        # Binary row
        t_layout.addWidget(QLabel("Binary search"), 2, 0)
        t_layout.addWidget(QLabel("O(log n)"), 2, 1)
        t_layout.addWidget(QLabel("O(1)"), 2, 2)
        t_layout.addWidget(QLabel("O(1)"), 2, 3)

        layout.addWidget(theory_box)

        # ======================================================================
        #                     GRAPHS + HISTORY (TWO-COLUMN LAYOUT)
        # ======================================================================
        middle = QHBoxLayout()
        middle.setSpacing(16)
        layout.addLayout(middle)

        # LEFT COLUMN → 3 GRAPHS + BUTTONS
        left = QVBoxLayout()
        middle.addLayout(left, stretch=2)

        # ----------------------------------------------------------------------
        # 1) Synthetic benchmark graph (n = 10,000)
        bench_title = QLabel("Synthetic benchmark (n = 10,000)")
        bench_title.setStyleSheet("font-size: 14px; font-weight: 600;")
        left.addWidget(bench_title)

        self.bench_canvas = MplCanvas(self)
        self.bench_canvas.setMinimumHeight(140)
        left.addWidget(self.bench_canvas, stretch=1)

        # ----------------------------------------------------------------------
        # 2) Growth curve graph
        growth_title = QLabel("Growth curve (Linear vs Binary as n grows)")
        growth_title.setStyleSheet("font-size: 14px; font-weight: 600;")
        left.addWidget(growth_title)

        self.growth_canvas = MplCanvas(self)
        self.growth_canvas.setMinimumHeight(140)
        left.addWidget(self.growth_canvas, stretch=1)

        # ----------------------------------------------------------------------
        # 3) Real search history graph
        hist_graph_title = QLabel("Search cost per action in this system")
        hist_graph_title.setStyleSheet("font-size: 14px; font-weight: 600;")
        left.addWidget(hist_graph_title)

        self.history_canvas = MplCanvas(self)
        self.history_canvas.setMinimumHeight(140)
        left.addWidget(self.history_canvas, stretch=1)

        # ----------------------------------------------------------------------
        # Buttons under graphs
        self.run_btn = QPushButton("Re-run synthetic benchmark")
        self.run_btn.clicked.connect(self.run_benchmark)
        left.addWidget(self.run_btn, alignment=Qt.AlignLeft)

        self.demo_btn = QPushButton("Play live demo")
        self.demo_btn.clicked.connect(self.start_demo)
        left.addWidget(self.demo_btn, alignment=Qt.AlignLeft)

        # ----------------------------------------------------------------------
        # Demo animation state
        self.demo_timer = QTimer(self)
        self.demo_timer.setInterval(300)   # frame every 300ms
        self.demo_timer.timeout.connect(self._demo_step)
        self.demo_index = 0
        self.demo_history = []

        # Result/explanation label under graphs
        self.result_label = QLabel("")
        self.result_label.setStyleSheet("color: #555;")
        left.addWidget(self.result_label)

        # ======================================================================
        #                             RIGHT COLUMN
        # ======================================================================
        right = QVBoxLayout()
        middle.addLayout(right, stretch=1)

        hist_title = QLabel("Recent search runs in this system")
        hist_title.setStyleSheet("font-size: 14px; font-weight: 600;")
        right.addWidget(hist_title)

        # Table for per-action stats
        self.history_table = QTableWidget()
        self.history_table.setColumnCount(5)
        self.history_table.setHorizontalHeaderLabels(
            ["Time", "Operation", "n", "Linear Comps", "Binary Comps"]
        )
        self.history_table.horizontalHeader().setStretchLastSection(True)
        right.addWidget(self.history_table, stretch=1)

        # Stats summary label
        self.stats_label = QLabel("")
        self.stats_label.setStyleSheet("color: #555;")
        right.addWidget(self.stats_label)

        # Spacer
        layout.setStretch(0, 0)
        layout.setStretch(1, 1)

        # Load initial content
        self.refresh_history()
        self.run_benchmark()
        self.show_growth_curve()

    def start_demo(self):
        """Start replaying the real search history as an animation."""
        history = self.scheduler.search_history
        if not history:
            self.result_label.setText("Run a few bookings / checks first, then try again.")
            return

        # We animate from oldest to newest
        self.demo_history = list(history)
        self.demo_index = 0
        self.demo_timer.start()
        self.result_label.setText("Playing live demo of past search runs...")

    def _demo_step(self):
        if self.demo_index >= len(self.demo_history):
            self.demo_timer.stop()
            self.result_label.setText("Demo finished. New actions will continue updating the graphs.")
            return

        # Take slice up to current index
        partial = self.demo_history[: self.demo_index + 1]

        # 1) animate history line chart
        self.plot_history_chart(partial)

        # 2) optionally, animate growth curve using real n vs time
        ns = [h["n"] for h in partial]
        lin_times = [h["linear_time_ms"] for h in partial]
        bin_times = [h["binary_time_ms"] for h in partial]

        ax = self.growth_canvas.ax
        ax.clear()
        ax.plot(ns, lin_times, marker="o", label="Linear")
        ax.plot(ns, bin_times, marker="o", label="Binary")
        ax.set_xlabel("n (size of list in that action)")
        ax.set_ylabel("Time (ms)")
        ax.set_title("Real running time vs n (replayed)")
        ax.legend()
        self.growth_canvas.draw()

        # 3) optionally, animate benchmark bars from 0 up to average comparisons
        lin_avg = sum(h["linear_comparisons"] for h in partial) / len(partial)
        bin_avg = sum(h["binary_comparisons"] for h in partial) / len(partial)

        axb = self.bench_canvas.ax
        axb.clear()
        labels = ["Linear", "Binary"]
        bars = axb.bar(labels, [lin_avg, bin_avg])
        bars[0].set_color("#e74c3c")
        bars[1].set_color("#3498db")
        axb.set_ylabel("Avg comparisons in demo so far")
        axb.set_title("Live demo benchmark (from real actions)")
        self.bench_canvas.draw()

        self.demo_index += 1

    def run_benchmark(self):
        results = benchmark_searches(10000)

        ax = self.bench_canvas.ax
        ax.clear()

        labels = ["Linear", "Binary"]
        comparisons = [
            results["linear_comparisons"],
            results["binary_comparisons"],
        ]

        bars = ax.bar(labels, comparisons)
        bars[0].set_color("#e74c3c")
        bars[1].set_color("#3498db")

        ax.set_ylabel("Number of comparisons")
        ax.set_title("Comparison count for n = 10,000 (worst-case)")
        self.bench_canvas.draw()

        self.result_label.setText(
            f"Linear: {results['linear_comparisons']} comparisons, "
            f"{results['linear_time_ms']:.3f} ms\n"
            f"Binary: {results['binary_comparisons']} comparisons, "
            f"{results['binary_time_ms']:.3f} ms\n"
            "Both algorithms use O(1) extra space."
        )

    def plot_history_chart(self, history=None):
        """
        Draw a line chart from real search runs:
        x = action number, y = comparisons (linear vs binary).
        """
        if history is None:
            history = self.scheduler.search_history[-100:]
            history = list(reversed(history))

        if not history:
            self.history_canvas.ax.clear()
            self.history_canvas.ax.set_title("No search runs yet")
            self.history_canvas.draw()
            return

        x = list(range(1, len(history) + 1))
        lin = [h["linear_comparisons"] for h in history]
        bin_ = [h["binary_comparisons"] for h in history]

        ax = self.history_canvas.ax
        ax.clear()
        ax.plot(x, lin, marker="o", label="Linear (theoretical)")
        ax.plot(x, bin_, marker="o", label="Binary (actual)")
        ax.set_xlabel("Action number (most recent on the right)")
        ax.set_ylabel("Comparisons")
        ax.set_title("Search cost per action in this system")
        ax.legend()
        self.history_canvas.draw()

        self.result_label.setText(
            "Each point is a real operation (add booking / availability check).\n"
            "For the same data size n, linear search would examine about n items,\n"
            "while binary search only checks about log₂(n) items."
        )

    def show_growth_curve(self):
        """
        Line graph: how time grows with n for both algorithms.
        """
        sizes = [100, 500, 1000, 2000, 5000, 10000]
        results = compare_search_algorithms(sizes, target=9999)

        ns = [r[0] for r in results]
        lin_times = [r[1] for r in results]
        bin_times = [r[2] for r in results]

        ax = self.growth_canvas.ax
        ax.clear()

        ax.plot(ns, lin_times, marker="o", label="Linear")
        ax.plot(ns, bin_times, marker="o", label="Binary")

        ax.set_xlabel("n (size of list)")
        ax.set_ylabel("Time (ms)")
        ax.set_title("Growth of running time vs n")
        ax.legend()
        self.growth_canvas.draw()

        self.result_label.setText(
            "Growth curve: linear time increases roughly proportionally to n (O(n)),\n"
            "while binary time grows much more slowly (O(log n))."
        )

    def refresh_history(self):
        """Load search_history from scheduler into the table + summary."""
        history = self.scheduler.search_history[-100:]  # last 100 runs

        # newest first (optional)
        history = list(reversed(history))

        self.history_table.setRowCount(len(history))
        lin_total = 0
        bin_total = 0

        for row, h in enumerate(history):
            ts_str = h["timestamp"].strftime("%H:%M:%S")
            self.history_table.setItem(row, 0, QTableWidgetItem(ts_str))
            self.history_table.setItem(row, 1, QTableWidgetItem(h["operation"]))
            # n is an int, but QTableWidgetItem wants a string
            self.history_table.setItem(row, 2, QTableWidgetItem(str(h["n"])))
            self.history_table.setItem(
                row, 3, QTableWidgetItem(str(h["linear_comparisons"]))
            )
            self.history_table.setItem(
                row, 4, QTableWidgetItem(str(h["binary_comparisons"]))
            )

            lin_total += h["linear_comparisons"]
            bin_total += h["binary_comparisons"]

        lin_runs = len(history)
        bin_runs = len(history)

        def avg(total, runs):
            return total / runs if runs else 0

        msg = (
            f"Linear (theoretical): {lin_runs} run(s), "
            f"avg {avg(lin_total, lin_runs):.1f} comparisons\n"
            f"Binary (actual): {bin_runs} run(s), "
            f"avg {avg(bin_total, bin_runs):.1f} comparisons"
        )

        self.stats_label.setText(msg)

        # also update the history line graph
        self.plot_history_chart(history)




class AllBookingsTab(QWidget):
    def __init__(self, scheduler: BookingScheduler, on_change=None, parent=None):
        super().__init__(parent)
        self.scheduler = scheduler
        self.on_change = on_change  # callback to MainWindow when bookings change

        root = QHBoxLayout()
        root.setContentsMargins(16, 16, 16, 16)
        root.setSpacing(16)
        self.setLayout(root)

        # ---------- LEFT: table + buttons ----------
        left = QVBoxLayout()
        left.setSpacing(10)
        root.addLayout(left, stretch=3)

        title = QLabel("All Bookings")
        title.setStyleSheet("font-size: 18px; font-weight: 600;")
        left.addWidget(title)

        self.table = QTableWidget()
        self.table.setColumnCount(6)
        self.table.setHorizontalHeaderLabels(
            ["ID", "Name", "Room", "Date", "Start", "End"]
        )
        self.table.horizontalHeader().setStretchLastSection(True)
        self.table.setSelectionBehavior(QTableWidget.SelectRows)
        left.addWidget(self.table, stretch=1)

        btn_row = QHBoxLayout()
        self.add_btn = QPushButton("Add")
        self.edit_btn = QPushButton("Edit")
        self.delete_btn = QPushButton("Delete")
        self.refresh_btn = QPushButton("Refresh")

        self.add_btn.clicked.connect(self.add_booking)
        self.edit_btn.clicked.connect(self.edit_selected)
        self.delete_btn.clicked.connect(self.delete_selected)
        self.refresh_btn.clicked.connect(self.refresh_table)

        btn_row.addWidget(self.add_btn)
        btn_row.addWidget(self.edit_btn)
        btn_row.addWidget(self.delete_btn)
        btn_row.addStretch(1)
        btn_row.addWidget(self.refresh_btn)
        left.addLayout(btn_row)

        # ---------- RIGHT: stats chart ----------
        right = QVBoxLayout()
        right.setSpacing(10)
        root.addLayout(right, stretch=2)

        stats_label = QLabel("Booking Stats")
        stats_label.setStyleSheet("font-size: 16px; font-weight: 600;")
        right.addWidget(stats_label)

        self.stats_canvas = MplCanvas(self)
        right.addWidget(self.stats_canvas, stretch=1)

        self.refresh_table()
        self.update_stats_chart()

    def update_stats_chart(self):
        """Draw a simple bar chart: total bookings per room."""
        bookings = self.scheduler.all_bookings()
        counts = {room: 0 for room in self.scheduler.rooms}
        for b in bookings:
            counts[b.room] = counts.get(b.room, 0) + 1

        rooms = list(counts.keys())
        values = list(counts.values())

        ax = self.stats_canvas.ax
        ax.clear()

        bars = ax.bar(rooms, values)
        # colour rooms roughly like your scheme
        palette = ["#3498db", "#e67e22", "#2ecc71", "#9b59b6", "#e74c3c"]
        for i, bar in enumerate(bars):
            bar.set_color(palette[i % len(palette)])

        ax.set_ylabel("Number of bookings")
        ax.set_xlabel("Room")
        ax.set_title("Bookings per room")
        self.stats_canvas.draw()

    def refresh_table(self):
        """Reload bookings from the scheduler into the table."""
        bookings = self.scheduler.all_bookings()

        self.table.setRowCount(len(bookings))

        for row, b in enumerate(bookings):
            self.table.setItem(row, 0, QTableWidgetItem(str(b.booking_id)))
            self.table.setItem(row, 1, QTableWidgetItem(b.name))
            self.table.setItem(row, 2, QTableWidgetItem(b.room))
            self.table.setItem(row, 3, QTableWidgetItem(b.booking_date.isoformat()))
            self.table.setItem(row, 4, QTableWidgetItem(f"{b.start_hour}:00"))
            self.table.setItem(row, 5, QTableWidgetItem(f"{b.end_hour}:00"))

        self.update_stats_chart()

    def _selected_booking_id(self) -> int | None:
        items = self.table.selectedItems()
        if not items:
            return None
        row = items[0].row()
        id_item = self.table.item(row, 0)
        return int(id_item.text()) if id_item else None

    def delete_selected(self):
        bid = self._selected_booking_id()
        if bid is None:
            QMessageBox.warning(self, "No selection", "Please select a booking to delete.")
            return

        ok = self.scheduler.delete_booking(bid)
        if ok:
            QMessageBox.information(self, "Deleted", "Booking deleted.")
            self.refresh_table()
            if self.on_change:
                self.on_change()
        else:
            QMessageBox.warning(self, "Error", "Could not delete booking.")

    def edit_selected(self):
        bid = self._selected_booking_id()
        if bid is None:
            QMessageBox.warning(self, "No selection", "Please select a booking to edit.")
            return

        booking = self.scheduler.find_booking(bid)
        if not booking:
            QMessageBox.warning(self, "Error", "Booking not found.")
            return

        dialog = EditBookingDialog(self.scheduler, booking, self)
        if dialog.exec_():
            self.refresh_table()
            if self.on_change:
                self.on_change()

    def add_booking(self):
        dialog = AddBookingDialog(self.scheduler, self)
        if dialog.exec_():
            self.refresh_table()
            if self.on_change:
                self.on_change()



class EditBookingDialog(QDialog):
    def __init__(self, scheduler: BookingScheduler, booking: Booking, parent=None):
        super().__init__(parent)
        self.scheduler = scheduler
        self.booking = booking

        self.setWindowTitle(f"Edit Booking [{booking.booking_id}]")
        self.resize(360, 260)

        layout = QVBoxLayout()
        self.setLayout(layout)

        row1 = QHBoxLayout()
        row1.addWidget(QLabel("Name:"))
        self.name_edit = QLineEdit(booking.name)
        row1.addWidget(self.name_edit)
        layout.addLayout(row1)

        row2 = QHBoxLayout()
        row2.addWidget(QLabel("Room:"))
        self.room_combo = QComboBox()
        self.room_combo.addItems(self.scheduler.rooms)
        self.room_combo.setCurrentText(booking.room)
        row2.addWidget(self.room_combo)
        layout.addLayout(row2)

        row3 = QHBoxLayout()
        row3.addWidget(QLabel("Date (YYYY-MM-DD):"))
        self.date_edit = QLineEdit(booking.booking_date.isoformat())
        row3.addWidget(self.date_edit)
        layout.addLayout(row3)

        row4 = QHBoxLayout()
        row4.addWidget(QLabel("Start:"))
        self.start_spin = QSpinBox()
        self.start_spin.setRange(7, 18)
        self.start_spin.setValue(booking.start_hour)
        row4.addWidget(self.start_spin)

        row4.addWidget(QLabel("End:"))
        self.end_spin = QSpinBox()
        self.end_spin.setRange(8, 19)
        self.end_spin.setValue(booking.end_hour)
        row4.addWidget(self.end_spin)
        layout.addLayout(row4)

        btn_row = QHBoxLayout()
        save_btn = QPushButton("Save")
        cancel_btn = QPushButton("Cancel")
        save_btn.clicked.connect(self.save)
        cancel_btn.clicked.connect(self.reject)
        btn_row.addWidget(save_btn)
        btn_row.addWidget(cancel_btn)
        layout.addLayout(btn_row)

    def save(self):
        from datetime import datetime

        name = self.name_edit.text().strip()
        room = self.room_combo.currentText()
        start = self.start_spin.value()
        end = self.end_spin.value()

        try:
            new_date = datetime.strptime(self.date_edit.text().strip(), "%Y-%m-%d").date()
        except ValueError:
            QMessageBox.warning(self, "Error", "Invalid date format.")
            return

        if not name:
            QMessageBox.warning(self, "Error", "Name is required.")
            return
        if start >= end:
            QMessageBox.warning(self, "Error", "Start must be before end.")
            return

        success, conflicts = self.scheduler.update_booking(
            self.booking.booking_id,
            new_name=name,
            new_room=room,
            new_date=new_date,
            new_start=start,
            new_end=end,
        )

        if success:
            QMessageBox.information(self, "Updated", "Booking updated successfully.")
            self.accept()
        else:
            msg = "Cannot update booking due to conflicts:\n\n"
            for c in conflicts:
                msg += (
                    f"• {c.name} in {c.room} "
                    f"({c.start_hour}:00–{c.end_hour}:00)\n"
                )
            QMessageBox.warning(self, "Conflict", msg)



class AddBookingDialog(QDialog):
    def __init__(self, scheduler: BookingScheduler, parent=None):
        super().__init__(parent)
        self.scheduler = scheduler

        self.setWindowTitle("Add Booking")
        self.resize(380, 260)

        layout = QVBoxLayout()
        self.setLayout(layout)

        row1 = QHBoxLayout()
        row1.addWidget(QLabel("Name:"))
        self.name_edit = QLineEdit()
        row1.addWidget(self.name_edit)
        layout.addLayout(row1)

        row2 = QHBoxLayout()
        row2.addWidget(QLabel("Room:"))
        self.room_combo = QComboBox()
        self.room_combo.addItems(self.scheduler.rooms)
        row2.addWidget(self.room_combo)
        layout.addLayout(row2)

        row3 = QHBoxLayout()
        row3.addWidget(QLabel("Date:"))
        from PyQt5.QtCore import QDate as QtDate
        self.date_edit = QDateEdit()
        self.date_edit.setCalendarPopup(True)
        self.date_edit.setDate(QtDate.currentDate())
        row3.addWidget(self.date_edit)
        layout.addLayout(row3)

        row4 = QHBoxLayout()
        row4.addWidget(QLabel("Start:"))
        self.start_spin = QSpinBox()
        self.start_spin.setRange(7, 18)
        self.start_spin.setValue(9)
        row4.addWidget(self.start_spin)

        row4.addWidget(QLabel("End:"))
        self.end_spin = QSpinBox()
        self.end_spin.setRange(8, 19)
        self.end_spin.setValue(10)
        row4.addWidget(self.end_spin)
        layout.addLayout(row4)

        btn_row = QHBoxLayout()
        save_btn = QPushButton("Add")
        cancel_btn = QPushButton("Cancel")
        save_btn.clicked.connect(self.save)
        cancel_btn.clicked.connect(self.reject)
        btn_row.addWidget(save_btn)
        btn_row.addWidget(cancel_btn)
        layout.addLayout(btn_row)

    def save(self):
        name = self.name_edit.text().strip()
        room = self.room_combo.currentText()
        start = self.start_spin.value()
        end = self.end_spin.value()

        qtdate = self.date_edit.date()
        booking_date = date(qtdate.year(), qtdate.month(), qtdate.day())

        if not name:
            QMessageBox.warning(self, "Error", "Please enter a name.")
            return
        if start >= end:
            QMessageBox.warning(self, "Error", "Start must be before end.")
            return

        success, conflicts = self.scheduler.add_booking(
            name=name,
            room=room,
            booking_date=booking_date,
            start_hour=start,
            end_hour=end,
        )

        if success:
            QMessageBox.information(
                self,
                "Booking added",
                f"Booking added!\n\n"
                f"{name} in {room}, {booking_date.isoformat()} "
                f"{start}:00–{end}:00",
            )
            self.accept()
        else:
            msg = "❌ This clashes with:\n\n"
            for c in conflicts:
                msg += (
                    f"• {c.name} in {c.room} "
                    f"{c.booking_date.isoformat()} "
                    f"({c.start_hour}:00–{c.end_hour}:00)\n"
                )
            QMessageBox.warning(self, "Conflict", msg)



class MainWindow(QMainWindow):
    def __init__(self, scheduler: BookingScheduler, parent=None):
        super().__init__(parent)
        self.scheduler = scheduler

        self.setWindowTitle("Shared Resource Scheduling System")
        self.resize(1300, 750)

        # Light background for whole window
        self.setStyleSheet("""
            QMainWindow {
                background: qlineargradient(
                    x1:0, y1:0, x2:1, y2:0,
                    stop:0 #4facfe,
                    stop:1 #00f2fe
                );
            }
            QTabWidget::pane {
                border: none;
            }
            /* push the whole tab bar a bit to the right so text isn't cut */
            QTabWidget::tab-bar {
                left: 8px;
            }
            QTabBar::tab {
                padding: 8px 18px;
                border-top-left-radius: 12px;
                border-top-right-radius: 12px;
                background: rgba(255,255,255,0.5);
                margin-right: 4px;
            }
            QTabBar::tab:selected {
                background: #ffffff;
                font-weight: 600;
            }
        QGroupBox {
                font-weight: bold;
                border: 1px solid #d0d7de;
                border-radius: 20px;
                margin-top: 12px;
                background-color: #ffffff;
            }
            QGroupBox::title {
                subcontrol-origin: margin;
                left: 16px;
                padding: 0px 4px;
            }
        """)

        self.gauge_mode = "today"

        self.tabs = QTabWidget()
        self.setCentralWidget(self.tabs)

        # ---- Tab 1: Scheduler (calendar + overview) ----
        self.scheduler_tab = QWidget()
        scheduler_layout = QHBoxLayout()
        scheduler_layout.setContentsMargins(16, 16, 16, 16)
        scheduler_layout.setSpacing(16)
        self.scheduler_tab.setLayout(scheduler_layout)

        self.calendar_group = self._build_calendar_panel()
        scheduler_layout.addWidget(self.calendar_group, stretch=3)

        self.sidebar_group = self._build_sidebar_panel()
        scheduler_layout.addWidget(self.sidebar_group, stretch=2)

        self.tabs.addTab(self.scheduler_tab, "  Scheduler  ")

        # ---- Tab 2: Algorithm comparison ----
        self.alg_tab = AlgorithmComparisonTab(self.scheduler)
        self.tabs.addTab(self.alg_tab, "  Algorithm Comparison  ")

        # ---- Tab 3: All bookings ----
        self.all_bookings_tab = AllBookingsTab(self.scheduler, on_change=self._bookings_changed)
        self.tabs.addTab(self.all_bookings_tab, "  Manage Bookings  ")

    # ---------- Calendar panel ----------

    def _build_calendar_panel(self) -> QGroupBox:
        group = QGroupBox()  # no outer title
        layout = QVBoxLayout()
        layout.setContentsMargins(20, 20, 20, 20)
        group.setLayout(layout)

        # Logo
        base_dir = os.path.dirname(os.path.abspath(__file__))
        logo_path = os.path.join(base_dir, "scheduler_logo1.png")

        icon = QLabel()
        pixmap = QPixmap(logo_path)

        if pixmap.isNull():
            print("WARNING: Could not load logo from", logo_path)
        else:
            icon.setPixmap(
                pixmap.scaled(330, 280, Qt.KeepAspectRatio, Qt.SmoothTransformation)
            )

        # Big title INSIDE the white card
        heading = QLabel("Meeting Room Scheduler")
        heading.setStyleSheet("font-size: 50px; font-weight: 1000; color: #DAA520;")

        header = QHBoxLayout()
        header.setContentsMargins(0, 0, 0, 0)
        header.setSpacing(6)
        header.addWidget(icon)
        header.addWidget(heading)
        header.setAlignment(Qt.AlignCenter)

        header_widget = QWidget()
        header_widget.setLayout(header)

        layout.addWidget(header_widget)

        # existing "Monthly Booking Overview" can stay just under it
        title = QLabel("Monthly Booking Overview")
        title.setAlignment(Qt.AlignLeft | Qt.AlignVCenter)
        title.setStyleSheet("font-size: 16px; font-weight: 600; margin-top: 8px;")
        layout.addWidget(title)

        nav_row = QHBoxLayout()
        self.prev_btn = QPushButton("◀")
        self.next_btn = QPushButton("▶")
        self.month_label = QLabel()
        self.month_label.setAlignment(Qt.AlignCenter)
        self.month_label.setStyleSheet("font-size: 20px; font-weight: 500;")
        nav_row.addWidget(self.prev_btn)
        nav_row.addWidget(self.month_label, stretch=1)
        nav_row.addWidget(self.next_btn)
        layout.addLayout(nav_row)

        separator = QFrame()
        separator.setFrameShape(QFrame.HLine)
        separator.setFrameShadow(QFrame.Sunken)
        layout.addWidget(separator)

        self.grid = QGridLayout()
        self.grid.setContentsMargins(0, 8, 0, 16)
        self.grid.setHorizontalSpacing(10)
        self.grid.setVerticalSpacing(10)
        layout.addLayout(self.grid)

        self.prev_btn.clicked.connect(self._go_prev_month)
        self.next_btn.clicked.connect(self._go_next_month)

        today = date.today()
        self.current_year = today.year
        self.current_month = today.month

        self._rebuild_calendar()
        return group

    def _rebuild_calendar(self):
        # Rebuild the month grid with utilisation bars for the selected room.
        # Clear old widgets
        while self.grid.count():
            item = self.grid.takeAt(0)
            w = item.widget()
            if w:
                w.deleteLater()

        from calendar import monthcalendar

        # Which room? (sidebar may not exist yet the first time)
        if hasattr(self, "resource_combo"):
            current_room = self.resource_combo.currentText()
        else:
            current_room = self.scheduler.rooms[0]

        self.month_label.setText(f"{month_name[self.current_month]} {self.current_year}")

        # Weekday headers
        weekdays = ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"]
        for col, name in enumerate(weekdays):
            lbl = QLabel(name)
            lbl.setAlignment(Qt.AlignCenter)
            lbl.setStyleSheet("font-weight: 600; color: #5b6475;")
            self.grid.addWidget(lbl, 0, col)

        # Make rows for days a bit taller
        for r in range(1, 7):
            self.grid.setRowMinimumHeight(r, 70)

        # Days
        cal = monthcalendar(self.current_year, self.current_month)
        for row, week in enumerate(cal, start=1):
            for col, day in enumerate(week):
                if day == 0:
                    continue
                d = date(self.current_year, self.current_month, day)
                # 👉 NOW we pass both date and room
                util = self.scheduler.utilisation_for_day(d, current_room)  # 0–100
                cell = DayCell(day, util)
                cell.dayClicked.connect(self._on_day_clicked)
                self.grid.addWidget(cell, row, col)

    def _bookings_changed(self):
        # Call this whenever bookings are added/edited/deleted.
        self._rebuild_calendar()
        self._update_today_utilisation()

        if hasattr(self, "all_bookings_tab"):
            self.all_bookings_tab.refresh_table()

        if hasattr(self, "alg_tab"):
            self.alg_tab.refresh_history()

    def _go_prev_month(self):
        if self.current_month == 1:
            self.current_month = 12
            self.current_year -= 1
        else:
            self.current_month -= 1
        self._rebuild_calendar()

    def _go_next_month(self):
        if self.current_month == 12:
            self.current_month = 1
            self.current_year += 1
        else:
            self.current_month += 1
        self._rebuild_calendar()

    def _on_day_clicked(self, day: int):
        selected_date = date(self.current_year, self.current_month, day)
        dialog = DayBookingsDialog(self.scheduler, selected_date, self)
        dialog.exec_()
        self._rebuild_calendar()
        self._update_today_utilisation()
        self._bookings_changed()
        if hasattr(self, "all_bookings_tab"):
            try:
                self.all_bookings_tab.refresh_table()
            except Exception as e:
                print("Error refreshing 'Manage Bookings' tab:", e)

    # ---------- Sidebar panel ----------

    def _build_sidebar_panel(self) -> QGroupBox:
        group = QGroupBox()  # no outer title
        layout = QVBoxLayout()
        layout.setContentsMargins(20, 20, 20, 20)
        group.setLayout(layout)

        header = QLabel("Resource Overview")
        header.setStyleSheet("font-size: 18px; font-weight: 600;")
        layout.addWidget(header)

        title = QLabel("Booking Overview & Quick Availability Check")
        title.setStyleSheet("font-size: 16px; font-weight: 600; margin-top: 4px;")
        layout.addWidget(title)

        self.today_label = QLabel()
        self.today_label.setStyleSheet("color: #5b6475;")
        layout.addWidget(self.today_label)

        # ---- Mode toggle: Today vs This month ----
        mode_row = QHBoxLayout()
        mode_row.addWidget(QLabel("View:"))
        self.today_mode_radio = QRadioButton("Today")
        self.month_mode_radio = QRadioButton("This month")
        self.today_mode_radio.setChecked(True)
        mode_row.addWidget(self.today_mode_radio)
        mode_row.addWidget(self.month_mode_radio)
        mode_row.addStretch(1)
        layout.addLayout(mode_row)

        self.today_mode_radio.toggled.connect(self._on_gauge_mode_changed)
        self.month_mode_radio.toggled.connect(self._on_gauge_mode_changed)

        layout.addSpacing(6)

        # ---- Grid of gauges: 3 on first row, 2 on second row ----
        gauges_grid = QGridLayout()
        gauges_grid.setHorizontalSpacing(20)
        gauges_grid.setVerticalSpacing(12)

        self.room_gauges = {}  # room -> CircularGauge

        for index, room in enumerate(self.scheduler.rooms):
            row = index // 3  # 0 for first three, 1 for last two
            col = index % 3

            cell_layout = QVBoxLayout()
            cell_layout.setSpacing(4)

            gauge = CircularGauge(diameter=180)  # slightly bigger
            self.room_gauges[room] = gauge
            cell_layout.addWidget(gauge, alignment=Qt.AlignCenter)

            label = QLabel(room)
            label.setAlignment(Qt.AlignCenter)
            label.setStyleSheet("font-size: 10px; color: #555;")
            cell_layout.addWidget(label)

            gauges_grid.addLayout(cell_layout, row, col, alignment=Qt.AlignCenter)

        layout.addLayout(gauges_grid)

        # summary label for whichever room is selected in the combo
        self.today_util_label = QLabel("Total utilisation today (all rooms): 0%")
        self.today_util_label.setStyleSheet("font-size: 13px; color: #5b6475;")
        layout.addWidget(self.today_util_label)

        layout.addSpacing(12)

        # --- Quick availability group ---
        quick_group = QGroupBox("Check Availability")
        qlayout = QVBoxLayout()
        quick_group.setLayout(qlayout)

        qlayout.addWidget(QLabel("Room:"))
        self.resource_combo = QComboBox()
        self.resource_combo.addItems(self.scheduler.rooms)
        self.resource_combo.currentIndexChanged.connect(self._on_room_changed)
        qlayout.addWidget(self.resource_combo)

        from PyQt5.QtCore import QDate as QtDate
        self.date_edit = QDateEdit()
        self.date_edit.setCalendarPopup(True)
        self.date_edit.setDate(QtDate.currentDate())
        qlayout.addWidget(QLabel("Date:"))
        qlayout.addWidget(self.date_edit)

        self.start_spin = QSpinBox()
        self.start_spin.setRange(7, 18)
        self.start_spin.setValue(9)
        self.end_spin = QSpinBox()
        self.end_spin.setRange(8, 19)
        self.end_spin.setValue(10)

        time_row = QHBoxLayout()
        time_row.addWidget(QLabel("Start:"))
        time_row.addWidget(self.start_spin)
        time_row.addWidget(QLabel("End:"))
        time_row.addWidget(self.end_spin)
        qlayout.addLayout(time_row)

        # # --- Algorithm toggle here ---
        # alg_row = QHBoxLayout()
        # alg_row.addWidget(QLabel("Search:"))
        # self.sidebar_linear_radio = QRadioButton("Linear")
        # self.sidebar_binary_radio = QRadioButton("Binary")
        # self.sidebar_binary_radio.setChecked(True)
        # alg_row.addWidget(self.sidebar_linear_radio)
        # alg_row.addWidget(self.sidebar_binary_radio)
        # qlayout.addLayout(alg_row)
        #
        # self.sidebar_linear_radio.toggled.connect(self._update_algorithm_choice)
        # self.sidebar_binary_radio.toggled.connect(self._update_algorithm_choice)

        self.check_btn = QPushButton("Check")
        self.check_btn.clicked.connect(self._check_availability)
        qlayout.addWidget(self.check_btn)

        layout.addWidget(quick_group)
        layout.addStretch(1)

        # set today's info
        today = date.today()
        self.today_label.setText(f"Today: {today.strftime('%d %b %Y')}")
        self._update_today_utilisation()
        return group

    def _on_room_changed(self):
        self._rebuild_calendar()
        self._update_today_utilisation()

    def _update_algorithm_choice(self):
        if self.sidebar_linear_radio.isChecked():
            self.scheduler.search_method = "linear"
        else:
            self.scheduler.search_method = "binary"

    def _update_today_utilisation(self):
        """Update all room gauges + total summary label based on current mode."""
        today = date.today()
        year = self.current_year
        month = self.current_month

        if not hasattr(self, "room_gauges"):
            return

        # 1) update each room gauge and accumulate percentages
        total = 0
        count = 0

        for room, gauge in self.room_gauges.items():
            if self.gauge_mode == "today":
                value = self.scheduler.utilisation_for_day(today, room)
            else:
                value = self.scheduler.utilisation_for_month(year, month, room)

            gauge.animate_to(value)
            total += value
            count += 1

        overall = round(total / count) if count else 0

        # 2) update the summary label
        if self.gauge_mode == "today":
            self.today_util_label.setText(
                f"Total utilisation today (all rooms): {overall}%"
            )
        else:
            self.today_util_label.setText(
                f"Total utilisation this month (all rooms): {overall}%"
            )

    def _check_availability(self):
        qtdate = self.date_edit.date()
        selected_date = date(qtdate.year(), qtdate.month(), qtdate.day())
        room = self.resource_combo.currentText()
        start = self.start_spin.value()
        end = self.end_spin.value()

        if start >= end:
            QMessageBox.warning(self, "Error", "Start hour must be before end hour.")
            return

        # Ask scheduler about conflicts and alternatives
        conflicts = self.scheduler.find_conflicts_for_slot(
            room, selected_date, start, end
        )
        available_rooms = self.scheduler.get_available_rooms(
            selected_date, start, end
        )
        suggestions = self.scheduler.suggest_next_slots(
            room, selected_date, start, end, max_suggestions=2
        )

        # We still update last_search_comparisons internally,
        # but we don't talk about algorithms here any more.
        # comps = self.scheduler.last_search_comparisons  # not shown in message

        if not conflicts:
            # Room is free
            msg = (
                f"✅ {room} is AVAILABLE from {start}:00 to {end}:00 on "
                f"{selected_date.strftime('%d %b %Y')}."
            )

            # Optionally list other available rooms in the same slot
            if available_rooms:
                others = [r for r in available_rooms if r != room]
                if others:
                    msg += "\n\nOther rooms also free for this time:\n"
                    for r in others:
                        msg += f"• {r}\n"

        else:
            # Room is not free
            msg = (
                f"❌ {room} is NOT available from {start}:00 to {end}:00 on "
                f"{selected_date.strftime('%d %b %Y')}.\n\n"
                "Conflicting booking(s):\n"
            )
            for c in conflicts:
                msg += (
                    f"• {c.name} in {c.room} "
                    f"({c.start_hour}:00–{c.end_hour}:00)\n"
                )

            if available_rooms:
                msg += "\n✅ Other rooms free for this time:\n"
                for r in available_rooms:
                    msg += f"• {r}\n"

            if suggestions:
                msg += "\n🕒 This room will next be free at:\n"
                for s_start, s_end in suggestions:
                    msg += f"• {s_start}:00–{s_end}:00\n"

        QMessageBox.information(self, "Room Availability", msg)

        # This operation still logged the search internally,
        # so we just tell the Algorithm tab to refresh its view.
        if hasattr(self, "alg_tab"):
            self.alg_tab.refresh_history()

    def _on_gauge_mode_changed(self):
        if self.today_mode_radio.isChecked():
            self.gauge_mode = "today"
        else:
            self.gauge_mode = "month"
        self._update_today_utilisation()



class DayBookingsDialog(QDialog):
    def __init__(self, scheduler: BookingScheduler, booking_date: date, parent=None):
        super().__init__(parent)
        self.scheduler = scheduler
        self.booking_date = booking_date

        self.setWindowTitle(f"Bookings for {booking_date.strftime('%d %b %Y')}")
        self.resize(500, 420)

        layout = QVBoxLayout()
        self.setLayout(layout)

        header = QLabel(self.windowTitle())
        header.setAlignment(Qt.AlignCenter)
        header.setStyleSheet("font-size: 16px; font-weight: 600;")
        layout.addWidget(header)

        self.list_widget = QListWidget()
        layout.addWidget(self.list_widget, stretch=1)

        # form
        form_group = QGroupBox("Add Booking")
        form_layout = QVBoxLayout()
        form_group.setLayout(form_layout)

        row1 = QHBoxLayout()
        row1.addWidget(QLabel("Name:"))
        self.name_edit = QLineEdit()
        row1.addWidget(self.name_edit)
        form_layout.addLayout(row1)

        row2 = QHBoxLayout()
        row2.addWidget(QLabel("Room:"))
        self.room_combo = QComboBox()
        self.room_combo.addItems(self.scheduler.rooms)
        row2.addWidget(self.room_combo)
        form_layout.addLayout(row2)

        row3 = QHBoxLayout()
        row3.addWidget(QLabel("Start:"))
        self.start_spin = QSpinBox()
        self.start_spin.setRange(7, 18)
        self.start_spin.setValue(9)
        row3.addWidget(self.start_spin)

        row3.addWidget(QLabel("End:"))
        self.end_spin = QSpinBox()
        self.end_spin.setRange(8, 19)
        self.end_spin.setValue(10)
        row3.addWidget(self.end_spin)

        form_layout.addLayout(row3)

        # algorithm choice (for your report)
        row_alg = QHBoxLayout()
        row_alg.addWidget(QLabel("Search:"))
        self.linear_radio = QRadioButton("Linear (O(n))")
        self.binary_radio = QRadioButton("Binary (O(log n))")
        self.binary_radio.setChecked(True)
        row_alg.addWidget(self.linear_radio)
        row_alg.addWidget(self.binary_radio)
        form_layout.addLayout(row_alg)

        self.comparisons_label = QLabel("Comparisons: 0")
        form_layout.addWidget(self.comparisons_label)

        add_btn = QPushButton("Add Booking")
        add_btn.clicked.connect(self._add_booking)
        form_layout.addWidget(add_btn)

        layout.addWidget(form_group)

        self._refresh_list()
        self.timeline.update()

    def _refresh_list(self):
        self.list_widget.clear()
        bookings = self.scheduler.get_bookings_for_day(self.booking_date)
        for b in bookings:
            text = (
                f"[{b.booking_id}] {b.name} - {b.room} "
                f"{b.start_hour}:00–{b.end_hour}:00"
            )
            QListWidgetItem(text, self.list_widget)

    def _add_booking(self):
        name = self.name_edit.text().strip()
        room = self.room_combo.currentText()
        start = self.start_spin.value()
        end = self.end_spin.value()

        if not name:
            QMessageBox.warning(self, "Error", "Please enter a name.")
            return
        if start >= end:
            QMessageBox.warning(self, "Error", "Start must be before end.")
            return

        success, conflicts = self.scheduler.add_booking(
            name=name,
            room=room,
            booking_date=self.booking_date,
            start_hour=start,
            end_hour=end,
        )

        if success:
            QMessageBox.information(
                self,
                "Booking added",
                f"Booking added!\n\n"
                f"{name} in {room}, {start}:00–{end}:00",
            )
            self.name_edit.clear()
            self.start_spin.setValue(9)
            self.end_spin.setValue(10)
            self._refresh_list()
            self.timeline.update()
        else:
            msg = "❌ This clashes with:\n\n"
            for c in conflicts:
                msg += (
                    f"• {c.name} in {c.room} "
                    f"({c.start_hour}:00–{c.end_hour}:00)\n"
                )
            QMessageBox.warning(self, "Conflict", msg)
            self._refresh_list()
            self.timeline.update()