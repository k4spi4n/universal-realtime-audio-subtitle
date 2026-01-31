import zmq
import sys

def run_subscriber():
    print("--- ZMQ Subscriber Test Client ---")
    print("Connecting to tcp://localhost:5555...")
    
    context = zmq.Context()
    socket = context.socket(zmq.SUB)
    
    # Kết nối đến server
    try:
        socket.connect("tcp://localhost:5555")
        # Đăng ký nhận tất cả các tin nhắn (topic rỗng)
        socket.subscribe("")
    except Exception as e:
        print(f"Error connecting: {e}")
        return

    print("Listening for subtitles... (Press Ctrl+C to stop)")
    print("Make sure 'server.py' is running in another terminal!")
    print("-" * 40)

    try:
        while True:
            # Chờ nhận tin nhắn
            message = socket.recv_string()
            print(f"Received: {message}")
    except KeyboardInterrupt:
        print("\nStopped.")
    finally:
        socket.close()
        context.term()

if __name__ == "__main__":
    run_subscriber()
