# GreytHR Attendance Automator ⏰

An automated, intelligent Windows background utility that reminds and helps you mark attendance on your company's **GreytHR** portal with a single click.

---

## ✨ Features

- **One-Click Attendance**: Automatically launches a headless browser, logs into GreytHR, and marks your attendance for the day.
- **Smart Prompts**: Detects when you are actively using your PC on weekdays and prompts you if attendance has not yet been marked today.
- **Snooze & Skip Options**: Conveniently snooze for 1 hour or skip for the day (e.g., when taking leave or already checked in).
- **Ultra-Low Resource Footprint**: Uses lazy loading and memory trimming to stay under ~15 MB RAM, checking every 2 minutes when waiting and backing off to 1-hour sleeps once marked.
- **System Tray Resident**: Runs silently in the background with minimal memory usage.
- **Auto-Start with Windows**: Automatically registered in Windows Startup during setup so you never forget to check in.
- **Location Selector**: Supports Office, Home, and Client Location check-ins.

---

## 🚀 Quick & Easy Setup

### Prerequisites
- **Windows 10 / 11**
- **Python 3.9 or newer**: Download from [python.org](https://www.python.org/downloads/) if not already installed.
  > ⚠️ **Important**: When installing Python, ensure the option **"Add python.exe to PATH"** is checked!
- **Git** installed on your system.

---

### ⚡ Option A: 1-Line Terminal Install (Fastest)

Open **PowerShell** or **Terminal** and paste this single command:

```powershell
git clone https://github.com/Kishore341507/GreytHR-Attendance-Automator.git; cd GreytHR-Attendance-Automator; .\setup.bat
```

*(Or in classic **Command Prompt / CMD**:)*
```cmd
git clone https://github.com/Kishore341507/GreytHR-Attendance-Automator.git && cd GreytHR-Attendance-Automator && setup.bat
```

---

### 🖱️ Option B: Manual / File Explorer

1. Download or clone this repository.
2. Open the `GreytHR-Attendance-Automator` folder.
3. Double-click **`setup.bat`**.

---

### What `setup.bat` does automatically:
- Creates an isolated Python virtual environment (`venv`).
- Installs required dependencies (`playwright`, `pystray`, `Pillow`).
- Downloads the Playwright Chromium automation engine.
- Configures auto-start on Windows boot (places a shortcut in your Startup folder).
- Launches the application silently in your Windows System Tray.

---

### Step 2: Configure Your Credentials
On the first run (or anytime via System Tray):
1. The **GreytHR Settings** window will appear.
2. Enter your details:
   - **GreytHR Portal URL**: e.g., `https://<your-company>.greythr.com/`
   - **User ID / Employee ID**: e.g., `AB-0123`
   - **Password**: Your GreytHR password
   - **Work Location**: Select `Office`, `Home`, or `Client Location`
   - **Browser Mode**: Keep *Run in background (Headless)* checked for silent operation.
3. Click **Save Settings**.

---

## 🛑 How to Stop the Application

### Via System Tray
1. Locate the **GreytHR Attendance** icon in your **Windows Taskbar System Tray** (bottom-right corner of your screen, next to the clock).
   > *Note: If hidden, click the small upward arrow `^` in the taskbar.*
2. **Right-click** on the GreytHR circular checkmark icon.
3. Click **Exit**.

The background service and tray icon will stop immediately.

```
+---------------------------+
|  Mark Attendance Now      |
|  Settings                 |
|---------------------------|
|  Exit              <------+--- Click here to stop!
+---------------------------+
```
---

## 🖥️ Everyday Usage

- **Daily Prompt**: When you start working on your PC on a weekday, a dialog pops up asking:
  - **✔ Mark Attendance**: Performs automatic check-in.
  - **🚫 Don't mark today**: Skips prompting for the rest of today.
  - **⏳ Remind in 1 Hour**: Postpones the prompt by 1 hour.
- **Manual Trigger**: Right-click the system tray icon and choose **Mark Attendance Now** at any time.
- **Change Settings**: Right-click the system tray icon and choose **Settings** to update your password or work location.

---

## 📁 File Structure

| File / Folder | Purpose |
| --- | --- |
| `main.py` | Main application script (GUI, Tray icon, Playwright automation). |
| `setup.bat` | Automated 1-click installer and launcher. |
| `run_silent.vbs`| VBScript wrapper that starts the app without opening a command prompt window. |
---

## 🔒 Security & Privacy
All credentials and configurations are stored **strictly locally** on your machine inside the `data/config.json` file. No data is ever sent to any third-party server—only directly to your company's official GreytHR portal.