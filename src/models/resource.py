from dataclasses import dataclass


@dataclass
class Resource:
    """Represents a shared resource, such as a room or piece of equipment."""
    resource_id: str
    name: str
    description: str = ""
