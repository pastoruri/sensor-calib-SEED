import pandas as pd
import numpy as np
import matplotlib.pyplot as plt

# Cargar datos
df = pd.read_csv("calibration_data.csv")

# Filtrar solo valores válidos (evitar divisiones por cero o NaN)
df = df[(df["z_real_mm"] > 0) & (df["side_avg_mm"] > 0) & (df["top_avg_mm"] > 0)]

# Calcular ángulos de inclinación reales
df["angle_side_deg"] = np.degrees(np.arccos(df["z_real_mm"] / df["side_avg_mm"]))
df["angle_top_deg"]  = np.degrees(np.arccos(df["z_real_mm"] / df["top_avg_mm"]))

# Resultados promedio
mean_side = df["angle_side_deg"].mean()
mean_top = df["angle_top_deg"].mean()

# Mostrar por consola
print("Ángulos estimados por distancia:")
print(df[["z_real_mm", "angle_side_deg", "angle_top_deg"]])
print("\n-------------------------------")
print(f"✅ Ángulo promedio SIDE: {mean_side:.2f}°")
print(f"✅ Ángulo promedio TOP : {mean_top:.2f}°")

# Plot
plt.figure(figsize=(8, 4))
plt.plot(df["z_real_mm"], df["angle_side_deg"], 'o-', label="side angle")
plt.plot(df["z_real_mm"], df["angle_top_deg"], 's-', label="top angle")
plt.axhline(mean_side, color='blue', linestyle='--', label=f"Mean side = {mean_side:.2f}°")
plt.axhline(mean_top, color='orange', linestyle='--', label=f"Mean top = {mean_top:.2f}°")
plt.xlabel("Distancia real (mm)")
plt.ylabel("Ángulo estimado (°)")
plt.title("Ángulos estimados de los sensores inclinados")
plt.legend()
plt.grid(True)
plt.tight_layout()
plt.show()
