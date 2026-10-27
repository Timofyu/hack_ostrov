import streamlit as st
import json
from models import Hotel, HotelFeature
from agent import HotelAgent

# Настройка страницы
st.set_page_config(page_title="Hotel Agent Prototype", layout="centered")
st.title("🏨 Прототип Агентной Системы")
st.markdown("Поиск отеля по неявным характеристикам с помощью мультиагентного сбора данных.")

# Кэшируем агента, чтобы он не создавался заново при каждом клике
@st.cache_resource
def get_agent():
    return HotelAgent()

agent = get_agent()

# Имитация базы данных (наш тестовый отель)
target_hotel = Hotel(hotel_id="H_777", name="Sea View Resort", lat=43.5855, lon=39.7230)

st.write(f"**Тестируем на отеле:** {target_hotel.name} (Координаты: {target_hotel.lat}, {target_hotel.lon})")

# Поле для ввода запроса от пользователя
user_query = st.text_input("Опишите, что для вас важно (например: 'тихий отель недалеко от пляжа')")

if st.button("Запустить агентов"):
    if user_query:
        # Индикатор загрузки, пока агент работает
        with st.spinner("Агент анализирует геоданные и связывается с отельером..."):
            
            # В полноценном MVP здесь работала бы LLM, которая из текста user_query 
            # извлекает список нужных фичей. Для хакатона жестко привязываем наш тестовый набор:
            features_to_find = ["time_to_beach", "is_quiet"]
            
            # Запускаем наш готовый пайплайн
            collected_data = agent.process_hotel(target_hotel.hotel_id, target_hotel.lat, target_hotel.lon, features_to_find)
            
            # Очищаем старые фичи перед новым поиском и добавляем новые
            target_hotel.features = []
            for item in collected_data:
                feature = HotelFeature(
                    name=item["feature"],
                    value=item["value"],
                    source=item["source"],
                    confidence=item["confidence"]
                )
                target_hotel.add_feature(feature)
            
            st.success("Агент успешно собрал уникальные характеристики!")
            
            # Выводим результат в красивом JSON-формате прямо на сайт
            st.json(target_hotel.to_dict())
    else:
        st.warning("Пожалуйста, введите запрос.")