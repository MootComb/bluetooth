#!/usr/bin/env python3
from pydbus import SystemBus
from gi.repository import GLib
from flask import Flask, jsonify, request
from flask_cors import CORS
from threading import Thread
import signal
import sys
import dbus
import time

app = Flask(__name__)
CORS(app) 
bus = SystemBus()
loop = GLib.MainLoop()

BLUEZ_SERVICE = 'org.bluez'
ADAPTER_INTERFACE = 'org.bluez.Adapter1'
DEVICE_INTERFACE = 'org.bluez.Device1'

class BluetoothManager:
    def __init__(self):
        self.adapter_path = None
        self.adapter = None
        self.devices = {}
        self.is_discovering = False  # Флаг для отслеживания состояния обнаружения
        self.update_adapter()
        self.auto_scan_thread = Thread(target=self.auto_scan, daemon=True)
        self.auto_scan_thread.start()
    
    def update_adapter(self):
        try:
            manager = bus.get(BLUEZ_SERVICE, '/')
            objects = manager.GetManagedObjects()
            for path, interfaces in objects.items():
                if ADAPTER_INTERFACE in interfaces:
                    self.adapter_path = path
                    self.adapter = bus.get(BLUEZ_SERVICE, path)
                    return True
            return False
        except Exception as e:
            print(f"Ошибка адаптера: {e}")
            return False

    def get_adapter_properties(self):
        if not self.adapter:
            if not self.update_adapter():
                return None
        try:
            return self.adapter.GetAll(ADAPTER_INTERFACE)
        except Exception as e:
            print(f"Ошибка свойств: {e}")
            return None

    def start_discovery(self, duration=15):
        if self.is_discovering:
            print("Обнаружение уже запущено.")
            return False  # Не запускаем, если уже идет обнаружение
        try:
            if not self.adapter and not self.update_adapter():
                print("Адаптер не доступен.")
                return False
            print("Начало обнаружения устройств...")
            self.is_discovering = True  # Устанавливаем флаг
            self.adapter.StartDiscovery()
            time.sleep(duration)
            self.adapter.StopDiscovery()
            print("Обнаружение завершено.")
            self.is_discovering = False  # Сбрасываем флаг
            return True
        except Exception as e:
            print(f"Ошибка обнаружения: {e}")
            self.is_discovering = False  # Сбрасываем флаг в случае ошибки
            return False

    def refresh_devices(self):
        try:
            manager = bus.get(BLUEZ_SERVICE, '/')
            objects = manager.GetManagedObjects()
            self.devices = {}
            for path, interfaces in objects.items():
                if DEVICE_INTERFACE in interfaces:
                    self.devices[path] = {
                        'interface': bus.get(BLUEZ_SERVICE, path),
                        'properties': interfaces[DEVICE_INTERFACE]
                    }
            return True
        except Exception as e:
            print(f"Ошибка обновления: {e}")
            return False

    def auto_scan(self, interval=30):
        while True:
            self.start_discovery(duration=10)  # Сканируем устройства на 10 секунд
            self.refresh_devices()
            time.sleep(interval)  # Ждем заданный интервал перед следующим сканированием

    def connect_device(self, device_path):
        try:
            if device_path not in self.devices:
                self.refresh_devices()
                if device_path not in self.devices:
                    return False, "Устройство не найдено"
            self.devices[device_path]['interface'].Connect()
            time.sleep(1)
            self.refresh_devices()
            return True, "Успешно подключено"
        except dbus.exceptions.DBusException as e:
            return False, str(e)

    def disconnect_device(self, device_path):
        try:
            if device_path not in self.devices:
                return False, "Устройство не найдено"
            self.devices[device_path]['interface'].Disconnect()
            time.sleep(1)
            self.refresh_devices()
            return True, "Успешно отключено"
        except dbus.exceptions.DBusException as e:
            return False, str(e)

    def pair_device(self, device_path):
        try:
            if device_path not in self.devices:
                return False, "Устройство не найдено"
            self.devices[device_path]['interface'].Pair()
            time.sleep(1)
            self.refresh_devices()
            return True, "Успешно спарено"
        except dbus.exceptions.DBusException as e:
            return False, str(e)

    def remove_device(self, device_path):
        try:
            if not self.adapter and not self.update_adapter():
                return False, "Адаптер недоступен"
            self.adapter.RemoveDevice(device_path)
            self.refresh_devices()
            return True, "Устройство удалено"
        except Exception as e:
            print(f"Ошибка удаления: {e}")
            return False, str(e)

bluetooth = BluetoothManager()

# API Эндпоинты
@app.route('/api/v1/adapter', methods=['GET'])
def get_adapter():
    props = bluetooth.get_adapter_properties()
    if not props:
        return jsonify({"error": "Адаптер недоступен"}), 503
    return jsonify(props)

@app.route('/api/v1/devices', methods=['GET'])
def get_devices():
    bluetooth.refresh_devices()
    devices = []
    for path, data in bluetooth.devices.items():
        device = {
            "path": path,
            "properties": data['properties']
        }
        devices.append(device)
    return jsonify({"devices": devices})

@app.route('/api/v1/devices/scan', methods=['POST'])
def scan_devices():
    try:
        duration = request.json.get('duration', 15)
        if not isinstance(duration, int) or duration < 1 or duration > 60:
            return jsonify({"error": "Неверная продолжительность (1-60с)"}), 400
        if not bluetooth.start_discovery(duration):
            return jsonify({"error": "Не удалось обнаружить устройства"}), 500
        bluetooth.refresh_devices()
        return jsonify({
            "status": "success",
            "devices_found": len(bluetooth.devices)
        })
    except Exception as e:
        print(f"Ошибка в сканировании: {e}")
        return jsonify({"error": str(e)}), 500

@app.route('/api/v1/devices/connect', methods=['POST'])
def connect():
    try:
        device_path = request.json.get('device_path')
        if not device_path:
            return jsonify({"error": "Требуется путь устройства"}), 400
        success, message = bluetooth.connect_device(device_path)
        if success:
            return jsonify({"status": "подключено"})
        return jsonify({"error": message}), 400
    except Exception as e:
        return jsonify({"error": str(e)}), 500

@app.route('/api/v1/devices/disconnect', methods=['POST'])
def disconnect():
    try:
        device_path = request.json.get('device_path')
        if not device_path:
            return jsonify({"error": "Требуется путь устройства"}), 400  
        success, message = bluetooth.disconnect_device(device_path)
        if success:
            return jsonify({"status": "отключено"})
        return jsonify({"error": message}), 400
    except Exception as e:
        return jsonify({"error": str(e)}), 500

@app.route('/api/v1/devices/pair', methods=['POST'])
def pair():
    try:
        device_path = request.json.get('device_path')
        if not device_path:
            return jsonify({"error": "Требуется путь устройства"}), 400
        success, message = bluetooth.pair_device(device_path)
        if success:
            return jsonify({"status": "спарено"})
        return jsonify({"error": message}), 400
    except Exception as e:
        return jsonify({"error": str(e)}), 500

@app.route('/api/v1/devices/remove', methods=['POST'])
def remove():
    try:
        device_path = request.json.get('device_path')
        if not device_path:
            return jsonify({"error": "Требуется путь устройства"}), 400
        success, message = bluetooth.remove_device(device_path)
        if success:
            return jsonify({"status": "удалено"})
        return jsonify({"error": message}), 400
    except Exception as e:
        return jsonify({"error": str(e)}), 500

@app.route('/api/v1/status', methods=['GET'])
def status():
    return jsonify({"status": "OK"}), 200

def run_server():
    app.run(host='0.0.0.0', port=5000, threaded=True)

def shutdown(signum, frame):
    print("Выключение...")
    loop.quit()
    sys.exit(0)

if __name__ == '__main__':
    signal.signal(signal.SIGINT, shutdown)
    signal.signal(signal.SIGTERM, shutdown)
    
    server_thread = Thread(target=run_server, daemon=True)
    server_thread.start()
    
    print("Сервер Bluetooth API запущен на http://0.0.0.0:5000")
    
    try:
        loop.run()
    except (KeyboardInterrupt, SystemExit):
        pass
