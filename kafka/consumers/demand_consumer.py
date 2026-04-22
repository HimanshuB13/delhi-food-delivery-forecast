import json
import redis
import threading
from datetime import datetime
from kafka import KafkaConsumer
from dotenv import load_dotenv

load_dotenv('../../.env')

# Redis connection
r = redis.Redis(host='localhost', port=6379, db=0, decode_responses=True)

def consume_weather():
    consumer = KafkaConsumer(
        'delhi_weather',
        bootstrap_servers='localhost:9092',
        api_version=(2, 8, 0),
        value_deserializer=lambda v: json.loads(v.decode('utf-8')),
        auto_offset_reset='latest',
        group_id='weather_consumer'
    )
    
    print("Weather consumer started...")
    
    for message in consumer:
        weather = message.value
        
        # Store latest weather in Redis
        r.hset('current_weather', mapping={
            'timestamp':    weather['timestamp'],
            'temperature':  weather['temperature'],
            'humidity':     weather['humidity'],
            'wind_speed':   weather['wind_speed'],
            'is_raining':   str(weather['is_raining']),
            'is_foggy':     str(weather['is_foggy']),
            'weather_desc': weather['weather_desc']
        })
        
        # Set expiry — weather data expires after 15 minutes
        r.expire('current_weather', 900)
        
        print(f"[WEATHER] {weather['timestamp']} | "
              f"Temp: {weather['temperature']}°C | "
              f"Rain: {weather['is_raining']}")

def consume_orders():
    consumer = KafkaConsumer(
        'delhi_orders',
        bootstrap_servers='localhost:9092',
        api_version=(2, 8, 0),
        value_deserializer=lambda v: json.loads(v.decode('utf-8')),
        auto_offset_reset='latest',
        group_id='order_consumer'
    )
    
    print("Order consumer started...")
    
    for message in consumer:
        order = message.value
        zone_id = order['zone_id']
        
        # Store latest orders per zone in Redis
        r.hset(f'zone_orders:{zone_id}', mapping={
            'timestamp': order['timestamp'],
            'orders':    order['orders'],
            'hour':      order['hour'],
            'expected':  order['expected'],
            'zone_name': order['zone_name']
        })
        
        # Keep order history (last 100 readings per zone)
        r.lpush(f'order_history:{zone_id}', json.dumps(order))
        r.ltrim(f'order_history:{zone_id}', 0, 99)
        
        print(f"[ORDERS] {order['zone_name']:30} | "
              f"Orders: {order['orders']:4} | "
              f"Expected: {order['expected']:4}")

def main():
    print("Starting demand consumer...")
    print("Listening to delhi_weather and delhi_orders topics\n")
    
    # Run both consumers in parallel threads
    weather_thread = threading.Thread(target=consume_weather, daemon=True)
    order_thread   = threading.Thread(target=consume_orders,  daemon=True)
    
    weather_thread.start()
    order_thread.start()
    
    print("Both consumers running. Press Ctrl+C to stop.\n")
    
    try:
        weather_thread.join()
        order_thread.join()
    except KeyboardInterrupt:
        print("\nConsumer stopped.")

if __name__ == '__main__':
    main()