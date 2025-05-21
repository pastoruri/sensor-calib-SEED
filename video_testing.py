import cv2
import numpy as np
import os
from tkinter import Tk, filedialog

# === Paso 1: Selección de video ===
Tk().withdraw()
video_path = filedialog.askopenfilename(title="Selecciona un video MP4", filetypes=[("Archivos MP4", "*.mp4")])
if not video_path:
    print("No se seleccionó ningún video.")
    exit()

cap = cv2.VideoCapture(video_path)
fps = cap.get(cv2.CAP_PROP_FPS)
total_frames = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))
frame_index = 0
paused = True

print("🔁 Usa [A] y [D] para navegar. [W] para aplicar corrección. [Q] para salir.")

while cap.isOpened():
    if paused:
        cap.set(cv2.CAP_PROP_POS_FRAMES, frame_index)
        ret, frame = cap.read()
        if not ret:
            print("⚠️ Fin del video.")
            break

        debug_frame = frame.copy()
        cv2.putText(debug_frame, f"Frame: {frame_index}", (20, 30), cv2.FONT_HERSHEY_SIMPLEX, 1, (255,255,255), 2)
        cv2.imshow("Frame", debug_frame)

    key = cv2.waitKey(0 if paused else int(1000/fps)) & 0xFF
    if key == ord('q'):
        break
    elif key == ord('a'):
        frame_index = max(frame_index - 1, 0)
    elif key == ord('d'):
        frame_index = min(frame_index + 1, total_frames - 1)
    elif key == ord(' '):
        paused = not paused
    elif key == ord('w'):
        # === Paso 2: Ingresar normal estimada ===
        print("📐 Ingrese la normal estimada del plano (nx, ny, nz)")
        try:
            nx = float(input("nx: "))
            ny = float(input("ny: "))
            nz = float(input("nz: "))
        except:
            print("❌ Valores inválidos.")
            continue

        #0.00233165 -0.0011155   0.99999666

        normal = np.array([nx, ny, nz])
        normal = normal / np.linalg.norm(normal)

        # === Paso 3: Calcular homografía correctiva ===

        # Suponemos que la cámara mira en dirección [0, 0, -1] (Z hacia adelante)
        view_dir = np.array([0, 0, -1])

        # Rotación entre dirección de vista y normal real
        axis = np.cross(normal, view_dir)
        angle = np.arccos(np.clip(np.dot(normal, view_dir), -1, 1))

        if np.linalg.norm(axis) < 1e-6:
            print("✅ Plano ya está alineado, sin corrección.")
            corrected = frame.copy()
        else:
            axis = axis / np.linalg.norm(axis)

            # Generar matriz de rotación (Rodrigues)
            R_vec = axis * angle
            R, _ = cv2.Rodrigues(R_vec)

            h, w = frame.shape[:2]
            K = np.array([[w, 0, w/2], [0, w, h/2], [0, 0, 1]])  # matriz intrínseca ficticia

            H = K @ R @ np.linalg.inv(K)  # homografía de rotación
            corrected = cv2.warpPerspective(frame, H, (w, h))

        # === Paso 4: Mostrar resultado ===
        side_by_side = np.hstack([cv2.resize(frame, (w//2, h//2)), cv2.resize(corrected, (w//2, h//2))])
        cv2.imshow("Corregido (derecha) vs Original (izquierda)", side_by_side)
        cv2.waitKey(0)

        # === Paso 5: Exportar imagen ===
        base = os.path.splitext(video_path)[0]
        out_path = f"{base}_frame{frame_index:04d}_rectified.png"
        cv2.imwrite(out_path, corrected)
        print(f"📸 Imagen corregida exportada: {out_path}")

cap.release()
cv2.destroyAllWindows()
