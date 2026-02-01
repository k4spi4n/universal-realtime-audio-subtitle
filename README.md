# Universal Realtime Audio Subtitle

**A high-performance, real-time subtitle overlay for Windows that captures system audio and generates accurate captions using state-of-the-art AI models.**

## 📖 Overview

This project provides a "universal" subtitle solution for any audio playing on your Windows machine (movies, meetings, streams, games). It uses a hybrid architecture:

1. **Frontend (JavaFX):** A lightweight, transparent, always-on-top window that overlays subtitles on your screen without interfering with your workflow.
2. **Backend (Python):** Runs powerful AI models (currently **Qwen3-ASR**) to transcribe audio in real-time with Voice Activity Detection (VAD) to ensure accuracy and silence suppression.
3. **Communication:** The two components communicate seamlessly via **ZeroMQ (ZMQ)**, ensuring low latency and decoupling the UI from heavy AI inference.

## ✨ Features

* **System Audio Capture:** Automatically detects and captures "Stereo Mix" or "What U Hear" to subtitle *computer audio* rather than just the microphone.
* **Next-Gen AI Accuracy:** Currently utilizes **Qwen3-ASR-0.6B** for transcription, offering superior performance and speed compared to older models.
* **Transparent Overlay:**
* **Draggable:** Move the subtitle bar anywhere on the screen.
* **Click-through:** (Planned) Doesn't block mouse interaction with windows behind it.
* **Auto-Hide:** Subtitles fade away after 3 seconds of silence.


* **Smart VAD Integration:** Uses **Silero VAD** to detect speech vs. background noise, preventing AI hallucinations during silence.
* **Controller Dashboard:** A dedicated control panel to Start, Stop, and Reset the transcription engine.

## 🛠 Architecture

The project is split into two distinct modules:

* **`audio-test/` (Java Client):**
* Built with Maven and JavaFX 21.
* Manages the GUI and lifecycle of the Python backend.
* Subscribes to `tcp://localhost:5555` to receive text.


* **`python-backend/` (AI Server):**
* Runs the ASR model and VAD.
* Processes audio chunks using `PyAudio` and `NumPy`.
* Publishes transcribed text via ZeroMQ.



## ⚙️ Prerequisites

### 1. System Audio (Important)

Since this tool is designed to subtitle *system output*, you must enable **Stereo Mix** on Windows:

1. Open **Sound Settings** > **Sound Control Panel**.
2. Go to the **Recording** tab.
3. Right-click and ensure "Show Disabled Devices" is checked.
4. Right-click **Stereo Mix** (or "What U Hear") and select **Enable**.

### 2. Software Requirements

* **Java JDK 21** or higher.
* **Apache Maven**.
* **Python 3.10+**.
* **NVIDIA GPU (Recommended):** The backend is optimized for CUDA (`torch`, `accelerate`). CPU inference is possible but may be slower.

## 🚀 Installation & Setup

### 1. Clone the Repository

```bash
git clone https://github.com/your-username/universal-realtime-audio-subtitle.git
cd universal-realtime-audio-subtitle

```

### 2. Setup Python Backend

Navigate to the backend folder and install dependencies:

```bash
cd python-backend
# Optional: Create a virtual environment
# python -m venv venv
# .\venv\Scripts\activate

pip install -r requirements.txt

```

*Note: Ensure you have the correct version of PyTorch installed for your CUDA version.*

### 3. Build Java Frontend

Navigate to the audio client folder:

```bash
cd ../audio-test
mvn clean compile

```

## ▶️ How to Run

The easiest way to run the application is using the provided batch script, which builds the Java app and handles the Python execution automatically.

1. Navigate to `audio-test/`.
2. Double-click **`run_app.bat`**.

Alternatively, via command line:

```bash
cd audio-test
mvn javafx:run

```

**What happens next?**

1. The **Controller** window will appear (Status: Ready).
2. The application will automatically launch the internal Python server in the background.
3. The **Subtitle Overlay** (black transparent bar) will appear at the bottom of your screen.
4. Play any audio on your computer. If speech is detected, subtitles will appear instantly.

## 🔧 Configuration

### Switching Models

Currently, the model is hardcoded in `python-backend/server.py`:

```python
model = Qwen3ASRModel.from_pretrained("Qwen/Qwen3-ASR-0.6B", ...)

```

### Troubleshooting

* **Stuck on "Waiting for python backend...":**
* Check if the Python backend started correctly. The Java console prints the Python logs.
* Ensure port `5555` is not blocked.


* **No Subtitles Appearing:**
* Verify **Stereo Mix** is the default recording device or active.
* Check the console for `[VAD]` logs to see if voice is being detected.



## 🤝 Contributing

Contributions are welcome! Please feel free to submit a Pull Request.

1. Fork the project.
2. Create your feature branch (`git checkout -b feature/AmazingFeature`).
3. Commit your changes (`git commit -m 'Add some AmazingFeature'`).
4. Push to the branch (`git push origin feature/AmazingFeature`).
5. Open a Pull Request.

## 📄 License

Distributed under the MIT License. See `LICENSE` for more information.
