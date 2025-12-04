from datetime import date, datetime
from time import perf_counter
from calendar import monthrange
from typing import Dict, List, Tuple

from src.models.booking import Booking
from src.algorithms.search_algorithms import binary_search

DAY_START_HOUR = 7
DAY_END_HOUR = 19      # exclusive upper bound (like 19:00)


class BookingScheduler:
    """
    Manages bookings using student's own binary_search (no bisect).

    bookings_by_room_date[(room, date)] = list[Booking] sorted by start_hour.
    """

    def __init__(self) -> None:
        self.bookings_by_room_date: Dict[Tuple[str, date], List[Booking]] = {}
        self.next_id: int = 1
        self.search_method = "binary"

        self.rooms = [
            "Meeting Room A",
            "Meeting Room B",
            "Meeting Room C",
            "Meeting Room D",
            "Meeting Room E",
        ]

        # history of search runs used inside the app
        # each item: {"timestamp": datetime, "operation": str,
        #             "algorithm": str, "n": int, "comparisons": int}
        self.search_history: List[dict] = []
        self.last_search_comparisons: int = 0

    # ---------- helpers ----------
    def _log_run(
            self,
            operation: str,
            n: int,
            linear_comparisons: int,
            binary_comparisons: int,
            linear_time_ms: float,
            binary_time_ms: float,
    ):
        self.search_history.append({
            "timestamp": datetime.now(),
            "operation": operation,
            "n": n,
            "linear_comparisons": linear_comparisons,
            "binary_comparisons": binary_comparisons,
            "linear_time_ms": linear_time_ms,
            "binary_time_ms": binary_time_ms,
        })

    def _get_list_for(self, room: str, booking_date: date) -> List[Booking]:
        key = (room, booking_date)
        if key not in self.bookings_by_room_date:
            self.bookings_by_room_date[key] = []
        return self.bookings_by_room_date[key]

    def get_bookings_for_day(self, booking_date: date) -> List[Booking]:
        out: List[Booking] = []
        for (room, d), blist in self.bookings_by_room_date.items():
            if d == booking_date:
                out.extend(blist)
        out.sort(key=lambda b: (b.room, b.start_hour))
        return out

    def get_bookings_for_room_on_day(self, room: str, booking_date: date) -> List[Booking]:
        return list(self.bookings_by_room_date.get((room, booking_date), []))

    # ---------- utilisation (PER ROOM) ----------

    def utilisation_for_day(self, booking_date: date, room: str) -> int:
        """
        Percentage of the room's open hours (7–19) that are booked for that date.
        100% means that room is fully booked for the whole working day.
        """
        blist = self.bookings_by_room_on_day(room, booking_date)
        total_hours = sum(b.end_hour - b.start_hour for b in blist)

        day_length = DAY_END_HOUR - DAY_START_HOUR  # 12 hours
        if day_length <= 0:
            return 0

        pct = int(round((total_hours / day_length) * 100))
        return max(0, min(100, pct))

    def utilisation_for_month(self, year: int, month: int, room: str) -> int:
        """
        Percentage of the month's working hours (7–19 each day) that are booked
        for the given room.
        """
        # count how many days in this month
        _, num_days = monthrange(year, month)
        day_length = DAY_END_HOUR - DAY_START_HOUR
        capacity = num_days * day_length
        if capacity <= 0:
            return 0

        booked_hours = 0.0
        for (r, d), blist in self.bookings_by_room_date.items():
            if r != room:
                continue
            if d.year == year and d.month == month:
                for b in blist:
                    booked_hours += (b.end_hour - b.start_hour)

        pct = int(round((booked_hours / capacity) * 100))
        return max(0, min(100, pct))

    def bookings_by_room_on_day(self, room: str, booking_date: date) -> List[Booking]:
        return self.bookings_by_room_date.get((room, booking_date), [])

    # ---------- conflict helpers (linear vs binary) ----------

    def _linear_conflicts(
        self, blist: List[Booking], candidate: Booking
    ):
        conflicts: List[Booking] = []
        comps = 0
        for b in blist:
            comps += 1
            if b.overlaps(candidate):
                conflicts.append(b)

        # insertion index by time
        idx = 0
        while idx < len(blist) and blist[idx].start_hour < candidate.start_hour:
            idx += 1

        return conflicts, comps, idx

    def _binary_conflicts(
        self, blist: List[Booking], candidate: Booking
    ):
        starts = [b.start_hour for b in blist]
        _, idx, comps = binary_search(starts, candidate.start_hour, verbose=False)

        conflicts: List[Booking] = []
        extra = 0

        # scan left
        i = idx - 1
        while i >= 0:
            extra += 1
            b = blist[i]
            if b.end_hour <= candidate.start_hour:
                break
            if b.overlaps(candidate):
                conflicts.append(b)
            i -= 1

        # scan right
        i = idx
        while i < len(blist):
            extra += 1
            b = blist[i]
            if b.start_hour >= candidate.end_hour:
                break
            if b.overlaps(candidate):
                conflicts.append(b)
            i += 1

        return conflicts, comps + extra, idx

    def _conflicts_for_list(self, blist: List[Booking], candidate: Booking):
        if self.search_method == "linear":
            return self._linear_conflicts(blist, candidate)
        else:
            return self._binary_conflicts(blist, candidate)

    # ---------- public API ----------

    def add_booking(
        self,
        name: str,
        room: str,
        booking_date: date,
        start_hour: int,
        end_hour: int,
    ):
        candidate = Booking(
            booking_id=self.next_id,
            name=name,
            room=room,
            booking_date=booking_date,
            start_hour=start_hour,
            end_hour=end_hour,
        )

        blist = self._get_list_for(room, booking_date)

        # --- binary search (real algorithm) ---
        t0 = perf_counter()
        binary_conflicts, bin_comps, idx = self._binary_conflicts(blist, candidate)
        t1 = perf_counter()
        bin_ms = (t1 - t0) * 1000.0

        # --- linear search (for stats only) ---
        t0 = perf_counter()
        linear_conflicts, lin_comps, _ = self._linear_conflicts(blist, candidate)
        t1 = perf_counter()
        lin_ms = (t1 - t0) * 1000.0

        self.last_search_comparisons = bin_comps  # real algorithm = binary

        self._log_run(
            "add_booking",
            n=len(blist),
            linear_comparisons=lin_comps,
            binary_comparisons=bin_comps,
            linear_time_ms=lin_ms,
            binary_time_ms=bin_ms,
        )

        # use *binary* conflicts for actual logic
        conflicts = binary_conflicts
        if conflicts:
            return False, conflicts

        blist.insert(idx, candidate)
        self.next_id += 1
        return True, []

    def find_conflicts_for_slot(
        self, room: str, booking_date: date, start_hour: int, end_hour: int
    ) -> List[Booking]:
        """Use chosen algorithm, but do NOT insert."""
        dummy = Booking(
            booking_id=-1,
            name="(check)",
            room=room,
            booking_date=booking_date,
            start_hour=start_hour,
            end_hour=end_hour,
        )
        blist = self._get_list_for(room, booking_date)

        # binary (real)
        t0 = perf_counter()
        binary_conflicts, bin_comps, _ = self._binary_conflicts(blist, dummy)
        t1 = perf_counter()
        bin_ms = (t1 - t0) * 1000.0

        # linear (demo only)
        t0 = perf_counter()
        linear_conflicts, lin_comps, _ = self._linear_conflicts(blist, dummy)
        t1 = perf_counter()
        lin_ms = (t1 - t0) * 1000.0

        self.last_search_comparisons = bin_comps

        self._log_run(
            "check_availability",
            n=len(blist),
            linear_comparisons=lin_comps,
            binary_comparisons=bin_comps,
            linear_time_ms=lin_ms,
            binary_time_ms=bin_ms,
        )

        # actual behaviour = binary
        return binary_conflicts

    def get_available_rooms(
        self, booking_date: date, start_hour: int, end_hour: int
    ) -> List[str]:
        """Rooms that have no conflicts in that slot."""
        available = []
        for room in self.rooms:
            if not self.find_conflicts_for_slot(room, booking_date, start_hour, end_hour):
                available.append(room)
        return available

    def suggest_next_slots(
        self,
        room: str,
        booking_date: date,
        start_hour: int,
        end_hour: int,
        max_suggestions: int = 2,
    ) -> List[Tuple[int, int]]:
        """
        Suggest up to `max_suggestions` alternative start/end times for the same
        duration on that day for the given room.
        """
        duration = end_hour - start_hour
        if duration <= 0:
            return []

        blist = self.get_bookings_for_room_on_day(room, booking_date)
        suggestions: List[Tuple[int, int]] = []

        # build "gaps" between bookings
        current = DAY_START_HOUR
        for b in blist:
            if b.start_hour - current >= duration:
                # gap [current, b.start_hour)
                if current >= start_hour:
                    suggestions.append((current, current + duration))
                    if len(suggestions) >= max_suggestions:
                        return suggestions
            current = max(current, b.end_hour)

        # after last booking
        if DAY_END_HOUR - current >= duration and current >= start_hour:
            suggestions.append((current, current + duration))

        return suggestions[:max_suggestions]

    # ---------- management by ID (for All Bookings tab) ----------

    def find_booking(self, booking_id: int) -> Booking | None:
        for blist in self.bookings_by_room_date.values():
            for b in blist:
                if b.booking_id == booking_id:
                    return b
        return None

    def delete_booking(self, booking_id: int) -> bool:
        for key, blist in self.bookings_by_room_date.items():
            for b in blist:
                if b.booking_id == booking_id:
                    blist.remove(b)
                    return True
        return False

    def update_booking(
        self,
        booking_id: int,
        new_name: str,
        new_room: str,
        new_date: date,
        new_start: int,
        new_end: int,
    ):
        """
        Try to update a booking by deleting the old one and inserting a new one.
        If the new booking conflicts, the old one is restored.
        Returns (success: bool, conflicts: list[Booking])
        """
        old = self.find_booking(booking_id)
        if not old:
            return False, []

        # remove old
        old_list = self.bookings_by_room_date[(old.room, old.booking_date)]
        old_list.remove(old)

        # attempt new
        success, conflicts = self.add_booking(
            new_name,
            new_room,
            new_date,
            new_start,
            new_end,
        )

        if not success:
            # restore old booking
            old_list.append(old)
            old_list.sort(key=lambda b: b.start_hour)

        return success, conflicts

    def all_bookings(self) -> List[Booking]:
        """
        Return a flat list of all bookings, sorted by date, room, then start time.
        Used by the 'All Bookings' tab.
        """
        out: List[Booking] = []
        for blist in self.bookings_by_room_date.values():
            out.extend(blist)

        out.sort(key=lambda b: (b.booking_date, b.room, b.start_hour))
        return out

