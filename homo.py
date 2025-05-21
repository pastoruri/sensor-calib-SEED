import cv2
import numpy as np
from math import sin, cos, radians
from tkinter import filedialog, Tk

Tk().withdraw()
img_path = filedialog.askopenfilename(title="Selecciona una imagen", filetypes=[("Imagen", "*.jpg *.png *.jpeg")])
if not img_path:
    print("No se seleccionó ninguna imagen.")
    exit()

imagen = cv2.imread(img_path)
H, W = imagen.shape[:2]
fx = fy = 1000
cx, cy = W / 2, H / 2
K = np.array([[fx, 0, cx], [0, fy, cy], [0, 0, 1]])

def on_change(val): pass

cv2.namedWindow("Homografía interactiva")
cv2.createTrackbar("Yaw (-90° a +90°)", "Homografía interactiva", 90, 180, on_change)
cv2.createTrackbar("Pitch (-90° a +90°)", "Homografía interactiva", 90, 180, on_change)

while True:
    yaw_deg = cv2.getTrackbarPos("Yaw (-90° a +90°)", "Homografía interactiva") - 90
    pitch_deg = cv2.getTrackbarPos("Pitch (-90° a +90°)", "Homografía interactiva") - 90

    pitch = radians(pitch_deg)
    yaw = radians(yaw_deg)

    normal = np.array([
        sin(yaw),
        sin(pitch),
        cos(yaw) * cos(pitch)
    ])
    normal /= np.linalg.norm(normal)

    z_axis = normal
    x_axis = np.cross([0, 1, 0], z_axis)
    x_axis /= np.linalg.norm(x_axis)
    y_axis = np.cross(z_axis, x_axis)
    R = np.vstack([x_axis, y_axis, z_axis]).T
    H_matrix = K @ R.T @ np.linalg.inv(K)

    # Proyección en canvas grande
    corregida_grande = cv2.warpPerspective(imagen, H_matrix, (int(W * 2), int(H * 2)))

    # Encontrar el contenido visible
    gray = cv2.cvtColor(corregida_grande, cv2.COLOR_BGR2GRAY)
    coords = cv2.findNonZero(cv2.threshold(gray, 1, 255, cv2.THRESH_BINARY)[1])
    x, y, w, h = cv2.boundingRect(coords)

    # Crop dinámico y resize proporcional
    recortada = corregida_grande[y:y+h, x:x+w]
    escala = min(W / w, H / h)
    resized = cv2.resize(recortada, (int(w * escala), int(h * escala)))

    # Centrar en canvas original
    canvas = np.zeros((H, W, 3), dtype=np.uint8)
    oy = (H - resized.shape[0]) // 2
    ox = (W - resized.shape[1]) // 2
    canvas[oy:oy+resized.shape[0], ox:ox+resized.shape[1]] = resized

    texto = f"Yaw: {yaw_deg}°, Pitch: {pitch_deg}°"
    cv2.putText(canvas, texto, (10, 30), cv2.FONT_HERSHEY_SIMPLEX, 1, (0, 255, 255), 2)
    cv2.imshow("Homografía interactiva", canvas)

    key = cv2.waitKey(30)
    if key == 27 or key == ord('q'):
        break

cv2.destroyAllWindows()
