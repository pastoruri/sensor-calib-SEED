import os
import pandas as pd

# 📂 Ruta a la carpeta con los CSV
FOLDER_PATH = "data"  # <--- cámbialo

# 📄 CSV de salida
OUTPUT_FILE = "calibration_data.csv"

# 🧱 Datos promediados
data = []

# 🔁 Iterar sobre cada archivo CSV en la carpeta
for filename in os.listdir(FOLDER_PATH):
    if filename.endswith(".csv"):
        filepath = os.path.join(FOLDER_PATH, filename)
        df = pd.read_csv(filepath)

        # Verificamos columnas esperadas
        if not {'side', 'top', 'bottom'}.issubset(df.columns):
            print(f"⚠️  Archivo ignorado por columnas faltantes: {filename}")
            continue

        side_avg   = df["side"].mean()
        top_avg    = df["top"].mean()
        bottom_avg = df["bottom"].mean()  # Este es Z real

        print(bottom_avg)
        data.append({
            "z_real_mm": bottom_avg,
            "side_avg_mm": side_avg,
            "top_avg_mm": top_avg
        })

# 📤 Guardar todo a un nuevo CSV
output_df = pd.DataFrame(data)
output_df.sort_values("z_real_mm", inplace=True)
output_df.to_csv(OUTPUT_FILE, index=False)

print(f"✅ Datos promediados guardados en: {OUTPUT_FILE}")
