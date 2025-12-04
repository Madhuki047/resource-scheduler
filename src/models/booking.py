from dataclasses import dataclass
from datetime import date


@dataclass
class Booking:
    # Represents a single booking for a specific date and room.
    # Times are stored as integer hours (0–24), just like in your Tkinter version.

    booking_id: int
    name: str
    room: str
    booking_date: date
    start_hour: int
    end_hour: int

    def overlaps(self, other: "Booking") -> bool:
        """Check if this booking overlaps with another on same date & room."""
        return (
            self.room == other.room
            and self.booking_date == other.booking_date
            and self.start_hour < other.end_hour
            and other.start_hour < self.end_hour
        )

    def __lt__(self, other: "Booking") -> bool:
        """
        For sorting: first by date, then by start time, then by end time.
        This lets us use bisect/binary search on the list.
        """
        return (
            (self.booking_date, self.start_hour, self.end_hour)
            < (other.booking_date, other.start_hour, other.end_hour)
        )

    def __repr__(self) -> str:
        return (
            f"{self.name}: {self.room} "
            f"{self.booking_date} ({self.start_hour}-{self.end_hour})"
        )
