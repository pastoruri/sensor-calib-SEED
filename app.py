import re
import sys
import time
import queue
import threading
import asyncio
import csv
import datetime

from PyQt5.QtWidgets import (
    QApplication, QWidget, QVBoxLayout, QHBoxLayout,
    QLabel, QSpinBox, QPushButton, QTextEdit
)
from PyQt5.QtCore import QTimer
from bleak import BleakScanner, BleakClient

SERVICE_UUID = "12345678-1234-1234-1234-1234567890ab"
CHAR_UUID    = "abcd1234-5678-90ab-cdef-1234567890ab"
ESP32_ADDR   = "1773840C-16AD-9822-65C7-87488BCE5B7C"

SAMPLE_EX = "1747410717.502,122,397,260"
SAMPLE_SIZE = len(SAMPLE_EX)

class BLEManager:
    def __init__(self, msg_q):
        self.msg_q = msg_q
        self.loop   = asyncio.new_event_loop()
        self.client = None
        threading.Thread(target=self._run_loop, daemon=True).start()

    def _run_loop(self):
        asyncio.set_event_loop(self.loop)
        self.loop.run_forever()

    def connect(self):
        asyncio.run_coroutine_threadsafe(self._connect(), self.loop)

    async def _connect(self):
        self.msg_q.put("Buscando ESP32...")
        devices = await BleakScanner.discover(timeout=5.0)
        target = next((d for d in devices if d.address.upper() == ESP32_ADDR.upper()), None)
        if not target:
            self.msg_q.put("No se encontró ESP32 por dirección")
            return
        self.msg_q.put(f"Intentando conectar a {target.address}")
        self.client = BleakClient(target.address)
        try:
            await self.client.connect()
            self.msg_q.put("Conectado al ESP32")
            await self.client.start_notify(CHAR_UUID, self._notification_handler)
        except Exception as e:
            self.msg_q.put(f"Error BLE: {e}")

    def _notification_handler(self, sender, data):
        text = data.decode("utf-8").strip()
        self.msg_q.put(text)

    async def _send(self, cmd):
        if self.client and self.client.is_connected:
            self.msg_q.put(f"DBG: enviando '{cmd}'")
            try:
                await self.client.write_gatt_char(CHAR_UUID, cmd.encode("utf-8"), response=True)
                self.msg_q.put(f"DBG: '{cmd}' enviado (request)")
            except Exception as e:
                self.msg_q.put(f"DBG: error al enviar: {e}")
        else:
            self.msg_q.put("No conectado. Presiona 'Conectar ESP32' primero.")

    def send(self, cmd):
        asyncio.run_coroutine_threadsafe(self._send(cmd), self.loop)

    def is_connected(self):
        return bool(self.client and self.client.is_connected)

    def close(self):
        if self.client:
            asyncio.run_coroutine_threadsafe(self.client.disconnect(), self.loop)

class MainWindow(QWidget):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("Sync BLE Clock – PyQt5")
        self.msg_q = queue.Queue()
        self.ble    = BLEManager(self.msg_q)
        self.csv_writing = False
        self.csv_file = None
        self.csv_writer = None
        self._build_ui()
        self._start_timer()

    def _build_ui(self):
        vbox = QVBoxLayout(self)

        h_params = QHBoxLayout()
        h_params.addWidget(QLabel("Buffer:"))
        self.spin_buffer = QSpinBox(); self.spin_buffer.setRange(1, 4000); self.spin_buffer.setValue(100)
        h_params.addWidget(self.spin_buffer)
        h_params.addWidget(QLabel("Hz:"))
        self.spin_freq = QSpinBox(); self.spin_freq.setRange(1, 10); self.spin_freq.setValue(2)
        h_params.addWidget(self.spin_freq)
        vbox.addLayout(h_params)

        h_buttons = QHBoxLayout()
        self.btn_connect = QPushButton("Conectar ESP32"); self.btn_connect.clicked.connect(self.on_connect)
        self.btn_verify  = QPushButton("Verificar Conexión"); self.btn_verify.clicked.connect(self.verify)
        self.btn_mem     = QPushButton("Obtener Memoria Libre"); self.btn_mem.clicked.connect(self.get_memory)
        self.btn_sync    = QPushButton("Sincronizar Tiempo"); self.btn_sync.clicked.connect(self.sync)
        self.btn_fetch   = QPushButton("Obtener Datos"); self.btn_fetch.clicked.connect(self.fetch)
        self.btn_reset   = QPushButton("Reiniciar ESP32"); self.btn_reset.clicked.connect(self.reset)
        self.btn_update  = QPushButton("Actualizar Configuración"); self.btn_update.clicked.connect(self.update)
        self.btn_clear   = QPushButton("Reiniciar GUI"); self.btn_clear.clicked.connect(self.reset_gui)
        for btn in (self.btn_connect, self.btn_verify, self.btn_mem,
                    self.btn_sync, self.btn_fetch,
                    self.btn_reset, self.btn_update,
                    self.btn_clear):
            h_buttons.addWidget(btn)
        vbox.addLayout(h_buttons)

        self.label_status = QLabel("Estado: desconectado")
        vbox.addWidget(self.label_status)
        self.label_mem    = QLabel("Muestras posibles: N/A")
        vbox.addWidget(self.label_mem)

        self.text_log = QTextEdit(readOnly=True)
        vbox.addWidget(self.text_log)

    def _start_timer(self):
        self.timer = QTimer(self)
        self.timer.timeout.connect(self._process_queue)
        self.timer.start(200)

    def on_connect(self):
        self.btn_connect.setEnabled(False)
        self.ble.connect()
        self.label_status.setText("Estado: buscando dispositivo...")

    def verify(self):
        if self.ble.is_connected():
            self.label_status.setText("Estado: ✅ Conectado")
        else:
            self.label_status.setText("Estado: ❌ No conectado")
            self.btn_connect.setEnabled(True)

    def get_memory(self):
        self.ble.send("GET_MEM")
        self.label_status.setText("Estado: solicitando memoria...")

    def sync(self):
        self.btn_sync.setEnabled(False)
        now = datetime.datetime.now()
        ts = now.strftime("%Y-%m-%d %H:%M:%S") + f".{now.microsecond//1000:03d}"
        self.ble.send(f"SYNC:{ts}")
        self.label_status.setText("Estado: sincronizando…")

    def update(self):
        self.btn_update.setEnabled(False)
        buf, freq = self.spin_buffer.value(), self.spin_freq.value()
        self.ble.send(f"SET:{buf},{freq}")
        self.label_status.setText("Estado: configurando…")

    def fetch(self):
        self.btn_fetch.setEnabled(False)
        fname = f"esp32_data_{time.strftime('%Y%m%d_%H%M%S')}.csv"
        try:
            self.csv_file = open(fname, "w", newline="", encoding="utf-8")
            self.csv_writer = csv.writer(self.csv_file)
            self.csv_writer.writerow(["timestamp","side","top","bottom"])
            self.text_log.append(f"Guardando datos en {fname}")
            self.csv_writing = True
        except Exception as e:
            self.text_log.append(f"Error al crear CSV: {e}")
            self.csv_writing = False
        self.ble.send("FETCH")
        self.label_status.setText("Estado: solicitando…")

    def reset(self):
        self.btn_reset.setEnabled(False)
        if self.csv_writing:
            self.csv_file.close()
            self.csv_writing = False
        self.ble.send("RESET")
        self.label_status.setText("Estado: reiniciando…")

    def reset_gui(self):
        if self.csv_writing:
            self.csv_file.close()
        self.csv_writing = False
        self.csv_file = None
        self.csv_writer = None
        self.text_log.clear()
        self.label_status.setText("Estado: desconectado")
        self.label_mem.setText("Muestras posibles: N/A")
        for btn in (self.btn_connect, self.btn_verify, self.btn_mem,
                    self.btn_sync, self.btn_fetch,
                    self.btn_reset, self.btn_update):
            btn.setEnabled(True)

    def _process_queue(self):
        while not self.msg_q.empty():
            msg = self.msg_q.get().strip()

            if msg.startswith("WAIT_ACK:"):
                block_id = msg.split(":")[1]
                self.ble.send(f"ACK:BLOCK_{block_id}")
                self.text_log.append(f"🟨 WAIT_ACK:{block_id} → ACK:BLOCK_{block_id}")
                continue

            if msg == "END":
                self.ble.send("ACK:BLOCK_9999")
                if self.csv_writing:
                    self.csv_file.close()
                    self.csv_writing = False
                    self.text_log.append("✅ CSV cerrado tras END")
                continue

            if msg.startswith("ESP32 libre:"):
                self.label_mem.setText(msg)
                continue

            if msg.startswith("FREE_HEAP:"):
                _, val = msg.split(":",1)
                free_bytes = int(val)
                free_samples = free_bytes // SAMPLE_SIZE
                self.label_mem.setText(f"Muestras posibles: {free_samples}")
                continue

            if msg.startswith("ACK:"):
                ack = msg.split(":",1)[1]
                self.text_log.append(f"✅ {msg}")
                if ack == "SYNC":
                    self.btn_sync.setEnabled(True)
                    self.label_status.setText("Estado: SYNC confirmado")
                elif ack == "SET":
                    self.btn_update.setEnabled(True)
                    self.label_status.setText("Estado: SET confirmado")
                elif ack == "FETCH":
                    self.btn_fetch.setEnabled(True)
                    self.label_status.setText("Estado: FETCH confirmado")
                elif ack == "RESET":
                    self.btn_reset.setEnabled(True)
                    self.label_status.setText("Estado: RESET confirmado")
                continue

            if msg.startswith(("Buscando","Intentando","Conectado","Error","No se encontró","DBG:")):
                self.label_status.setText(f"Estado: {msg}")
            else:
                self.text_log.append(msg)
                if self.csv_writing:
                    parts = msg.split(",")
                    if len(parts) in (4, 5):
                        try:
                            float(parts[1]); int(parts[-3]); int(parts[-2]); int(parts[-1])
                            self.csv_writer.writerow(parts[1:] if len(parts) == 5 else parts)
                        except ValueError:
                            pass

    def closeEvent(self, event):
        if self.csv_writing:
            self.csv_file.close()
        self.ble.close()
        super().closeEvent(event)

def main():
    app = QApplication(sys.argv)
    win = MainWindow()
    win.show()
    sys.exit(app.exec_())

if __name__ == "__main__":
    main()
