# 🤖 Smart AgroNovaX — AI-Powered Autonomous Agricultural Robot

<div align="center">

[![NASA Space Apps Challenge](https://shields.io)](https://spaceappschallenge.org)
[![Team](https://shields.io)]()
[![Python](https://shields.io)](https://python.org)
[![Raspberry Pi](https://shields.io)](https://raspberrypi.org)
[![Arduino](https://shields.io)](https://arduino.cc)

</div>

---

## 📽️ Project Video Preview & Demonstration
*(Apanar video link ti nicher bracket e bosiye din)*

[![Smart AgroNovaX Video Demo](https://shields.io▶_Watch_Full_4--Min_Project_Video-Click_Here_to_Play-red?style=for-the-badge&logo=youtube)](https://videotourl.com/videos/1791658269891-d39bc75d-de4c-4719-ba88-611086651a4f.mp4)

> **[▶ Click here to watch the full presentation and demonstration video](https://videotourl.com/videos/1791658056993-f254e21f-4bfa-4de3-929e-d17286fbcc4e.mp4)**

---

## 🌾 About Smart AgroNovaX
**Smart AgroNovaX** is an advanced, AI-powered autonomous agricultural robot developed by **SmartBD TECH**. Built for the **NASA Space Apps Challenge** under the category *"Field Shift: Adapting Farms with NASA Data"*, this project bridges space technology with ground-level farming. By leveraging real-time satellite remote sensing and local IoT sensor data, Smart AgroNovaX optimizes crop health, automates heavy labor, executes precision seed sowing, and protects agricultural assets.

---

## 👥 Team & Organization Information
* **Team Name:** SmartBD TECH  
* **Organization:** SmartBD TECH Company  
* **Location:** Dhaka, Bangladesh  

### **Team Leadership & Members:**
* **Md. Saimun Islam** — CEO, President & Founder (Team Leader)  
  * ✉️ Email: `saimunteach7@gmail.com` | 📞 Phone: `+8801603320208`
* **Furkan Mahmud** — Project Manager (Smart AgroNovaX Project)  
  * ✉️ Email: `furkanmahmudlegacy@gmail.com` | 📞 Phone: `+8801893602237`

---

## 🛰️ NASA Data & Satellite Integration
Smart AgroNovaX utilizes space-borne data to make intelligent agronomic decisions:
* **NASA EOSDIS & Landsat:** High-resolution satellite imagery for land cover mapping and environmental tracking.
* **MODIS & VIIRS Hot Spots:** Near real-time satellite data for soil moisture analysis, vegetation health indexing (NDVI), and drought risk forecasting.

---

## ✨ Key Features & Capabilities
1. **🌱 Robotic Arm & Seed Sowing:** Automated precision seed sowing and sapling planting mechanism with optimal depth and spacing control.
2. **💧 Smart Irrigation Pumping:** Intelligent water pump system integrated with real-time soil moisture sensors.
3. **🌿 Grass Cutting & Terrain Navigation:** Autonomous path traversal, obstacle avoidance, and terrain maintenance.
4. **🌏 Global Remote Control:** Control the robot from anywhere on Earth via Cellular SIM (GSM), Wi-Fi, Bluetooth, or Web Dashboard.
5. **🚨 Advanced Security & Anti-Theft:** Ultrasonic height-lift sensors and flame/fire sensors with automated high-decibel alarms, instant SMS/Call alerts, and continuous camera evidence recording.

---

## 🛠️ Hardware & Technical Stack
* **Processing & AI Hub:** Raspberry Pi Zero 2 W (Python, OpenCV, MQTT, OpenRouter AI Llama 3.1)
* **Microcontroller & Sensor Bridge:** Arduino UNO (C++, Motor Drivers, Real-time sensor polling)
* **Locomotion:** Heavy-duty DC gear motors driven by L298N/BTS7960 motor drivers.
* **Sensors Integrated:** Soil Moisture Sensor, DHT22 (Temperature & Humidity), Flame Sensor, HC-SR04 Ultrasonic Distance Sensor, NEO-6M GPS.
* **Communication Modules:** SIM900A GSM Module (SMS/Call alerts), HC-05 Bluetooth Module, Wi-Fi.

---

## ⚙️ Complete A-Z Setup & Installation Guide

### Part 1: Raspberry Pi OS & System Configuration
Execute the following commands on your Raspberry Pi Zero 2 W terminal:

1. **System & Serial Configuration (`sudo raspi-config`):**
   * Interface Options → Serial Port: Login shell = **NO**, Serial hardware = **YES**.
   * Interface Options → I2C: **Enable**.
   * Performance Options → GPU Memory: Set to **128MB**.
   * Localisation → Timezone: `Asia/Dhaka`.

2. **Boot Configuration Update:**
   ```bash
   sudo nano /boot/firmware/config.txt
   ```
   Add these lines at the end:
   ```text
   enable_uart=1
   dtoverlay=disable-bt
   gpu_mem=128
   start_x=1
   ```
   *(Save & Exit: `Ctrl+X`, then `Y`, then `Enter`)*

3. **Install Dependencies & Packages:**
   ```bash
   sudo apt update && sudo apt upgrade -y
   sudo apt install -y python3-pip python3-dev python3-opencv git nginx build-essential cmake v4l-utils python3-serial python3-requests python3-numpy python3-asyncio-mqtt
   sudo usermod -a -G dialout,video,gpio pi
   ```

4. **Create Directory Structure:**
   ```bash
   mkdir -p ~/agribot_data/evidence
   mkdir -p ~/agribot_data/recordings
   ```

---

### Part 2: Systemd Auto-Start Service Setup
To ensure the main agribot Python script (`agribot_main.py`) runs automatically on boot:

1. Create the service file:
   ```bash
   sudo nano /etc/systemd/system/agribot.service
   ```
2. Paste the following configuration:
   ```ini
   [Unit]
   Description=Agribot Ultimate Control System
   After=network.target

   [Service]
   Type=simple
   User=pi
   WorkingDirectory=/home/pi
   ExecStart=/usr/bin/python3 /home/pi/agribot_main.py
   Restart=always
   RestartSec=10
   StandardOutput=append:/home/pi/agribot_data/agribot.log
   StandardError=append:/home/pi/agribot_data/agribot_error.log

   [Install]
   WantedBy=multi-user.target
   ```
3. Enable and start the service:
   ```bash
   sudo systemctl daemon-reload
   sudo systemctl enable agribot.service
   sudo systemctl start agribot.service
   ```

---

### Part 3: WiFi Configuration Script (`change_wifi.sh`)
Create a helper script in your home directory to easily update Wi-Fi credentials on the go:
```bash
nano ~/change_wifi.sh
```
Paste the following script content:
```bash
#!/bin/bash
echo "Current WiFi networks:"
sudo iwlist wlan0 scan | grep ESSID

echo ""
read -p "Enter WiFi SSID: " SSID
read -sp "Enter WiFi Password: " PASS
echo ""

sudo tee /etc/wpa_supplicant/wpa_supplicant.conf > /dev/null <<EOF
country=BD
ctrl_interface=DIR=/var/run/wpa_supplicant GROUP=netdev
update_config=1

network={
    ssid="\$SSID"
    psk="\$PASS"
    key_mgmt=WPA-PSK
}
EOF

echo "Restarting WiFi..."
sudo wpa_cli -i wlan0 reconfigure
echo "Done! New WiFi configured."
```

---
© 2026 SmartBD TECH. All rights reserved.
