import pyaudio
import wave

def list_devices():
    p = pyaudio.PyAudio()
    info = p.get_host_api_info_by_index(0)
    numdevices = info.get('deviceCount')
    
    print("--- Available Audio Devices ---")
    for i in range(0, numdevices):
        if (p.get_device_info_by_host_api_device_index(0, i).get('maxInputChannels')) > 0:
            dev_name = p.get_device_info_by_host_api_device_index(0, i).get('name')
            print(f"Input Device id {i} - {dev_name}")
    print("-" * 30)
    p.terminate()

def record_test(filename="test_record.wav", duration=3):
    CHUNK = 1024
    FORMAT = pyaudio.paInt16
    CHANNELS = 1
    RATE = 16000
    
    p = pyaudio.PyAudio()

    # Tìm device loopback/mix nếu có
    device_index = None
    for i in range(p.get_device_count()):
        info = p.get_device_info_by_index(i)
        name = info['name'].lower()
        if "stereo mix" in name or "mix" in name:
            device_index = i
            print(f"Auto-selecting Loopback Device: {info['name']}")
            break

    stream = p.open(format=FORMAT,
                    channels=CHANNELS,
                    rate=RATE,
                    input=True,
                    input_device_index=device_index,
                    frames_per_buffer=CHUNK)

    print(f"\n[REC] Recording for {duration} seconds...")
    print("Please speak or play some audio now!")

    frames = []
    for i in range(0, int(RATE / CHUNK * duration)):
        data = stream.read(CHUNK)
        frames.append(data)

    print("[STOP] Recording finished.")

    stream.stop_stream()
    stream.close()
    p.terminate()

    wf = wave.open(filename, 'wb')
    wf.setnchannels(CHANNELS)
    wf.setsampwidth(p.get_sample_size(FORMAT))
    wf.setframerate(RATE)
    wf.writeframes(b''.join(frames))
    wf.close()
    print(f"Saved test file to: {filename}")
    print("Please play this file to confirm audio is clear.")

if __name__ == "__main__":
    list_devices()
    record_test()
