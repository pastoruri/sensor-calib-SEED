import cv2
import os
import re
import csv
import numpy as np
import pandas as pd
from math import cos, radians
from datetime import timezone, timedelta, datetime
from tkinter import Tk, filedialog

# === Selección de archivos ===
Tk().withdraw()
video_path = filedialog.askopenfilename(title="Selecciona un video MP4", filetypes=[("Archivos MP4", "*.mp4")])
if not video_path:
    print("No se seleccionó ningún video. Cerrando.")
    exit()

base = os.path.splitext(video_path)[0]
srt_path = base + '.srt'

def parse_srt_by_frame(path):
    pos_data = {}
    current_frame = None
    lat = lon = alt = None
    gb_yaw = gb_pitch = gb_roll = None
    unix_ts = None
    timeframe_unix = None

    with open(path, 'r', encoding='utf-8', errors='ignore') as f:
        for line in f:
            line = line.strip()

            time_match = re.search(r"(\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2}\.\d+)", line)
            if time_match:
                dt = datetime.strptime(time_match.group(1), "%Y-%m-%d %H:%M:%S.%f")
                unix_ts = (dt - timedelta(hours=5)).timestamp()
                timeframe_unix = unix_ts

            if "FrameCnt:" in line:
                match = re.search(r"FrameCnt: (\d+)", line)
                if match:
                    current_frame = int(match.group(1)) - 1

            if "[latitude:" in line:
                match = re.search(r"\[latitude: ([\-\d\.]+)\]", line)
                if match:
                    lat = float(match.group(1))

            if "[longitude:" in line:
                match = re.search(r"\[longitude: ([\-\d\.]+)\]", line)
                if match:
                    lon = float(match.group(1))

            if "[rel_alt:" in line:
                match = re.search(r"\[rel_alt: ([\-\d\.]+)", line)
                if match:
                    alt = float(match.group(1))

            if "[gb_yaw:" in line:
                yaw_match = re.search(r"\[gb_yaw:\s*([\-\d\.]+)", line)
                pitch_match = re.search(r"gb_pitch:\s*([\-\d\.]+)", line)
                roll_match = re.search(r"gb_roll:\s*([\-\d\.]+)", line)
                if yaw_match: gb_yaw = float(yaw_match.group(1))
                if pitch_match: gb_pitch = float(pitch_match.group(1))
                if roll_match: gb_roll = float(roll_match.group(1))

            if "</font>" in line:
                if current_frame is not None:
                    pos_data[current_frame] = {
                        "lat": lat, "lon": lon, "alt": alt,
                        "gb_yaw": gb_yaw, "gb_pitch": gb_pitch, "gb_roll": gb_roll,
                        "unix_ts": unix_ts, "frame_unix_ts": timeframe_unix
                    }
                current_frame = lat = lon = alt = gb_yaw = gb_pitch = gb_roll = unix_ts = timeframe_unix = None

    print(f"✅ Frames con datos cargados: {len(pos_data)}")
    return pos_data

def calcular_inclinacion_pared(d_bottom, d_side, d_top):
    theta_side_deg = 16.09
    theta_top_deg  = 14.54
    delta_x_side = -60
    delta_y_top  = 25

    theta_side = np.radians(theta_side_deg)
    theta_top  = np.radians(theta_top_deg)

    v_bottom = np.array([0.0, 0.0, -1.0])
    v_side   = np.array([np.sin(theta_side), 0.0, -np.cos(theta_side)])
    v_top    = np.array([0.0, np.sin(theta_top), -np.cos(theta_top)])

    o_bottom = np.array([0.0, 0.0, 0.0])
    o_side   = np.array([delta_x_side, 0.0, 0.0])
    o_top    = np.array([0.0, delta_y_top, 0.0])

    p_bottom = o_bottom + d_bottom * v_bottom
    p_side   = o_side   + d_side   * v_side
    p_top    = o_top    + d_top    * v_top

    v1 = p_side - p_bottom
    v2 = p_top  - p_bottom
    normal = np.cross(v1, v2)
    normal /= np.linalg.norm(normal)

    yaw_rad   = np.arctan2(normal[0], -normal[2])
    pitch_rad = np.arctan2(normal[1], -normal[2])
    yaw_deg   = np.degrees(yaw_rad)
    pitch_deg = np.degrees(pitch_rad)

    print("\n================ DEBUG (Plano respecto al dron) ================")
    print(f"→ Pitch: {pitch_deg:.2f}°  |  Yaw: {yaw_deg:.2f}°")
    print(f"→ Normal (dron): {normal}")
    print("===============================================================\n")

    return pitch_deg, yaw_deg, normal

def rotar_normal_a_sistema_camara(normal_dron, yaw_deg, pitch_deg, roll_deg):
    yaw = np.radians(yaw_deg)
    pitch = np.radians(pitch_deg)
    roll = np.radians(roll_deg)

    R_yaw = np.array([
        [np.cos(-yaw), -np.sin(-yaw), 0],
        [np.sin(-yaw),  np.cos(-yaw), 0],
        [0,             0,            1]
    ])
    R_pitch = np.array([
        [ np.cos(-pitch), 0, np.sin(-pitch)],
        [ 0,              1, 0],
        [-np.sin(-pitch), 0, np.cos(-pitch)]
    ])
    R_roll = np.array([
        [1, 0,              0],
        [0, np.cos(-roll), -np.sin(-roll)],
        [0, np.sin(-roll),  np.cos(-roll)]
    ])
    R = R_yaw @ R_pitch @ R_roll
    normal_camera = R @ normal_dron

    yaw_c = np.degrees(np.arctan2(normal_camera[0], -normal_camera[2]))
    pitch_c = np.degrees(np.arctan2(normal_camera[1], -normal_camera[2]))

    print("================ DEBUG (Transformación a cámara) ================")
    print(f"→ Gimbal yaw: {yaw_deg:.2f}°  pitch: {pitch_deg:.2f}°  roll: {roll_deg:.2f}°")
    print(f"→ Pitch cámara: {pitch_c:.2f}°  |  Yaw cámara: {yaw_c:.2f}°")
    print(f"→ Normal (cámara): {normal_camera}")
    print("===============================================================\n")

    return normal_camera

def corregir_perspectiva(img, normal, frame_index=None, pitch=None, yaw=None):
    H, W = img.shape[:2]
    fx = fy = 1000
    cx, cy = W / 2, H / 2
    K = np.array([[fx, 0, cx], [0, fy, cy], [0, 0, 1]])

    z_axis = normal / np.linalg.norm(normal)
    x_axis = np.cross(np.array([0, 1, 0]), z_axis)
    x_axis /= np.linalg.norm(x_axis)
    y_axis = np.cross(z_axis, x_axis)
    R = np.vstack([x_axis, y_axis, z_axis]).T

    H_matrix = K @ R.T @ np.linalg.inv(K)
    corrected = cv2.warpPerspective(img, H_matrix, (W, H))

    # Overlay con parámetros aplicados directamente en la imagen corregida
    if pitch is not None and yaw is not None:
        text = f"Frame: {frame_index} | Pitch: {pitch:.2f}° | Yaw: {yaw:.2f}°"
        cv2.putText(corrected, text, (30, 40), cv2.FONT_HERSHEY_SIMPLEX, 1.0, (255, 255, 255), 2)

    return corrected


def load_distance_csv():
    csv_path = filedialog.askopenfilename(title="Selecciona el CSV de distancias", filetypes=[("CSV", "*.csv")])
    if not csv_path:
        print("⚠️ No se seleccionó CSV de distancias. Continuando sin datos.")
        return None
    df = pd.read_csv(csv_path, dtype={"timestamp": float, "side": float, "top": float, "bottom": float})
    df = df.sort_values("timestamp").reset_index(drop=True)
    print("[DEBUG] Primeros timestamps del CSV:")
    print(df.head())
    return df

def find_closest_average(df, target_ts, k=3):
    if df is None or len(df) < k:
        return None
    df_temp = df.copy()
    df_temp["abs_diff"] = np.abs(df_temp["timestamp"] - target_ts)
    closest = df_temp.nsmallest(k, "abs_diff")
    print(f"[DEBUG] Frame timestamp: {target_ts:.3f}")
    print("[DEBUG] Muestras más cercanas:")
    print(closest[["timestamp", "abs_diff", "side", "top", "bottom"]])
    avg = closest[["side", "top", "bottom"]].mean().to_dict()
    return avg

# === Cargar datos ===
drone_data = parse_srt_by_frame(srt_path) if os.path.exists(srt_path) else {}
distance_df = load_distance_csv()
waypoints = []

cap = cv2.VideoCapture(video_path)
fps = cap.get(cv2.CAP_PROP_FPS)
total_frames = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))
frame_index = 0
paused = True

commands_text = [
    "[ESPACIO] Play / Pausa",
    "[D] Avanzar frame",
    "[A] Retroceder frame",
    "[W] Guardar waypoint",
    "[Q] Salir"
]

while cap.isOpened():
    ret, frame = cap.read()
    if not ret:
        break
    frame_index = int(cap.get(cv2.CAP_PROP_POS_FRAMES))
    pos_data = drone_data.get(frame_index)

    if pos_data:
        lat = pos_data["lat"]
        lon = pos_data["lon"]
        alt = pos_data["alt"]
        gb_yaw = pos_data["gb_yaw"]
        gb_pitch = pos_data["gb_pitch"]
        gb_roll = pos_data["gb_roll"]
        unix_ts = pos_data["unix_ts"]

        cv2.putText(frame, f"FRAME: {frame_index}", (10, 30), cv2.FONT_HERSHEY_SIMPLEX, 0.6, (255,255,255), 2)
        cv2.putText(frame, f"GPS: {lat:.6f}, {lon:.6f}, {alt:.1f}m", (10, 60), cv2.FONT_HERSHEY_SIMPLEX, 0.6, (0,255,0), 2)
        cv2.putText(frame, f"GIMBAL: yaw:{gb_yaw:.1f} pitch:{gb_pitch:.1f} roll:{gb_roll:.1f}", (10, 90), cv2.FONT_HERSHEY_SIMPLEX, 0.6, (0,255,0), 2)

        if unix_ts and distance_df is not None:
            avg = find_closest_average(distance_df, unix_ts)
            if avg:
                cv2.putText(frame, f"SIDE: {avg['side']:.1f} mm", (10, 120), cv2.FONT_HERSHEY_SIMPLEX, 0.6, (255,255,0), 2)
                cv2.putText(frame, f"TOP : {avg['top']:.1f} mm", (10, 150), cv2.FONT_HERSHEY_SIMPLEX, 0.6, (255,255,0), 2)
                cv2.putText(frame, f"BOTTOM: {avg['bottom']:.1f} mm", (10, 180), cv2.FONT_HERSHEY_SIMPLEX, 0.6, (255,255,0), 2)

    for i, line in enumerate(commands_text):
        cv2.putText(frame, line, (10, 210 + i * 30), cv2.FONT_HERSHEY_SIMPLEX, 0.7, (255,255,255), 2)

    cv2.imshow("Video", frame)

    key = cv2.waitKey(0 if paused else int(1000 / fps)) & 0xFF
    if key == ord('q'):
        break
    elif key == ord(' '):
        paused = not paused
    elif key == ord('d'):
        paused = True
        frame_index = min(frame_index + 1, total_frames - 1)
        cap.set(cv2.CAP_PROP_POS_FRAMES, frame_index)
    elif key == ord('a'):
        paused = True
        frame_index = max(frame_index - 1, 0)
        cap.set(cv2.CAP_PROP_POS_FRAMES, frame_index)
    elif key == ord('w'):
        gps = drone_data.get(frame_index)
        if gps:
            avg = find_closest_average(distance_df, gps["unix_ts"]) if distance_df is not None else {}
            d_bottom = avg.get("bottom", 0)
            d_side = avg.get("side", 0)
            d_top = avg.get("top", 0)
            pitch_deg, yaw_deg, normal = calcular_inclinacion_pared(d_bottom, d_side, d_top)
            normal_camara = rotar_normal_a_sistema_camara(normal, gps["gb_yaw"], gps["gb_pitch"], gps["gb_roll"])
            img_corrected = corregir_perspectiva(frame, normal_camara)
            img_path = f"{base}_frame_{frame_index:04d}_corr.jpg"
            cv2.imwrite(img_path, img_corrected)
            print(f"🖼️ Imagen corregida guardada en {img_path}")
            waypoint = {
                "frame": frame_index,
                "yaw": gps["gb_yaw"],
                "pitch": gps["gb_pitch"],
                "roll": gps["gb_roll"],
                "side": d_side,
                "top": d_top,
                "bottom": d_bottom,
                "normal_x": normal_camara[0],
                "normal_y": normal_camara[1],
                "normal_z": normal_camara[2]
            }
            waypoints.append(waypoint)
            print(f"✅ Waypoint guardado: frame {frame_index} → {waypoint}")
            cv2.putText(frame, "✅ Imagen corregida y guardada", (10, frame.shape[0] - 20),
                        cv2.FONT_HERSHEY_SIMPLEX, 0.8, (0, 255, 0), 2)
            cv2.imshow("Video", frame)
            cv2.waitKey(500)
        else:
            print("⚠️ No hay datos disponibles para este frame.")

cap.release()
cv2.destroyAllWindows()

if waypoints:
    csv_path = base + "_waypoints_full.csv"
    with open(csv_path, "w", newline='') as f:
        writer = csv.DictWriter(f, fieldnames=waypoints[0].keys())
        writer.writeheader()
        writer.writerows(waypoints)
    print(f"📦 Waypoints completos exportados a {csv_path}")
