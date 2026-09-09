import random

def apply_sensor_noise(depth_dict):
    noisy_data = {}
    for node, depth in depth_dict.items():
        if random.random() < 0.02:
            continue # 2% chance of a dropped reading
        noise = random.uniform(-0.02, 0.02)
        noisy_data[node] = max(0.0, depth + noise)
    return noisy_data