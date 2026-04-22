import json
import time
import requests
import os
from datetime import datetime
from kafka import KafkaProducer
from dotenv import load_dotenv

# Load .env from project root
load_dotenv(os.path.join(os.path.dirname(__file__), '../../.env'))

API_KEY = os.getenv('OPENWEATHER_API_KEY')
TOPIC   = 'delhi_weather'

def get_delhi_weather():
    url = f"http://api.openweathermap.org/data/2.5/weather?q=Delhi&appid={API_KEY}&units=metric"
    response = requests.get(url, timeout=10)
    data = response.json()
    
    # Debug — print full response first time
    print(f"API Response keys: {list(data.keys())}")
    
    # Check for API error
    if data.get('cod') != 200:
        print(f"API Error: {data}")
        return None
    
    return {
        'timestamp':    datetime.now().isoformat(),
        'temperature':  data['main']['temp'],
        'humidity':     data['main']['humidity'],
        'pressure':     data['main']['pressure'],
        'wind_speed':   data['wind']['speed'],
        'visibility':   data.get('visibility', 10000),
        'weather_main': data['weather'][0]['main'],
        'weather_desc': data['weather'][0]['description'],
        'is_raining':   data['weather'][0]['main'] in ['Rain', 'Drizzle', 'Thunderstorm'],
        'is_foggy':     data['weather'][0]['main'] in ['Fog', 'Mist', 'Haze'],
        'clouds':       data['clouds']['all']
    }

def main():
    print(f"API Key loaded: {'Yes' if API_KEY else 'NO - CHECK .env FILE'}")
    
    producer = KafkaProducer(
        bootstrap_servers='localhost:9092',
        api_version=(2, 8, 0),
        value_serializer=lambda v: json.dumps(v).encode('utf-8')
    )
    
    print(f"Weather producer started — sending to topic: {TOPIC}")
    print("Fetching Delhi weather every 60 seconds...")
    print("Press Ctrl+C to stop\n")
    
    while True:
        try:
            weather = get_delhi_weather()
            
            if weather is None:
                print("Skipping — bad API response")
                time.sleep(30)
                continue
                
            producer.send(TOPIC, value=weather)
            producer.flush()
            
            print(f"[{weather['timestamp']}] Sent weather:")
            print(f"  Temperature: {weather['temperature']}°C")
            print(f"  Humidity:    {weather['humidity']}%")
            print(f"  Condition:   {weather['weather_desc']}")
            print(f"  Raining:     {weather['is_raining']}")
            print()
            
            time.sleep(60)
            
        except KeyboardInterrupt:
            print("\nWeather producer stopped.")
            break
        except Exception as e:
            print(f"Error details: {e}")
            import traceback
            traceback.print_exc()
            time.sleep(10)
    
    producer.close()

if __name__ == '__main__':
    main()