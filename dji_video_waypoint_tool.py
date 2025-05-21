import cv2
import os
import re
import csv
from math import cos, radians
from tkinter import Tk, filedialog

# === Seleccionar archivo de video ===
Tk().withdraw()  # Oculta ventana principal de Tkinter
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

    with open(path, 'r', encoding='utf-8', errors='ignore') as f:
        for i, line in enumerate(f):
            line = line.strip()

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

            # Extraer orientación del gimbal
            if "[gb_yaw:" in line:
                yaw_match   = re.search(r"\[gb_yaw:\s*([\-\d\.]+)", line)
                pitch_match = re.search(r"gb_pitch:\s*([\-\d\.]+)", line)
                roll_match  = re.search(r"gb_roll:\s*([\-\d\.]+)", line)
                if yaw_match:   gb_yaw   = float(yaw_match.group(1))
                if pitch_match: gb_pitch = float(pitch_match.group(1))
                if roll_match:  gb_roll  = float(roll_match.group(1))

            if "</font>" in line:
                if current_frame is not None:
                    pos_data[current_frame] = {
                        "lat": lat,
                        "lon": lon,
                        "alt": alt,
                        "gb_yaw": gb_yaw,
                        "gb_pitch": gb_pitch,
                        "gb_roll": gb_roll
                    }
                # Reset
                current_frame = lat = lon = alt = gb_yaw = gb_pitch = gb_roll = None

    print(f"✅ Frames con datos cargados: {len(pos_data)}")
    return pos_data


# === Conversión de coordenadas GPS a sistema local ===
def gps_to_local_coords(lat0, lon0, lat, lon, alt, scale=111320):
    x = (lon - lon0) * scale * cos(radians(lat0))
    y = (lat - lat0) * scale
    z = alt
    return (x, y, z)

# === Cargar datos GPS ===
drone_data = parse_srt_by_frame(srt_path) if os.path.exists(srt_path) else {}
waypoints = []

# === Abrir video ===
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

        cv2.putText(frame, f"FRAME: {frame_index}", (10, 30),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.6, (255, 255, 255), 2)
                    
        cv2.putText(frame, f"GPS: {lat:.6f}, {lon:.6f}, {alt:.1f}m", (10, 60),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.6, (0, 255, 0), 2)
        
        cv2.putText(frame, f"GIMBAL: yaw: {gb_yaw:.6f}, pitch: {gb_pitch:.6f}, roll: {gb_roll:.6f}m", (10, 90),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.6, (0, 255, 0), 2)
        
    for i, line in enumerate(commands_text):
        cv2.putText(frame, line, (10, 120 + i * 30),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.7, (255, 255, 255), 2)

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
            waypoints.append((frame_index, *gps))
            print(f"✅ Waypoint guardado: frame {frame_index} → {gps}")
            cv2.putText(frame, "✅ Waypoint guardado", (10, frame.shape[0] - 20),
                        cv2.FONT_HERSHEY_SIMPLEX, 0.8, (0, 255, 0), 2)
            cv2.imshow("Video", frame)
            cv2.waitKey(500)
        else:
            print("⚠️ No hay datos GPS para este frame.")
            cv2.putText(frame, "⚠️ Sin datos GPS", (10, frame.shape[0] - 20),
                        cv2.FONT_HERSHEY_SIMPLEX, 0.8, (0, 0, 255), 2)
            cv2.imshow("Video", frame)
            cv2.waitKey(1000)

cap.release()
cv2.destroyAllWindows()

# === Exportar waypoints ===
if waypoints:
    csv_path = base + "_waypoints.csv"
    local_path = base + "_waypoints_local.csv"

    with open(csv_path, "w", newline='') as f:
        writer = csv.writer(f)
        writer.writerow(["frame", "lat", "lon", "alt"])
        writer.writerows(waypoints)
    print(f"📦 Waypoints exportados a {csv_path}")

    # Exportar en sistema local
    lat0, lon0 = waypoints[0][1], waypoints[0][2]
    local_coords = [(f, *gps_to_local_coords(lat0, lon0, lat, lon, alt)) for f, lat, lon, alt in waypoints]

    with open(local_path, "w", newline='') as f:
        writer = csv.writer(f)
        writer.writerow(["frame", "x", "y", "z"])
        writer.writerows(local_coords)
    print(f"📦 Coordenadas locales exportadas a {local_path}")
