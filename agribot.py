#!/usr/bin/env python3
"""
AGRIBOT RASPBERRY PI ZERO 2 W - ULTIMATE COMPLETE SYSTEM (MQTT VERSION - FIXED)
Features: Offline Bluetooth Control, Auto Recording, Theft Detection,
Auto Charging, Battery Monitoring, GPS Tracking, GSM Alerts
"""

import asyncio
import cv2
import numpy as np
import serial
import json
import time
import os
import shutil
from datetime import datetime
from threading import Thread
import requests
import re
from aiomqtt import Client  # pip install aiomqtt

# ===================== CONFIGURATION =====================
ARDUINO_PORT = '/dev/ttyACM0'
ARDUINO_BAUD = 9600

GSM_PORT = '/dev/ttyUSB0'
GSM_BAUD = 9600

GPS_PORT = '/dev/ttyAMA0'
GPS_BAUD = 9600

ALERT_PHONE = "01603320208"

CAMERA_INDEX = 0
VIDEO_WIDTH = 640
VIDEO_HEIGHT = 480
VIDEO_FPS = 20

# MQTT Configuration
MQTT_BROKER = "test.mosquitto.org"
MQTT_PORT = 1883
MQTT_CONTROL_TOPIC = "agribot/control"
MQTT_STATUS_TOPIC = "agribot/status"
MQTT_RESPONSE_TOPIC = "agribot/response"
MQTT_LOGS_TOPIC = "agribot/logs"

BASE_DIR = "~/agribot_data"
EVIDENCE_DIR = f"{BASE_DIR}/evidence"
RECORDING_DIR = f"{BASE_DIR}/recordings"
ACTIVITY_LOG_FILE = f"{BASE_DIR}/activity_log.txt"

os.makedirs(EVIDENCE_DIR, exist_ok=True)
os.makedirs(RECORDING_DIR, exist_ok=True)

AUTO_CHARGE_LOCATION = {"lat": 0.0, "lon": 0.0}
CHARGE_LOCATION_FILE = f"{BASE_DIR}/charge_location.json"

BATTERY_LOW_THRESHOLD = 30
BATTERY_CRITICAL_THRESHOLD = 20
THEFT_HEIGHT_THRESHOLD = 4

OPENROUTER_API_KEY = "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"
OPENROUTER_API_URL = "https://openrouter.ai/api/v1/chat/completions"
AI_MODEL = "meta-llama/llama-3.1-8b-instruct:free"

WIFI_CONFIG_FILE = "/etc/wpa_supplicant/wpa_supplicant.conf"

# ===================== ACTIVITY LOGGER =====================
class ActivityLogger:
    def __init__(self):
        self.logs = []
        self.max_logs = 100
        
    def log(self, message):
        timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        log_entry = f"[{timestamp}] {message}"
        self.logs.append(log_entry)
        
        if len(self.logs) > self.max_logs:
            self.logs.pop(0)
        
        with open(ACTIVITY_LOG_FILE, 'a') as f:
            f.write(log_entry + '\n')
        
        print(log_entry)
        return log_entry
    
    def get_recent_logs(self, count=20):
        return self.logs[-count:]
    
    def clear_old_logs(self):
        if os.path.exists(ACTIVITY_LOG_FILE):
            with open(ACTIVITY_LOG_FILE, 'r') as f:
                lines = f.readlines()
            with open(ACTIVITY_LOG_FILE, 'w') as f:
                f.writelines(lines[-50:])

activity_log = ActivityLogger()

# ===================== STORAGE MANAGER =====================
class StorageManager:
    def __init__(self):
        self.recording_active = False
        self.video_writer = None
        self.current_recording = None
        
    def get_storage_info(self):
        total, used, free = shutil.disk_usage("/")
        return {
            "total_gb": total // (2**30),
            "used_gb": used // (2**30),
            "free_gb": free // (2**30),
            "percent_used": (used / total) * 100
        }
    
    def clear_old_recordings(self, keep_recent=10):
        try:
            files = sorted(
                [f for f in os.listdir(RECORDING_DIR) if f.endswith('.avi')],
                key=lambda x: os.path.getctime(os.path.join(RECORDING_DIR, x)),
                reverse=True
            )
            
            deleted = 0
            for old_file in files[keep_recent:]:
                os.remove(os.path.join(RECORDING_DIR, old_file))
                activity_log.log(f"Deleted old recording: {old_file}")
                deleted += 1
            
            return deleted
        except Exception as e:
            activity_log.log(f"Error clearing recordings: {e}")
            return 0
    
    def start_continuous_recording(self, camera):
        try:
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            filename = f"{RECORDING_DIR}/recording_{timestamp}.avi"
            
            fourcc = cv2.VideoWriter_fourcc(*'XVID')
            self.video_writer = cv2.VideoWriter(filename, fourcc, VIDEO_FPS, (VIDEO_WIDTH, VIDEO_HEIGHT))
            self.current_recording = filename
            self.recording_active = True
            
            activity_log.log(f"Started recording: {filename}")
            return filename
        except Exception as e:
            activity_log.log(f"Recording start error: {e}")
            return None
    
    def stop_recording(self):
        if self.video_writer:
            self.video_writer.release()
            self.recording_active = False
            activity_log.log(f"Stopped recording: {self.current_recording}")
    
    def record_frame(self, frame):
        if self.recording_active and self.video_writer:
            self.video_writer.write(frame)

# ===================== HARDWARE MANAGER =====================
class HardwareManager:
    def __init__(self):
        self.battery_level = 100
        self.charging_status = "Not Charging"
        self.charging_source = None
        
        try:
            self.arduino = serial.Serial(ARDUINO_PORT, ARDUINO_BAUD, timeout=1)
            activity_log.log("✓ Arduino connected")
        except Exception as e:
            activity_log.log(f"✗ Arduino error: {e}")
            self.arduino = None
        
        try:
            self.gsm = serial.Serial(GSM_PORT, GSM_BAUD, timeout=1)
            self.init_gsm()
            activity_log.log("✓ GSM connected")
        except Exception as e:
            activity_log.log(f"✗ GSM error: {e}")
            self.gsm = None
        
        try:
            self.gps = serial.Serial(GPS_PORT, GPS_BAUD, timeout=1)
            activity_log.log("✓ GPS connected")
        except Exception as e:
            activity_log.log(f"✗ GPS error: {e}")
            self.gps = None
        
        try:
            self.camera = cv2.VideoCapture(CAMERA_INDEX)
            self.camera.set(cv2.CAP_PROP_FRAME_WIDTH, VIDEO_WIDTH)
            self.camera.set(cv2.CAP_PROP_FRAME_HEIGHT, VIDEO_HEIGHT)
            activity_log.log("✓ Camera connected")
        except Exception as e:
            activity_log.log(f"✗ Camera error: {e}")
            self.camera = None
    
    def init_gsm(self):
        if not self.gsm:
            return
        time.sleep(2)
        self.gsm.write(b'AT\r\n')
        time.sleep(1)
        self.gsm.write(b'AT+CMGF=1\r\n')
        time.sleep(1)
    
    def send_command_to_arduino(self, command):
        if self.arduino:
            try:
                self.arduino.write((command + '\n').encode())
                activity_log.log(f"→ Arduino: {command}")
            except Exception as e:
                activity_log.log(f"Arduino write error: {e}")
    
    def read_arduino_data(self):
        if self.arduino and self.arduino.in_waiting:
            try:
                line = self.arduino.readline().decode().strip()
                return line
            except:
                pass
        return None
    
    def send_sms(self, phone, message):
        if not self.gsm:
            return False
        try:
            self.gsm.write(f'AT+CMGS="{phone}"\r\n'.encode())
            time.sleep(1)
            self.gsm.write(f'{message}\x1A'.encode())
            time.sleep(2)
            activity_log.log(f"✓ SMS sent: {message}")
            return True
        except Exception as e:
            activity_log.log(f"SMS error: {e}")
            return False
    
    def make_call(self, phone):
        if not self.gsm:
            return False
        try:
            self.gsm.write(f'ATD{phone};\r\n'.encode())
            time.sleep(5)
            activity_log.log(f"✓ Called {phone}")
            return True
        except Exception as e:
            activity_log.log(f"Call error: {e}")
            return False
    
    def read_gps(self):
        if self.gps and self.gps.in_waiting:
            try:
                line = self.gps.readline().decode().strip()
                if line.startswith('$GPGGA'):
                    parts = line.split(',')
                    if len(parts) > 5 and parts[2] and parts[4]:
                        return {"lat": parts[2], "lon": parts[4]}
            except:
                pass
        return None
    
    def get_camera_frame(self):
        if self.camera:
            ret, frame = self.camera.read()
            if ret:
                return frame
        return None
    
    def capture_photo(self, filename):
        frame = self.get_camera_frame()
        if frame is not None:
            cv2.imwrite(filename, frame)
            activity_log.log(f"✓ Photo: {filename}")
            return True
        return False
    
    def update_battery_status(self, level, charging=False, source=None):
        self.battery_level = level
        if charging:
            self.charging_status = "Charging"
            self.charging_source = source
        else:
            self.charging_status = "Not Charging"
            self.charging_source = None

# ===================== AI VOICE ASSISTANT =====================
class AIAssistant:
    def __init__(self, hardware, sensors):
        self.hardware = hardware
        self.sensors = sensors
        self.conversation_history = []
        self.enabled = True
        self.use_google_fallback = True
        
    async def process_voice_command(self, user_input):
        if not self.enabled:
            return "AI mode disabled"
        
        try:
            sensor_context = f"""Temperature: {self.sensors.latest_data['temp']}°C
Humidity: {self.sensors.latest_data['humidity']}%
Soil: {self.sensors.latest_data['soil']}
Battery: {self.hardware.battery_level}%
Fire: {self.sensors.latest_data['fire']}
Theft: {self.sensors.latest_data['theft']}"""
            
            messages = [
                {
                    "role": "system",
                    "content": f"""You are Agribot AI. Control commands: FORWARD, BACKWARD, LEFT, RIGHT, STOP, PUMP_ON, PUMP_OFF, GRASS_ON, GRASS_OFF, SEED_ON, SEED_OFF.
Status: {sensor_context}
Include commands in [BRACKETS] like [FORWARD]."""
                }
            ]
            
            messages.extend(self.conversation_history[-5:])
            messages.append({"role": "user", "content": user_input})
            
            headers = {
                "Authorization": f"Bearer {OPENROUTER_API_KEY}",
                "Content-Type": "application/json"
            }
            
            payload = {
                "model": AI_MODEL,
                "messages": messages,
                "max_tokens": 150,
                "temperature": 0.7
            }
            
            response = requests.post(OPENROUTER_API_URL, headers=headers, json=payload, timeout=10)
            
            if response.status_code == 200:
                ai_response = response.json()['choices'][0]['message']['content']
                self.conversation_history.append({"role": "user", "content": user_input})
                self.conversation_history.append({"role": "assistant", "content": ai_response})
                await self.execute_ai_commands(ai_response)
                return ai_response
            else:
                if self.use_google_fallback:
                    return await self.google_voice_fallback(user_input)
                return "AI API error"
                
        except Exception as e:
            activity_log.log(f"AI error: {e}")
            if self.use_google_fallback:
                return await self.google_voice_fallback(user_input)
            return "AI processing failed"
    
    async def google_voice_fallback(self, user_input):
        cmd = user_input.upper()
        if "FORWARD" in cmd or "MOVE FORWARD" in cmd or "GO AHEAD" in cmd:
            self.hardware.send_command_to_arduino("FORWARD")
            return "Moving forward"
        elif "BACKWARD" in cmd or "MOVE BACK" in cmd or "REVERSE" in cmd:
            self.hardware.send_command_to_arduino("BACKWARD")
            return "Moving backward"
        elif "LEFT" in cmd or "TURN LEFT" in cmd:
            self.hardware.send_command_to_arduino("LEFT")
            return "Turning left"
        elif "RIGHT" in cmd or "TURN RIGHT" in cmd:
            self.hardware.send_command_to_arduino("RIGHT")
            return "Turning right"
        elif "STOP" in cmd or "HALT" in cmd:
            self.hardware.send_command_to_arduino("STOP")
            return "Stopped"
        elif "PUMP" in cmd and "ON" in cmd:
            self.hardware.send_command_to_arduino("PUMP_ON")
            return "Water pump started"
        elif "PUMP" in cmd and "OFF" in cmd:
            self.hardware.send_command_to_arduino("PUMP_OFF")
            return "Water pump stopped"
        elif "GRASS" in cmd or "CUTTER" in cmd:
            if "ON" in cmd or "START" in cmd:
                self.hardware.send_command_to_arduino("GRASS_ON")
                return "Grass cutter started"
            else:
                self.hardware.send_command_to_arduino("GRASS_OFF")
                return "Grass cutter stopped"
        elif "SEED" in cmd:
            if "ON" in cmd or "START" in cmd:
                self.hardware.send_command_to_arduino("SEED_ON")
                return "Seed motor started"
            else:
                self.hardware.send_command_to_arduino("SEED_OFF")
                return "Seed motor stopped"
        else:
            return f"Command not recognized: {user_input}"
    
    async def execute_ai_commands(self, ai_response):
        commands = re.findall(r'\[([A-Z_]+)\]', ai_response)
        for cmd in commands:
            self.hardware.send_command_to_arduino(cmd)
            await asyncio.sleep(0.1)

# ===================== SENSOR PROCESSOR =====================
class SensorProcessor:
    def __init__(self):
        self.latest_data = {
            "flame": 1023,
            "soil": 1023,
            "temp": 0,
            "humidity": 0,
            "fire": False,
            "theft": False,
            "distance": 0,
            "gps": None
        }
    
    def parse_arduino_data(self, data_string):
        try:
            parts = data_string.split(',')
            battery = None
            for part in parts:
                if ':' in part:
                    key, value = part.split(':', 1)
                    key = key.strip().lower()
                    value = value.strip()
                    
                    if key == "flame":
                        self.latest_data["flame"] = int(value)
                    elif key == "soil":
                        self.latest_data["soil"] = int(value)
                    elif key == "temp":
                        self.latest_data["temp"] = float(value)
                    elif key == "hum":
                        self.latest_data["humidity"] = float(value)
                    elif key == "dist":
                        self.latest_data["distance"] = int(value)
                    elif key == "fire":
                        self.latest_data["fire"] = value == "1"
                    elif key == "theft":
                        self.latest_data["theft"] = value == "1"
                    elif key == "battery":
                        battery = int(value)
            return battery
        except:
            return None
    
    def get_status_json(self):
        return json.dumps(self.latest_data)

# ===================== SECURITY & AUTO CHARGING SYSTEM =====================
class SecuritySystem:
    def __init__(self, hardware, sensors, storage):
        self.hardware = hardware
        self.sensors = sensors
        self.storage = storage
        self.alert_active = False
        self.last_alert_time = 0
        self.auto_charging_mode = False
        self.battery_alert_sent = False
        
    async def check_alerts(self):
        while True:
            try:
                if self.sensors.latest_data["distance"] > THEFT_HEIGHT_THRESHOLD:
                    if not self.sensors.latest_data["theft"]:
                        self.hardware.send_command_to_arduino("THEFT_ON")
                        activity_log.log("🚨 THEFT DETECTED - Height threshold exceeded")
                
                if self.sensors.latest_data["fire"] or self.sensors.latest_data["theft"]:
                    current_time = time.time()
                    if current_time - self.last_alert_time > 300:
                        await self.trigger_alert()
                        self.last_alert_time = current_time
                
                await self.check_battery_level()
                
            except Exception as e:
                activity_log.log(f"Security check error: {e}")
            await asyncio.sleep(1)
    
    async def check_battery_level(self):
        battery = self.hardware.battery_level
        
        if battery <= BATTERY_LOW_THRESHOLD and battery > BATTERY_CRITICAL_THRESHOLD:
            if not self.battery_alert_sent:
                msg = f"Agribot Battery Low: {battery}%"
                self.hardware.send_sms(ALERT_PHONE, msg)
                self.hardware.make_call(ALERT_PHONE)
                activity_log.log(f"⚠️ {msg}")
                self.battery_alert_sent = True
        
        if battery <= BATTERY_CRITICAL_THRESHOLD and not self.auto_charging_mode:
            activity_log.log(f"🔋 CRITICAL BATTERY: {battery}% - Auto charging activated")
            await self.go_to_charging_station()
    
    async def go_to_charging_station(self):
        self.auto_charging_mode = True
        activity_log.log("🤖 Navigating to charging station...")
        
        try:
            if os.path.exists(CHARGE_LOCATION_FILE):
                with open(CHARGE_LOCATION_FILE, 'r') as f:
                    target = json.load(f)
                    activity_log.log(f"Target: {target['lat']}, {target['lon']}")
            else:
                activity_log.log("⚠️ Charging location not set!")
                return
        except Exception as e:
            activity_log.log(f"Error loading charge location: {e}")
            return
        
        self.hardware.send_sms(ALERT_PHONE, "Agribot: Auto-charging mode activated. Going to charging station.")
        
        self.hardware.send_command_to_arduino("FORWARD")
        
        timeout = time.time() + 120  # 2 min timeout
        while self.hardware.charging_status != "Charging" and time.time() < timeout:
            await asyncio.sleep(2)
        
        self.hardware.send_command_to_arduino("STOP")
        activity_log.log("✓ Reached charging station" if self.hardware.charging_status == "Charging" else "⚠️ Charging station timeout")
        self.auto_charging_mode = False
    
    async def trigger_alert(self):
        alert_type = "FIRE" if self.sensors.latest_data["fire"] else "THEFT"
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        
        activity_log.log(f"🚨 {alert_type} ALERT TRIGGERED")
        
        for i in range(10):
            filename = f"{EVIDENCE_DIR}/{alert_type}_{timestamp}_photo_{i}.jpg"
            self.hardware.capture_photo(filename)
            await asyncio.sleep(0.5)
        
        video_file = f"{EVIDENCE_DIR}/{alert_type}_{timestamp}_video.avi"
        Thread(target=self.record_evidence_video, args=(video_file, 120)).start()
        
        gps_data = self.hardware.read_gps()
        location = f"GPS: {gps_data}" if gps_data else "GPS unavailable"
        
        sms_message = f"AGRIBOT {alert_type} ALERT! Time: {timestamp}. {location}"
        self.hardware.send_sms(ALERT_PHONE, sms_message)
        
        await asyncio.sleep(2)
        self.hardware.make_call(ALERT_PHONE)
        
        self.hardware.send_command_to_arduino("STOP")
        
        activity_log.log(f"✓ Security protocol completed for {alert_type}")
    
    def record_evidence_video(self, filename, duration):
        fourcc = cv2.VideoWriter_fourcc(*'XVID')
        out = cv2.VideoWriter(filename, fourcc, VIDEO_FPS, (VIDEO_WIDTH, VIDEO_HEIGHT))
        start = time.time()
        while time.time() - start < duration:
            frame = self.hardware.get_camera_frame()
            if frame is not None:
                out.write(frame)
        out.release()
        activity_log.log(f"✓ Evidence video saved: {filename}")

# ===================== MQTT MANAGER =====================
class MQTTManager:
    def __init__(self, hardware, sensors, ai_assistant, storage, security):
        self.hardware = hardware
        self.sensors = sensors
        self.ai_assistant = ai_assistant
        self.storage = storage
        self.security = security
        self.ai_mode = True
        
    async def run_mqtt(self):
        while True:
            try:
                async with Client(hostname=MQTT_BROKER, port=MQTT_PORT) as client:
                    activity_log.log(f"✓ Connected to MQTT broker {MQTT_BROKER}:{MQTT_PORT}")
                    
                    await client.subscribe(MQTT_CONTROL_TOPIC)
                    
                    publish_task = asyncio.create_task(self.broadcast_sensor_data(client))
                    
                    async for message in client.messages:
                        if message.topic.matches(MQTT_CONTROL_TOPIC):
                            command = message.payload.decode("utf-8").strip()
                            await self.process_command(command, client)
                    
                    publish_task.cancel()
                    
            except Exception as error:
                activity_log.log(f"✗ MQTT error: {error}. Reconnecting in 10s...")
                await asyncio.sleep(10)
    
    async def process_command(self, command, client):
        cmd_upper = command.upper()
        
        if cmd_upper == "AI_ON":
            self.ai_mode = True
            self.ai_assistant.enabled = True
            await client.publish(MQTT_RESPONSE_TOPIC, json.dumps({"type": "ai_status", "enabled": True}))
        elif cmd_upper == "AI_OFF":
            self.ai_mode = False
            self.ai_assistant.enabled = False
            await client.publish(MQTT_RESPONSE_TOPIC, json.dumps({"type": "ai_status", "enabled": False}))
        
        elif command.startswith("VOICE:"):
            voice_text = command[6:].strip()
            activity_log.log(f"🎤 Voice: {voice_text}")
            
            if self.ai_mode:
                ai_response = await self.ai_assistant.process_voice_command(voice_text)
                await client.publish(MQTT_RESPONSE_TOPIC, json.dumps({"type": "ai_response", "text": ai_response}))
            else:
                self.hardware.send_command_to_arduino(voice_text.upper())
        
        elif cmd_upper == "CLEAR_RECORDINGS":
            deleted = self.storage.clear_old_recordings()
            activity_log.log(f"🗑️ Cleared {deleted} old recordings")
            await client.publish(MQTT_RESPONSE_TOPIC, json.dumps({"type": "storage_cleared", "count": deleted}))
        
        elif cmd_upper == "START_RECORDING":
            filename = self.storage.start_continuous_recording(self.hardware.camera)
            if filename:
                await client.publish(MQTT_RESPONSE_TOPIC, json.dumps({"type": "recording_started", "file": filename}))
        
        elif cmd_upper == "STOP_RECORDING":
            self.storage.stop_recording()
            await client.publish(MQTT_RESPONSE_TOPIC, json.dumps({"type": "recording_stopped"}))
        
        elif command.startswith("SET_CHARGE_LOC:"):
            coords = command[15:].split(',')
            if len(coords) == 2:
                try:
                    location = {"lat": float(coords[0]), "lon": float(coords[1])}
                    with open(CHARGE_LOCATION_FILE, 'w') as f:
                        json.dump(location, f)
                    activity_log.log(f"📍 Charge location set: {location}")
                    await client.publish(MQTT_RESPONSE_TOPIC, json.dumps({"type": "charge_location_set"}))
                except:
                    activity_log.log("Invalid charge location format")
        
        elif command.startswith("CHARGE_SOURCE:"):
            source = command[14:].strip()
            self.hardware.charging_source = source
            activity_log.log(f"⚡ Charging source: {source}")
        
        elif command.startswith("WIFI:"):
            wifi_data = command[5:]
            await self.change_wifi(wifi_data)
            await client.publish(MQTT_RESPONSE_TOPIC, json.dumps({"type": "wifi_changed"}))
        
        elif cmd_upper == "GET_LOGS":
            logs = activity_log.get_recent_logs(50)
            await client.publish(MQTT_LOGS_TOPIC, json.dumps({"type": "logs", "data": logs}))
        
        else:
            self.hardware.send_command_to_arduino(cmd_upper)
    
    async def change_wifi(self, wifi_data):
        try:
            ssid, password = wifi_data.split('|', 1)
            config = f'''
network={{
    ssid="{ssid}"
    psk="{password}"
    key_mgmt=WPA-PSK
}}
'''
            with open(WIFI_CONFIG_FILE, 'w') as f:
                f.write(config)
            
            activity_log.log(f"📶 WiFi changed to: {ssid}")
            os.system("sudo wpa_cli -i wlan0 reconfigure")
        except Exception as e:
            activity_log.log(f"WiFi change error: {e}")
    
    async def broadcast_sensor_data(self, client):
        last_publish = 0
        while True:
            try:
                now = time.time()
                if now - last_publish >= 0.5:
                    data = {
                        "sensors": self.sensors.latest_data,
                        "battery": self.hardware.battery_level,
                        "charging": self.hardware.charging_status,
                        "charging_source": self.hardware.charging_source,
                        "storage": self.storage.get_storage_info(),
                        "recording": self.storage.recording_active,
                        "ai_mode": self.ai_mode
                    }
                    await client.publish(MQTT_STATUS_TOPIC, json.dumps(data))
                    last_publish = now
            except Exception as e:
                activity_log.log(f"MQTT publish error: {e}")
                break
            await asyncio.sleep(0.1)

# ===================== CONTINUOUS RECORDING =====================
async def continuous_recording_task(hardware, storage):
    while True:
        try:
            frame = hardware.get_camera_frame()
            if frame is not None:
                storage.record_frame(frame)
        except:
            pass
        await asyncio.sleep(0.05)

# ===================== MAIN SYSTEM =====================
class AgribotSystem:
    def __init__(self):
        activity_log.log("🤖 Initializing Agribot Ultimate System (MQTT)...")
        
        self.hardware = HardwareManager()
        self.sensors = SensorProcessor()
        self.storage = StorageManager()
        self.ai_assistant = AIAssistant(self.hardware, self.sensors)
        self.security = SecuritySystem(self.hardware, self.sensors, self.storage)
        self.mqtt_manager = MQTTManager(self.hardware, self.sensors, self.ai_assistant, self.storage, self.security)
        
        self.storage.start_continuous_recording(self.hardware.camera)
        activity_log.log("✓ Continuous recording started")
    
    async def sensor_reader_loop(self):
        while True:
            try:
                data = self.hardware.read_arduino_data()
                if data:
                    battery_level = self.sensors.parse_arduino_data(data)
                    if battery_level is not None:
                        self.hardware.update_battery_status(battery_level)
            except:
                pass
            await asyncio.sleep(0.1)
    
    async def gps_reader_loop(self):
        while True:
            try:
                gps_data = self.hardware.read_gps()
                if gps_data:
                    self.sensors.latest_data["gps"] = gps_data
            except:
                pass
            await asyncio.sleep(1)
    
    async def battery_monitor_loop(self):
        prev_battery = self.hardware.battery_level
        while True:
            try:
                await asyncio.sleep(5)
                curr_battery = self.hardware.battery_level
                
                if curr_battery > prev_battery + 1:
                    if self.hardware.charging_status != "Charging":
                        self.hardware.update_battery_status(
                            curr_battery, 
                            charging=True,
                            source=self.hardware.charging_source or "Wireless"
                        )
                        activity_log.log(f"🔋 Charging started: {self.hardware.charging_source}")
                elif curr_battery < prev_battery - 1:
                    if self.hardware.charging_status == "Charging":
                        self.hardware.update_battery_status(curr_battery, charging=False)
                        activity_log.log("🔋 Charging stopped")
                
                prev_battery = curr_battery
                
            except Exception as e:
                activity_log.log(f"Battery monitor error: {e}")
            await asyncio.sleep(10)
    
    async def storage_cleanup_loop(self):
        while True:
            try:
                storage_info = self.storage.get_storage_info()
                if storage_info['free_gb'] < 1:
                    activity_log.log("⚠️ Low storage! Cleaning old recordings...")
                    deleted = self.storage.clear_old_recordings(keep_recent=5)
                    activity_log.log(f"🗑️ Cleaned {deleted} old recordings")
                    
                    if storage_info['free_gb'] < 0.5:
                        activity_log.clear_old_logs()
                        activity_log.log("🗑️ Cleared old logs")
                
            except Exception as e:
                activity_log.log(f"Storage cleanup error: {e}")
            
            await asyncio.sleep(600)
    
    async def start(self):
        activity_log.log("🚀 Starting all systems...")
        
        try:
            if os.path.exists(CHARGE_LOCATION_FILE):
                with open(CHARGE_LOCATION_FILE, 'r') as f:
                    location = json.load(f)
                    activity_log.log(f"📍 Loaded charge location: {location}")
        except Exception as e:
            activity_log.log(f"Charge location load error: {e}")
        
        activity_log.log(f"✓ MQTT broker: {MQTT_BROKER}")
        activity_log.log(f"✓ Control topic: {MQTT_CONTROL_TOPIC}")
        activity_log.log(f"✓ Status topic: {MQTT_STATUS_TOPIC}")
        activity_log.log(f"✓ Continuous recording active")
        activity_log.log(f"✓ Theft detection: Height > {THEFT_HEIGHT_THRESHOLD}cm")
        activity_log.log(f"✓ Battery alerts: {BATTERY_LOW_THRESHOLD}% and {BATTERY_CRITICAL_THRESHOLD}%")
        
        await asyncio.gather(
            self.mqtt_manager.run_mqtt(),
            self.sensor_reader_loop(),
            self.gps_reader_loop(),
            self.battery_monitor_loop(),
            self.storage_cleanup_loop(),
            self.security.check_alerts(),
            continuous_recording_task(self.hardware, self.storage)
        )

# =================== ENTRY POINT ===================
if __name__ == "__main__":
    print("""
    ╔════════════════════════════════════════════════╗
    ║         AGRIBOT ULTIMATE CONTROL SYSTEM        ║
    ║              Stable Version - 2026             ║
    ╚════════════════════════════════════════════════╝
    """)
    
    if os.geteuid() != 0:
        print("⚠️  Warning: Not running as root. Some features may not work.")
        print("   Run with: sudo python3 agribot_main.py")
    
    system = AgribotSystem()
    
    try:
        asyncio.run(system.start())
        
    except KeyboardInterrupt:
        print("\n🛑 Shutdown requested...")
        activity_log.log("System shutdown by user")
        
        system.storage.stop_recording()
        activity_log.log("✓ Recording stopped")
        
        system.hardware.send_command_to_arduino("EMERGENCY")
        activity_log.log("✓ All motors stopped")
        
        print("👋 Agribot stopped safely")
        
    except Exception as e:
        error_msg = f"❌ Fatal error: {e}"
        activity_log.log(error_msg)
        print(error_msg)
        
        try:
            system.hardware.send_sms(ALERT_PHONE, f"Agribot system error: {str(e)[:50]}")
        except:
            pass
    
    finally:
        try:
            system.storage.stop_recording()
            if system.hardware.camera:
                system.hardware.camera.release()
        except:
            pass
        
        print("System cleanup complete")
