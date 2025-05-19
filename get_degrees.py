import numpy as np



def calcular_inclinacion_pared(
    d_bottom, d_side, d_top,
    theta_side_deg, theta_top_deg,
    delta_x_side, delta_y_top
):
    # Convertir ángulos a radianes
    theta_side = np.radians(theta_side_deg)
    theta_top  = np.radians(theta_top_deg)

    # Vectores unitarios de cada sensor
    v_bottom = np.array([0.0, 0.0, -1.0])  # referencia perpendicular
    v_side   = np.array([np.sin(theta_side), 0.0, -np.cos(theta_side)])  # horizontal
    v_top    = np.array([0.0, np.sin(theta_top), -np.cos(theta_top)])    # vertical

    # Posiciones relativas
    o_bottom = np.array([0.0, 0.0, 0.0])
    o_side   = np.array([delta_x_side, 0.0, 0.0])
    o_top    = np.array([0.0, delta_y_top, 0.0])

    # Puntos 3D de impacto
    p_bottom = o_bottom + d_bottom * v_bottom
    p_side   = o_side   + d_side   * v_side
    p_top    = o_top    + d_top    * v_top

    # Calcular plano (normal a partir de los vectores)
    v1 = p_side - p_bottom
    v2 = p_top  - p_bottom
    normal = np.cross(v1, v2)
    normal /= np.linalg.norm(normal)

    # Separar componentes de inclinación
    # La proyección sobre Z da inclinación total
    # Proyección sobre XZ = yaw, YZ = pitch
    yaw_rad   = np.arctan2(normal[0], -normal[2])  # eje X/Z
    pitch_rad = np.arctan2(normal[1], -normal[2])  # eje Y/Z

    yaw_deg   = np.degrees(yaw_rad)
    pitch_deg = np.degrees(pitch_rad)

    return pitch_deg, yaw_deg, normal

# === 🧪 EJEMPLO DE USO ===

# Entradas (ejemplo real)
		

d_bottom = 551.38  # mm
d_side   = 574.1
d_top    = 569.43

# Calibración previa
theta_side_deg = 16.09  # inclinación horizontal
theta_top_deg  = 14.54  # inclinación vertical

# Posiciones relativas
delta_x_side = -60  # mm (izquierda de bottom)
delta_y_top  = 25  # mm (encima de bottom)

pitch, yaw, normal = calcular_inclinacion_pared(
    d_bottom, d_side, d_top,
    theta_side_deg, theta_top_deg,
    delta_x_side, delta_y_top
)

print(f"✅ Inclinación vertical (pitch): {pitch:.2f}°")
print(f"✅ Inclinación horizontal (yaw): {yaw:.2f}°")
print(f"🧭 Normal estimada del plano: {normal}")
