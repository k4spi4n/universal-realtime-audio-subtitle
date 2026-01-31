import zmq
import pyaudio
import numpy as np
import time
from faster_whisper import WhisperModel
import os
import threading
import queue
import sys
import io

# --- CẤU HÌNH HỆ THỐNG ---
# Fix encoding cho Windows Console
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')
sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding='utf-8')

# Cấu hình ZMQ
PORT = 5555
context = zmq.Context()
socket = context.socket(zmq.PUB)

# --- AUTO-KILL PORT LOGIC ---
try:
    socket.bind(f"tcp://*:{PORT}")
except zmq.ZMQError as e:
    if "Address in use" in str(e):
        print(f"Port {PORT} busy. Cleaning up...")
        import subprocess, re
        try:
            res = subprocess.check_output(f"netstat -ano | findstr :{PORT}", shell=True).decode()
            for line in res.strip().split('\n'):
                parts = re.split(r'\s+', line.strip())
                if len(parts) > 4:
                    subprocess.run(f"taskkill /F /PID {parts[-1]}", shell=True)
            time.sleep(0.5)
            socket.bind(f"tcp://*:{PORT}")
            print("Port cleaned and bound.")
        except: pass

# --- CẤU HÌNH AUDIO & MODEL ---
# Model
MODEL_SIZE = "large-v3-turbo"
device = "cuda"
compute_type = "float16"

print(f"Loading {MODEL_SIZE} on {device}...")
model = WhisperModel(MODEL_SIZE, device=device, compute_type=compute_type)
print("Model Ready.")

# Audio Constants
RATE = 16000
CHUNK = 1024 # Buffer phần cứng
CHUNK_DURATION = CHUNK / RATE 
FORMAT = pyaudio.paInt16
CHANNELS = 1

# Queue để chuyển dữ liệu từ luồng thu âm sang luồng xử lý
raw_queue = queue.Queue()

def input_stream():
    """Luồng thu âm liên tục không chặn"""
    p = pyaudio.PyAudio()
    
    # Auto-select Stereo Mix/Loopback if available
    dev_idx = None
    for i in range(p.get_device_count()):
        info = p.get_device_info_by_index(i)
        if "mix" in info['name'].lower():
            dev_idx = i
            print(f"Using Loopback: {info['name']}")
            break

    stream = p.open(format=FORMAT, channels=CHANNELS, rate=RATE, 
                    input=True, input_device_index=dev_idx, 
                    frames_per_buffer=CHUNK)
    
    print("Microphone/System Audio Stream Started.")
    while True:
        try:
            data = stream.read(CHUNK, exception_on_overflow=False)
            raw_queue.put(data)
        except: break

def main_process():
    """Luồng xử lý chính: Tích lũy & Nhận diện"""
    
    audio_buffer = np.array([], dtype=np.float32)
    
    # Các biến kiểm soát trạng thái
    last_transcribe_time = time.time()
    silence_start_time = None
    
    # Config Logic
    TRANSCRIBE_INTERVAL = 0.25  # Nhận diện mỗi 0.25s (Tăng tốc độ phản hồi)
    SILENCE_THRESHOLD_DB = 500  # Ngưỡng biên độ để coi là im lặng (Tùy chỉnh nếu mic ồn)
    SILENCE_DURATION_LIMIT = 0.6 # Nếu im lặng quá 0.6s thì chốt câu và xóa buffer

    print(">>> REALTIME ENGINE STARTED <<<")
    
    while True:
        # 1. Lấy dữ liệu từ Queue (Non-blocking hoặc timeout cực ngắn)
        try:
            # Lấy hết dữ liệu đang chờ trong queue để xử lý một thể
            new_data_list = []
            while True:
                new_data_list.append(raw_queue.get_nowait())
        except queue.Empty:
            pass

        if new_data_list:
            # Gộp byte và convert sang float32
            raw_bytes = b''.join(new_data_list)
            new_audio = np.frombuffer(raw_bytes, dtype=np.int16).astype(np.float32) / 32768.0
            audio_buffer = np.concatenate((audio_buffer, new_audio))
            
            # --- SIMPLE VAD (Voice Activity Detection) ---
            # Tính biên độ trung bình của chunk mới nhất để xem có tiếng không
            amplitude = np.abs(new_audio).mean() * 32768
            
            if amplitude < SILENCE_THRESHOLD_DB:
                if silence_start_time is None:
                    silence_start_time = time.time()
            else:
                silence_start_time = None # Có tiếng nói, reset bộ đếm im lặng

        # 2. Kiểm tra điều kiện để Transcribe
        now = time.time()
        
        # Chỉ nhận diện nếu buffer đủ dài (>0.2s) và đã đến chu kỳ transcribe
        if len(audio_buffer) > RATE * 0.2 and (now - last_transcribe_time > TRANSCRIBE_INTERVAL):
            
            # Transcribe toàn bộ buffer hiện tại
            segments, _ = model.transcribe(audio_buffer, beam_size=1, language=None, vad_filter=True)
            
            text = " ".join([s.text for s in segments]).strip()
            
            if text:
                # In ra console (Ghi đè dòng cũ để gọn, tùy chọn)
                print(f"\r> {text}", end="", flush=True)
                socket.send_string(text)
            
            last_transcribe_time = now

        # 3. Logic Reset Buffer (Chốt câu)
        # Nếu im lặng quá lâu, ta coi như hết câu -> Xóa buffer để sẵn sàng cho câu mới
        if silence_start_time and (now - silence_start_time > SILENCE_DURATION_LIMIT):
            if len(audio_buffer) > 0:
                # Debug: print(f"\n[Sentence End] Cleared Buffer. Len: {len(audio_buffer)}")
                audio_buffer = np.array([], dtype=np.float32)
                silence_start_time = None
                # Gửi tin nhắn rỗng hoặc ký tự đặc biệt nếu muốn Frontend xóa text (tùy chọn)

        # Ngủ cực ngắn để giảm load CPU
        time.sleep(0.01)

if __name__ == "__main__":
    # Start Thread thu âm
    t = threading.Thread(target=input_stream, daemon=True)
    t.start()
    
    # Chạy process chính
    main_process()
