import json
import time
import random
import numpy as np
from datetime import datetime
from kafka import KafkaProducer
from dotenv import load_dotenv

load_dotenv('../../.env')

TOPIC = 'delhi_orders'

DELHI_ZONES = {
    'zone_1': {'name': 'Connaught Place', 'base_demand': 120},
    'zone_2': {'name': 'South Delhi / Hauz Khas', 'base_demand': 150},
    'zone_3': {'name': 'North Delhi / Rohini', 'base_demand': 90},
    'zone_4': {'name': 'East Delhi / Laxmi Nagar', 'base_demand': 85},
    'zone_5': {'name': 'West Delhi / Rajouri Garden', 'base_demand': 100},
    'zone_6': {'name': 'Noida / Cyber City', 'base_demand': 130}
}

def get_time_multiplier(hour):
    if 12 <= hour <= 14:   return 1.8   # Lunch
    elif 19 <= hour <= 22: return 2.2   # Dinner
    elif 7 <= hour <= 9:   return 0.8   # Breakfast
    elif 0 <= hour <= 6:   return 0.2   # Late night
    else:                  return 0.6   # Off peak

def simulate_orders(zone_id, zone_info, hour):
    base      = zone_info['base_demand']
    time_mult = get_time_multiplier(hour)
    expected  = base * time_mult
    actual    = max(0, int(np.random.normal(expected, expected * 0.15)))
    
    return {
        'timestamp': datetime.now().isoformat(),
        'zone_id':   zone_id,
        'zone_name': zone_info['name'],
        'orders':    actual,
        'hour':      hour,
        'expected':  int(expected)
    }

def main():
    producer = KafkaProducer(
        bootstrap_servers='localhost:9092',
        api_version=(2, 8, 0),
        value_serializer=lambda v: json.dumps(v).encode('utf-8')
    )
    
    print(f"Order simulator started — sending to topic: {TOPIC}")
    print("Simulating orders for 6 Delhi zones every 10 seconds...")
    print("Press Ctrl+C to stop\n")
    
    while True:
        try:
            hour = datetime.now().hour
            
            for zone_id, zone_info in DELHI_ZONES.items():
                order_data = simulate_orders(zone_id, zone_info, hour)
                producer.send(TOPIC, value=order_data)
            
            producer.flush()
            
            print(f"[{datetime.now().strftime('%H:%M:%S')}] Orders sent for all 6 zones | Hour: {hour}")
            
            time.sleep(10)  # Every 10 seconds
            
        except KeyboardInterrupt:
            print("\nOrder simulator stopped.")
            break
        except Exception as e:
            print(f"Error: {e}")
            time.sleep(5)
    
    producer.close()

if __name__ == '__main__':
    main()