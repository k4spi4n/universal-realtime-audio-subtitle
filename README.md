# Universal Realtime Audio Subtitle

**A high-performance, real-time subtitle overlay for Windows that captures system audio and generates accurate captions using cutting-edge AI models.**

## 📖 Overview

This project provides a "universal" subtitle solution for any audio playing on your Windows machine: movies, meetings, streams, games,... for over 52 languages.
It uses a hybrid architecture:

1. **Frontend (JavaFX):** A hardware accelerated and always-on-top window that overlays subtitles on your screen.
2. **Backend (Python):** Runs powerful AI models (currently **Qwen3-ASR**) to transcribe audio in real-time with Voice Activity Detection (VAD) to ensure accuracy and silence suppression.
3. **Communication:** The two components communicate seamlessly via **ZeroMQ (ZMQ)**, ensuring ultra low latency and decoupling the UI from heavy AI inference.

## ✨ Features

* **System Audio Capture:** Automatically detects and captures "Stereo Mix" to subtitle *computer audio* rather than just the microphone.
* **Next-Gen AI Accuracy:** Locally utilizes **Qwen3-ASR**, offering automatic languages detection and noisy-background voice transcription with superior accuracy.
* **Transparent Overlay:**
* **Draggable:** Move the subtitle bar anywhere on the screen.
* **Click-through:** (Planned) Doesn't block mouse interaction with windows behind it.
* **Auto-Hide:** Subtitles fade away after several seconds of silence.

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
4. Right-click **Stereo Mix** and select **Enable**.

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

## 🔧 Configuration

### Switching Models

You can specify the ASR model in `python-backend/server.py`:

```python
model = Qwen3ASRModel.from_pretrained("Qwen/Qwen3-ASR-0.6B", ...)

```

## 🗺️ Future Roadmap

We are actively working on expanding the capabilities of this tool. Planned features include:

* **🌐 Realtime Translation:** Instantly translate captured audio from one language to another (e.g., Japanese Anime audio -> English Subtitles) directly in the overlay.
* **📝 Meeting Summarization:** Automatically generate and export a concise summary of the conversation or meeting notes after the session ends.
* **💾 Session Logs:** Save the full transcription history to a text file for later reference.
* **🎛️ Audio Source Selection:** UI to manually select specific input devices or application audio sources instead of relying solely on "Stereo Mix."
* **🎨 UI Customization:** Settings to adjust font size, color, background opacity, and overlay position.

## 🤝 Contributing

Contributions are welcome! Please feel free to submit a Pull Request.

1. Fork the project.
2. Create your feature branch (`git checkout -b feature/AmazingFeature`).
3. Commit your changes (`git commit -m 'Add some AmazingFeature'`).
4. Push to the branch (`git push origin feature/AmazingFeature`).
5. Open a Pull Request.

## 📄 License

Distributed under the MIT License. See `LICENSE` for more information.
