import json
# ИМПОРТИРУЕМ нашу новую функцию из гео-движка
from geo_engine import get_walk_time_to_beach

class HotelAgent:
    def __init__(self):
        self.tools = {
            "get_real_walk_time": self._tool_calculate_walk_time,
            "ask_hotelier": self._tool_ask_hotelier
        }

    def _tool_calculate_walk_time(self, params):
        print(f"[Agent] Calling geo-module for hotel {params['hotel_id']}...")
        
        # РЕАЛЬНЫЙ ВЫЗОВ математического графового расчета
        lat = params.get('lat', 43.5855)
        lon = params.get('lon', 39.7230)
        real_time = get_walk_time_to_beach(lat, lon)
        
        return {"value": real_time, "source": "OSM_Graph_Math_Model", "confidence": 0.95}

    def _tool_ask_hotelier(self, params):
        question = params['question']
        print(f"[Agent] Data not found. Asking hotelier: '{question}'")
        mock_hotelier_response = "Yes, we have great soundproofing, 40cm walls, windows face the courtyard."
        print(f"[Hotelier] Reply: '{mock_hotelier_response}'")
        return {"value": True, "source": "Hotelier_Direct", "confidence": 0.8}

    def process_hotel(self, hotel_id, lat, lon, required_features):
        print(f"\n--- Starting data collection for hotel {hotel_id} ---")
        results = []
        
        for feature in required_features:
            if feature == "time_to_beach":
                # Передаем координаты в инструмент
                result = self.tools["get_real_walk_time"]({"hotel_id": hotel_id, "lat": lat, "lon": lon})
                results.append({"feature": feature, **result})
                
            elif feature == "is_quiet":
                result = self.tools["ask_hotelier"]({
                    "hotel_id": hotel_id, 
                    "question": "Is there soundproofing in the rooms?"
                })
                results.append({"feature": feature, **result})
                
        return results