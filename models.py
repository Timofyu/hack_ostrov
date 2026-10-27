import json
from dataclasses import dataclass, asdict
from typing import Any, List
from datetime import datetime

@dataclass
class HotelFeature:
    name: str
    value: Any
    source: str
    confidence: float
    timestamp: str = datetime.now().isoformat()

class Hotel:
    def __init__(self, hotel_id: str, name: str, lat: float, lon: float):
        self.hotel_id = hotel_id
        self.name = name
        self.lat = lat
        self.lon = lon
        self.features: List[HotelFeature] = []

    def add_feature(self, feature: HotelFeature):
        self.features.append(feature)

    def to_dict(self):
        return {
            "hotel_id": self.hotel_id,
            "name": self.name,
            "coordinates": {"lat": self.lat, "lon": self.lon},
            "features": [asdict(f) for f in self.features]
        }