import redis
import joblib
import json
import numpy as np
import pandas as pd
from datetime import datetime
import os

# Connect to Redis
r = redis.Redis(host='localhost', port=6379, db=0, decode_responses=True)

# Load model and feature columns
BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
model = joblib.load(os.path.join(BASE_DIR, 'models/baseline_model.pkl'))

with open(os.path.join(BASE_DIR, 'models/feature_cols.json')) as f:
    feature_cols = json.load(f)

ZONES = {
    'zone_1': {'name': 'Connaught Place',        'base_demand': 120, 'type_encoded': 0, 'encoded': 1},
    'zone_2': {'name': 'South Delhi / Hauz Khas','base_demand': 150, 'type_encoded': 1, 'encoded': 2},
    'zone_3': {'name': 'North Delhi / Rohini',   'base_demand': 90,  'type_encoded': 2, 'encoded': 3},
    'zone_4': {'name': 'East Delhi / Laxmi Nagar','base_demand': 85, 'type_encoded': 2, 'encoded': 4},
    'zone_5': {'name': 'West Delhi / Rajouri Garden','base_demand': 100,'type_encoded': 3,'encoded': 5},
    'zone_6': {'name': 'Noida / Cyber City',     'base_demand': 130, 'type_encoded': 4, 'encoded': 6}
}

def get_current_features(zone_id):
    now   = datetime.now()
    hour  = now.hour
    dow   = now.weekday()
    month = now.month
    dom   = now.day
    zone  = ZONES[zone_id]

    # Time features
    is_lunch      = 1 if 12 <= hour <= 14 else 0
    is_dinner     = 1 if 19 <= hour <= 22 else 0
    is_breakfast  = 1 if 7  <= hour <= 9  else 0
    is_late_night = 1 if hour >= 23 or hour <= 5 else 0
    is_peak       = 1 if is_lunch or is_dinner else 0
    is_weekend    = 1 if dow >= 5 else 0

    # Cyclical encoding
    hour_sin = np.sin(2 * np.pi * hour / 24)
    hour_cos = np.cos(2 * np.pi * hour / 24)
    dow_sin  = np.sin(2 * np.pi * dow  / 7)
    dow_cos  = np.cos(2 * np.pi * dow  / 7)

    # Get lag features from Redis order history
    history_key = f'order_history:{zone_id}'
    history_raw = r.lrange(history_key, 0, 99)
    history     = [json.loads(h) for h in history_raw]
    orders_list = [h['orders'] for h in history] if history else [zone['base_demand']]

    lag_1  = orders_list[0]  if len(orders_list) > 0  else zone['base_demand']
    lag_2  = orders_list[1]  if len(orders_list) > 1  else zone['base_demand']
    lag_4  = orders_list[3]  if len(orders_list) > 3  else zone['base_demand']
    lag_48 = orders_list[47] if len(orders_list) > 47 else zone['base_demand']

    rolling_4  = np.mean(orders_list[:4])  if len(orders_list) >= 4  else zone['base_demand']
    rolling_48 = np.mean(orders_list[:48]) if len(orders_list) >= 48 else zone['base_demand']

    features = {
        'hour': hour, 'day_of_week': dow, 'month': month,
        'day_of_month': dom, 'is_weekend': is_weekend,
        'is_lunch': is_lunch, 'is_dinner': is_dinner,
        'is_breakfast': is_breakfast, 'is_late_night': is_late_night,
        'is_peak': is_peak, 'hour_sin': hour_sin, 'hour_cos': hour_cos,
        'dow_sin': dow_sin, 'dow_cos': dow_cos,
        'is_festival': 0, 'demand_multiplier': 1.0,
        'is_major_festival': 0, 'is_ipl_season': 1 if month in [4,5] else 0,
        'is_monsoon': 1 if month in [7,8,9] else 0,
        'zone_base_demand': zone['base_demand'],
        'zone_type_encoded': zone['type_encoded'],
        'zone_encoded': zone['encoded'],
        'orders_lag_1': lag_1, 'orders_lag_2': lag_2,
        'orders_lag_4': lag_4, 'orders_lag_48': lag_48,
        'orders_rolling_mean_4': rolling_4,
        'orders_rolling_mean_48': rolling_48
    }

    return pd.DataFrame([features])[feature_cols]

def predict_demand(zone_id):
    features   = get_current_features(zone_id)
    prediction = model.predict(features)[0]
    return max(0, int(prediction))

def predict_all_zones():
    predictions = {}
    for zone_id, zone_info in ZONES.items():
        pred = predict_demand(zone_id)
        predictions[zone_id] = {
            'zone_name':  zone_info['name'],
            'predicted':  pred,
            'timestamp':  datetime.now().isoformat()
        }
        # Store prediction in Redis
        r.hset(f'prediction:{zone_id}', mapping={
            'predicted':  pred,
            'zone_name':  zone_info['name'],
            'timestamp':  datetime.now().isoformat()
        })
    return predictions

if __name__ == '__main__':
    print("Running predictions for all Delhi zones...\n")
    predictions = predict_all_zones()
    for zone_id, pred in predictions.items():
        print(f"{pred['zone_name']:35} → {pred['predicted']:4} orders predicted")