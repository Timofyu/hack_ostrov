import osmnx as ox
import networkx as nx
import matplotlib.pyplot as plt
import random
import math

ox.settings.overpass_endpoint = "https://overpass.kumi.systems/api/interpreter"

def add_elevation_and_calculate_weights(G):
    print("Adding elevation data and calculating route difficulty...")
    
    # 1. Симулируем получение карты высот (DEM) для каждого узла
    for node, data in G.nodes(data=True):
        # Имитируем, что город находится на склоне (чем больше долгота, тем выше)
        base_elevation = (data['x'] - 39.72) * 10000 
        data['elevation'] = base_elevation + random.uniform(-2, 2)

    # 2. Вычисляем кастомный вес для каждого ребра (дорожки)
    for u, v, key, data in G.edges(keys=True, data=True):
        # Перепад высот
        dz = G.nodes[v]['elevation'] - G.nodes[u]['elevation']
        # Расстояние в метрах
        length = data['length']
        
        # Уклон
        slope = dz / length if length > 0 else 0
        
        # Упрощенная функция Тоблера: базовая скорость 5 км/ч (1.4 м/с)
        speed = 1.4 * math.exp(-3.5 * abs(slope + 0.05))
        
        # Время в секундах для прохождения этого участка
        walk_time = length / speed if speed > 0 else float('inf')
        
        # Записываем наше уникальное значение в ребро графа
        data['real_walk_time'] = walk_time

    return G

def find_best_route():
    target_point = (43.5855, 39.7230)
    print("Downloading graph (it will take a few seconds)...")
    G = ox.graph_from_point(target_point, dist=500, network_type='walk')
    
    # Добавляем рельеф
    G = add_elevation_and_calculate_weights(G)
    
    # Берем случайный "Отель" и случайный "Пляж" из наших узлов
    nodes = list(G.nodes())
    hotel_node = nodes[10]
    beach_node = nodes[-10]
    
    # Ищем стандартный кратчайший путь (по расстоянию)
    shortest_path_dist = nx.shortest_path(G, hotel_node, beach_node, weight='length')
    
    # Ищем НАШ "реальный" путь (с учетом перепада высот и времени)
    shortest_path_time = nx.shortest_path(G, hotel_node, beach_node, weight='real_walk_time')
    
    print("\nRoute comparison:")
    print(f"Standard route: {len(shortest_path_dist)} intersections.")
    print(f"Our 'smart' route (elevation-based): {len(shortest_path_time)} intersections.")
    
    # Визуализируем оба маршрута для сравнения (синий - обычный, зеленый - наш)
    fig, ax = ox.plot_graph_routes(G, [shortest_path_dist, shortest_path_time], 
                                   route_colors=['b', 'g'], route_linewidths=[4, 4], 
                                   node_size=0)

if __name__ == "__main__":
    find_best_route()

def get_walk_time_to_beach(lat, lon):
    print(f"[GeoEngine] Building graph for coordinates {lat}, {lon}...")
    G = ox.graph_from_point((lat, lon), dist=500, network_type='walk')
    G = add_elevation_and_calculate_weights(G)
    
    nodes = list(G.nodes())
    # Берем случайные узлы для имитации точек старта и финиша
    hotel_node = nodes[10]  
    beach_node = nodes[-10] 
    
    # nx.shortest_path_length сама просуммирует вес 'real_walk_time' по всему маршруту
    total_seconds = nx.shortest_path_length(G, hotel_node, beach_node, weight='real_walk_time')
    total_minutes = round(total_seconds / 60, 1)
    
    return total_minutes