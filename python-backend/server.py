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
TRANSCRIBE_INTERVAL = 0.2
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
        max_inference_batch_size=-1,
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

# Khởi tạo VAD toàn cục (để dùng trong thread thu âm)
vad_model = None
if HAS_VAD:
    try:
        vad_model = SileroVoiceActivityDetector()
        log("VAD (pysilero-vad) Pre-loaded for Stream Thread.")
    except Exception as e:
        log(f"Lỗi khởi tạo VAD: {e}")

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
        
        log("Audio Stream Thread Started (Pre-calc: Float32 & VAD)")

        while running:
            # 1. Đọc dữ liệu thô (Bytes)
            raw_data = stream.read(CHUNK, exception_on_overflow=False)
            
            # 2. Tính toán trước: VAD
            is_speech = False
            if vad_model:
                try:
                    if vad_model(raw_data):
                        is_speech = True
                except:
                    pass
            
            # 3. Tính toán trước: Convert sang Float32
            # (Làm ngay lập tức để giảm tải cho luồng xử lý chính)
            float_data = np.frombuffer(raw_data, dtype=np.int16).astype(np.float32) / 32768.0
            
            # Đẩy cả dữ liệu đã xử lý và flag VAD vào hàng đợi
            audio_queue.put((float_data, is_speech))

    except Exception as e:
        log(f"Lỗi Stream Audio: {e}")
    finally:
        stream.stop_stream()
        stream.close()
        p.terminate()

def processing_thread():
    global running
    
    # Sử dụng deque để quản lý buffer hiệu quả hơn (tránh np.concatenate liên tục)
    from collections import deque
    audio_buffer_chunks = deque()
    current_buffer_length = 0
    
    last_transcribe_time = time.time()
    last_sent_text = ""

    # Giới hạn buffer (tính theo số lượng chunks)
    # MAX_BUFFER_LEN (samples) / CHUNK (samples per chunk)
    MAX_CHUNKS = int((RATE * 10) / CHUNK)
    
    # Biến theo dõi hoạt động giọng nói (tích lũy từ stream thread)
    speech_detected_accumulated = False
    
    log("Processing Thread Started (Fast Buffer & Inference)")
    
    while running:
        try:
            # Lấy tất cả dữ liệu từ hàng đợi
            has_new_data = False
            while not audio_queue.empty():
                float_chunk, chunk_is_speech = audio_queue.get_nowait()
                
                # Cập nhật trạng thái VAD
                if chunk_is_speech:
                    speech_detected_accumulated = True
                
                # Thêm vào buffer
                audio_buffer_chunks.append(float_chunk)
                current_buffer_length += len(float_chunk)
                has_new_data = True
            
            if not has_new_data:
                time.sleep(0.005) # Ngủ ngắn hơn chút
                continue

            # Quản lý kích thước buffer (Rolling window)
            while len(audio_buffer_chunks) > MAX_CHUNKS:
                removed_chunk = audio_buffer_chunks.popleft()
                current_buffer_length -= len(removed_chunk)

        except queue.Empty:
            continue

        now = time.time()
        
        # Logic quyết định transcribe
        should_transcribe = (speech_detected_accumulated or (vad_model is None))

        # Điều kiện thời gian và độ dài tối thiểu
        if (now - last_transcribe_time > TRANSCRIBE_INTERVAL) and \
           (current_buffer_length > RATE * MIN_AUDIO_LENGTH) and \
           should_transcribe:
            
            # Reset cờ phát hiện giọng nói
            speech_detected_accumulated = False 
            
            try:
                # Gộp buffer chỉ khi cần inference (Lazy concatenation)
                # Chuyển deque thành list rồi thành array nhanh hơn concat từng cái
                full_audio = np.concatenate(list(audio_buffer_chunks))

                with torch.no_grad():
                    results = model.transcribe(
                        audio=(full_audio, RATE),
                        language=None, 
                    )

                if results and len(results) > 0:
                    current_text = results[0].text.strip()
                    
                    if current_text and current_text != last_sent_text:
                        print(f"\r> {current_text}" + " " * 30, end="", flush=True)
                        socket.send_string(current_text)
                        last_sent_text = current_text
            
            
            except Exception as e:
                pass
            
            KEEP_CHUNKS = int((RATE * 2) / CHUNK)
            while len(audio_buffer_chunks) > KEEP_CHUNKS:
                removed = audio_buffer_chunks.popleft()
                current_buffer_length -= len(removed)

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