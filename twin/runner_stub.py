import math

def run_simulation(control_on=False, steps=100):
    data = []
    for t in range(steps):
        depths = {}
        # Base water level rises then falls
        base = max(0.1, math.sin(t / 20.0) * 1.5 if t < 60 else 0.2)
        
        # If control is active, simulate gates diverting water
        if control_on and base > 0.8:
            base = 0.8 + (base - 0.8) * 0.2 
            
        depths["Velachery_Main"] = base
        depths["Pallikaranai_Marsh"] = base * 0.5 # Marsh absorbs water
        depths["Outfall_Gate"] = base * 0.8
        data.append(depths)
    return data