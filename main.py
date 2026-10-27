import json
# Импортируем наши готовые модули
from models import Hotel, HotelFeature
from agent import HotelAgent

def run_pipeline():
    print("Starting Hackathon Prototype: Hotel Agent System...\n")
    
    # 1. Инициализируем отель (имитация загрузки из базы данных)
    target_hotel = Hotel(hotel_id="H_777", name="Sea View Resort", lat=43.5855, lon=39.7230)
    
    # 2. Инициализируем агента
    agent = HotelAgent()
    
    # 3. Имитируем запрос: нужны данные о доступности пляжа и уровне шума
    features_to_find = ["time_to_beach", "is_quiet"]
    
    # 4. Агент собирает данные с помощью своих инструментов
    collected_data = agent.process_hotel(target_hotel.hotel_id, target_hotel.lat, target_hotel.lon, features_to_find)
    
    # 5. Сохраняем собранные данные в структуру отеля
    for item in collected_data:
        feature = HotelFeature(
            name=item["feature"],
            value=item["value"],
            source=item["source"],
            confidence=item["confidence"]
        )
        target_hotel.add_feature(feature)
        
    # 6. Выводим готовый результат, который можно отправлять на фронтенд
    print("\n--- Final System Output ---")
    print(json.dumps(target_hotel.to_dict(), indent=2))

if __name__ == "__main__":
    run_pipeline()