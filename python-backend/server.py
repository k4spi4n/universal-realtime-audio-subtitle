import zmq
import pyaudio
import numpy as np
import time
import os
import threading
import queue
import sys
import io
import torch
import logging
import warnings

# --- VAD INTEGRATION ---
try:
    from pysilero_vad import SileroVoiceActivityDetector
    HAS_VAD = True
except ImportError:
    HAS_VAD = False

# --- CẤU HÌNH HỆ THỐNG ---
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')
sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding='utf-8')
logging.getLogger("transformers").setLevel(logging.ERROR)
warnings.filterwarnings('ignore')

def log(msg):
    print(f"[{time.strftime('%H:%M:%S')}] {msg}", flush=True)

# --- TỐI ƯU CUDA CHO WINDOWS (API MỚI PyTorch 2.9+) ---
try:
    # API mới (PyTorch 2.9+)
    torch.backends.cudnn.conv.fp32_precision = 'tf32'
    torch.backends.cuda.matmul.fp32_precision = 'tf32'
except AttributeError:
    # API cũ (PyTorch < 2.9)
    torch.backends.cuda.matmul.allow_tf32 = True
    torch.backends.cudnn.allow_tf32 = True

# --- ZMQ SETUP ---
PORT = 5555
context = zmq.Context()
socket = context.socket(zmq.PUB)

# --- AUTO-KILL PORT ---
try:
    socket.bind(f"tcp://*:{PORT}")
except zmq.ZMQError as e:
    if "Address in use" in str(e):
        log(f"Port {PORT} đang bận. Đang dọn dẹp...")
        import subprocess, re
        try:
            res = subprocess.check_output(f"netstat -ano | findstr :{PORT}", shell=True).decode()
            for line in res.strip().split('\n'):
                parts = re.split(r'\s+', line.strip())
                if len(parts) > 4:
                    subprocess.run(f"taskkill /F /PID {parts[-1]}", shell=True)
            time.sleep(1)
            socket.bind(f"tcp://*:{PORT}")
            log("Đã giải phóng Port thành công.")
        except Exception:
            pass

# --- CẤU HÌNH AUDIO REALTIME (TỐI ƯU) ---
FORMAT = pyaudio.paInt16
CHANNELS = 1
RATE = 16000
CHUNK = 512
TRANSCRIBE_INTERVAL = 0.1
MIN_AUDIO_LENGTH = 0.2

# --- TỰ ĐỘNG TÌM STEREO MIX ---
def find_stereo_mix_index():
    p = pyaudio.PyAudio()
    info = p.get_host_api_info_by_index(0)
    numdevices = info.get('deviceCount')
    
    candidate_id = None
    candidate_name = ""
    
    log("Đang quét thiết bị âm thanh...")

    for i in range(0, numdevices):
        device_info = p.get_device_info_by_host_api_device_index(0, i)
        if device_info.get('maxInputChannels') > 0:
            name = device_info.get('name')
            if any(k in name.lower() for k in ["stereo mix", "wave out", "what u hear", "loopback"]):
                candidate_id = i
                candidate_name = name
                break

    final_id = 0
    if candidate_id is not None:
        final_id = candidate_id
        log(f"--> TỰ ĐỘNG CHỌN: {candidate_name} (ID: {final_id})")
    else:
        try:
            default_device = p.get_default_input_device_info()
            final_id = default_device['index']
            log(f"CẢNH BÁO: Không tìm thấy 'Stereo Mix'. Đang dùng mặc định: {default_device['name']}")
            log("HÃY BẬT STEREO MIX TRONG WINDOWS SOUND SETTINGS ĐỂ THU ÂM HỆ THỐNG.")
        except:
            log("LỖI: Không tìm thấy bất kỳ thiết bị thu âm nào!")
            sys.exit(1)
            
    p.terminate()
    return final_id

MIC_INDEX = find_stereo_mix_index()

from qwen_asr import Qwen3ASRModel

log("Đang khởi động Qwen3-ASR (Tối ưu cho Windows)...")

try:
    if not torch.cuda.is_available():
        log("LỖI: Script này yêu cầu NVIDIA GPU!")
        sys.exit(1)

    # TỐI ƯU CHO WINDOWS: Không dùng Flash Attention, dùng SDPA
    model = Qwen3ASRModel.from_pretrained(
        "Qwen/Qwen3-ASR-0.6B",
        dtype=torch.bfloat16, 
        max_inference_batch_size=1,
        device_map="cuda:0", 
        attn_implementation="sdpa",  # Scaled Dot Product Attention (tích hợp PyTorch)
        max_new_tokens=128
    )
    
    log(f"✓ Model Ready! Attention: SDPA | Mode: System Audio")

except Exception as e:
    log(f"LỖI LOAD MODEL: {e}")
    sys.exit(1)

# Biến Global
audio_queue = queue.Queue()
running = True

def audio_stream_thread():
    p = pyaudio.PyAudio()
    try:
        stream = p.open(format=FORMAT,
                        channels=CHANNELS,
                        rate=RATE,
                        input=True,
                        input_device_index=MIC_INDEX,
                        frames_per_buffer=CHUNK,
                        stream_callback=None)
        
        while running:
            data = stream.read(CHUNK, exception_on_overflow=False)
            audio_queue.put(data)
    except Exception as e:
        log(f"Lỗi Stream Audio: {e}")
    finally:
        stream.stop_stream()
        stream.close()
        p.terminate()

def processing_thread():
    global running
    audio_buffer = np.array([], dtype=np.float32)
    last_transcribe_time = time.time()
    last_sent_text = ""
    transcribe_count = 0

    MAX_BUFFER_LEN = int(RATE * 10)
    
    # Init VAD
    vad = None
    if HAS_VAD:
        try:
            vad = SileroVoiceActivityDetector()
            log("VAD (pysilero-vad) Activated.")
        except Exception as e:
            log(f"Lỗi khởi tạo VAD: {e}")
            vad = None

    # Biến theo dõi hoạt động giọng nói
    speech_detected = False
    
    log("Server đang chạy. Đang lắng nghe âm thanh hệ thống...")
    
    while running:
        try:
            chunks = []
            # Check speech in incoming chunks
            chunk_speech_found = False
            
            while not audio_queue.empty():
                chunk = audio_queue.get_nowait()
                chunks.append(chunk)
                
                if vad:
                    try:
                        # pysilero-vad expects bytes (typically 512 samples)
                        if vad(chunk):
                            chunk_speech_found = True
                    except:
                        pass
            
            if chunks:
                if chunk_speech_found:
                    speech_detected = True

                raw_data = b''.join(chunks)
                new_audio = np.frombuffer(raw_data, dtype=np.int16).astype(np.float32) / 32768.0
                audio_buffer = np.concatenate((audio_buffer, new_audio))
                
                # Giảm buffer tối đa
                if len(audio_buffer) > MAX_BUFFER_LEN:
                    audio_buffer = audio_buffer[-int(RATE*5):]

        except queue.Empty:
            time.sleep(0.001)
            continue

        now = time.time()
        
        # Chỉ transcribe nếu có giọng nói mới được phát hiện hoặc không có VAD
        should_transcribe = (speech_detected or (vad is None))

        if (now - last_transcribe_time > TRANSCRIBE_INTERVAL) and \
           (len(audio_buffer) > RATE * MIN_AUDIO_LENGTH) and \
           should_transcribe:
            
            # Reset flag to avoid repeated transcription of the same speech event
            # unless new speech is detected in next chunks
            speech_detected = False 
            
            try:
                with torch.no_grad():
                    results = model.transcribe(
                        audio=(audio_buffer, RATE),
                        language=None,  # Chỉ định trước để nhanh hơn
                    )

                if results and len(results) > 0:
                    current_text = results[0].text.strip()
                    
                    if current_text and current_text != last_sent_text:
                        print(f"\r> {current_text}" + " " * 30, end="", flush=True)
                        socket.send_string(current_text)
                        last_sent_text = current_text
                
                # Dọn cache định kỳ
                transcribe_count += 1
                if transcribe_count % 500 == 0:
                    torch.cuda.empty_cache()
            
            except Exception as e:
                # Bỏ qua lỗi im lặng để tránh spam log
                pass
            
            # Giữ buffer nhỏ hơn (FIX: Dùng int cho slice)
            if len(audio_buffer) > RATE * 3:
                audio_buffer = audio_buffer[-int(RATE*2):]  # Thay đổi từ 1.5 → 2

            last_transcribe_time = now

if __name__ == "__main__":
    t1 = threading.Thread(target=audio_stream_thread)
    t2 = threading.Thread(target=processing_thread)
    t1.start()
    t2.start()
    try:
        while True: time.sleep(0.5)
    except KeyboardInterrupt:
        log("\nStopping...")
        running = False
        t1.join()
        t2.join()
        log("Stopped.")