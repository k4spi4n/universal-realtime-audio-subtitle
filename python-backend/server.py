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
from collections import deque

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

# --- TỐI ƯU CUDA ---
try:
    torch.backends.cudnn.conv.fp32_precision = 'tf32'
    torch.backends.cuda.matmul.fp32_precision = 'tf32'
except AttributeError:
    torch.backends.cuda.matmul.allow_tf32 = True
    torch.backends.cudnn.allow_tf32 = True

# --- ZMQ SETUP ---
PORT = 5555
context = zmq.Context()
socket = context.socket(zmq.PUB)

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

# --- CONSTANTS & PRE-CALCULATIONS (TIỀN TÍNH TOÁN) ---
# Quy tắc: Không thực hiện phép tính trong vòng lặp nếu là hằng số.
FORMAT = pyaudio.paInt16
CHANNELS = 1
RATE = 16000
CHUNK = 512
TRANSCRIBE_INTERVAL = 0.2
MIN_AUDIO_LENGTH = 0.2

# 1. Biến đổi phép chia Int16 sang Float32 thành phép nhân
# Thay vì x / 32768.0, ta dùng x * (1.0/32768.0)
INT16_SCALE = np.float32(1.0 / 32768.0)

# 2. Tiền tính toán số mẫu (samples) tối thiểu cần thiết để transcribe
# Tránh việc tính (RATE * MIN_AUDIO_LENGTH) trong vòng lặp while
MIN_SAMPLES_THRESHOLD = int(RATE * MIN_AUDIO_LENGTH)

# 3. Tiền tính toán giới hạn bộ nhớ đệm
# Tính trước số lượng chunk tối đa và số lượng chunk giữ lại
# Thay vì phép chia, ta tính một lần ở đây.
MAX_CHUNKS = int((RATE * 10) / CHUNK) 
KEEP_CHUNKS = int((RATE * 2) / CHUNK)

# --- AUTO-KILL & SETUP MIC ---
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
            log(f"CẢNH BÁO: Dùng mặc định: {default_device['name']}")
        except:
            sys.exit(1)
    p.terminate()
    return final_id

MIC_INDEX = find_stereo_mix_index()

from qwen_asr import Qwen3ASRModel
log("Đang khởi động Qwen3-ASR-0.6B")

try:
    if not torch.cuda.is_available():
        sys.exit(1)

    model = Qwen3ASRModel.from_pretrained(
        "Qwen/Qwen3-ASR-0.6B",
        dtype=torch.bfloat16, 
        max_inference_batch_size=-1,
        device_map="cuda:0", 
        attn_implementation="sdpa", 
        max_new_tokens=128
    )
    log(f"Model Ready!")
except Exception as e:
    log(f"LỖI LOAD MODEL: {e}")
    sys.exit(1)

audio_queue = queue.Queue()
running = True
vad_model = None
if HAS_VAD:
    try:
        vad_model = SileroVoiceActivityDetector()
        log("VAD Ready.")
    except: pass

def audio_stream_thread():
    p = pyaudio.PyAudio()
    # Sử dụng hằng số đã tính trước INT16_SCALE
    local_scale = INT16_SCALE 
    
    try:
        stream = p.open(format=FORMAT, channels=CHANNELS, rate=RATE, input=True,
                        input_device_index=MIC_INDEX, frames_per_buffer=CHUNK,
                        stream_callback=None)
        
        log("Stream Started.")

        while running:
            raw_data = stream.read(CHUNK, exception_on_overflow=False)
            
            is_speech = False
            if vad_model:
                try:
                    if vad_model(raw_data): is_speech = True
                except: pass

            # TỐI ƯU HÓA: Dùng phép nhân thay vì phép chia
            # np.frombuffer tốn ít CPU, astype tốn một chút
            # Phép nhân vector ở đây rất nhanh nhờ numpy SIMD
            float_data = np.frombuffer(raw_data, dtype=np.int16).astype(np.float32)
            float_data *= local_scale 

            audio_queue.put((float_data, is_speech))

    except Exception as e:
        log(f"Lỗi Stream: {e}")
    finally:
        stream.stop_stream(); stream.close(); p.terminate()

def processing_thread():
    global running
    
    audio_buffer_chunks = deque()
    current_buffer_length = 0 # Đếm số lượng samples
    
    last_transcribe_time = time.time()
    last_sent_text = ""
    
    speech_detected_accumulated = False
    
    # Cache các biến global vào local để truy xuất nhanh hơn trong vòng lặp
    local_max_chunks = MAX_CHUNKS
    local_keep_chunks = KEEP_CHUNKS
    local_min_samples = MIN_SAMPLES_THRESHOLD
    local_interval = TRANSCRIBE_INTERVAL
    
    log("Processing Started (Optimized Math).")
    
    while running:
        try:
            # Lấy dữ liệu không chặn (Non-blocking)
            has_new_data = False
            while not audio_queue.empty():
                float_chunk, chunk_is_speech = audio_queue.get_nowait()
                if chunk_is_speech: speech_detected_accumulated = True
                
                audio_buffer_chunks.append(float_chunk)
                current_buffer_length += len(float_chunk) # Phép cộng số nguyên cực nhanh
                has_new_data = True
            
            if not has_new_data:
                time.sleep(0.005)
                continue

            # TỐI ƯU: So sánh với biến int đã tính trước, không thực hiện phép chia/nhân ở đây
            while len(audio_buffer_chunks) > local_max_chunks:
                removed_chunk = audio_buffer_chunks.popleft()
                current_buffer_length -= len(removed_chunk)

        except queue.Empty:
            continue

        now = time.time()
        should_transcribe = (speech_detected_accumulated or (vad_model is None))

        # TỐI ƯU: So sánh (current_buffer_length > local_min_samples)
        # Thay vì (current_buffer_length > RATE * MIN_AUDIO_LENGTH) -> Đã loại bỏ phép nhân trong loop
        if (now - last_transcribe_time > local_interval) and \
           (current_buffer_length > local_min_samples) and \
           should_transcribe:
            
            speech_detected_accumulated = False 
            
            try:
                # Concatenate là thao tác tốn kém nhất ở đây (Memory copy)
                # Không thể tránh khỏi nhưng deque giúp giảm số lần re-allocation trước đó
                full_audio = np.concatenate(list(audio_buffer_chunks))

                with torch.inference_mode():
                    # Tuple (full_audio, RATE) không tốn tính toán
                    results = model.transcribe(audio=(full_audio, RATE), language=None)

                if results and len(results) > 0:
                    current_text = results[0].text.strip()
                    if current_text and current_text != last_sent_text:
                        print(f"\r> {current_text}" + " " * 30, end="", flush=True)
                        socket.send_string(current_text)
                        last_sent_text = current_text
            
            except Exception: pass
            
            # Dọn dẹp buffer
            while len(audio_buffer_chunks) > local_keep_chunks:
                removed = audio_buffer_chunks.popleft()
                current_buffer_length -= len(removed)

            last_transcribe_time = now

if __name__ == "__main__":
    t1 = threading.Thread(target=audio_stream_thread)
    t2 = threading.Thread(target=processing_thread)
    t1.start(); t2.start()
    try:
        while True: time.sleep(0.5)
    except KeyboardInterrupt:
        running = False
        t1.join(); t2.join()