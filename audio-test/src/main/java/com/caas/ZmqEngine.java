package com.caas;

import javafx.application.Platform;
import javafx.scene.control.Label;
import org.zeromq.SocketType;
import org.zeromq.ZContext;
import org.zeromq.ZMQ;

public class ZmqEngine {

    private final Label subtitleLabel;
    private final Label statusLabel;
    private volatile boolean isRunning = false;
    private Thread listenerThread;
    private Process pythonProcess;

    public ZmqEngine(Label subtitleLabel, Label statusLabel) {
        this.subtitleLabel = subtitleLabel;
        this.statusLabel = statusLabel;
    }

    public void start() {
        if (isRunning) return;
        isRunning = true;
        updateStatus("Starting Python Backend...");

        // 1. Start Python Process (Optional)
        // ... (Code khởi chạy python giữ nguyên ở App.java hoặc xử lý tại đây nếu cần)

        // 2. Start ZMQ Listener using Java 21 VIRTUAL THREADS
        // Virtual threads cực nhẹ, tối ưu cho các tác vụ blocking I/O như mạng (ZeroMQ)
        listenerThread = Thread.ofVirtual().name("zmq-virtual-worker").start(() -> {
            try (ZContext context = new ZContext()) {
                updateStatus("Connecting to ZMQ Server (Virtual Thread)...");
                ZMQ.Socket subscriber = context.createSocket(SocketType.SUB);
                subscriber.connect("tcp://localhost:5555");
                subscriber.subscribe(ZMQ.SUBSCRIPTION_ALL); 

                updateStatus("Connected & Listening...");

                while (isRunning && !Thread.currentThread().isInterrupted()) {
                    // Blocking receive is fine with Virtual Threads!
                    // Nó sẽ unmount khỏi OS thread khi block, giúp tối ưu CPU tối đa.
                    String msg = subscriber.recvStr(0); 
                    if (msg != null) {
                        processResult(msg);
                    }
                }
            } catch (Exception e) {
                // Ignore interruption during stop
                if (isRunning) {
                    e.printStackTrace();
                    updateStatus("ZMQ Error: " + e.getMessage());
                }
            }
        });
    }

    private void updateStatus(String msg) {
        System.out.println("[ZMQ-Java] " + msg);
        if (statusLabel != null) {
            Platform.runLater(() -> statusLabel.setText(msg));
        }
    }

    private void processResult(String text) {
        if (text == null || text.trim().isEmpty()) return;

        // System.out.println("Received: " + text); // Debug log

        Platform.runLater(() -> {
            // Cấu hình Label để hỗ trợ xuống dòng
            subtitleLabel.setWrapText(true);
            subtitleLabel.setMaxWidth(900); // Giới hạn chiều rộng để text xuống dòng đẹp
            
            String displayText = text;

            // --- XỬ LÝ HIỂN THỊ (VISUAL SLIDING WINDOW) ---
            // Nếu câu quá dài (> 150 ký tự), cắt bớt phần đầu
            int MAX_CHARS = 150;
            String tempText = text; // Dùng biến tạm để xử lý logic cắt chuỗi

            if (tempText.length() > MAX_CHARS) {
                // Lấy phần dư ra (ví dụ: chuỗi dài 200, lấy từ index 50 trở đi)
                int cutOffIndex = tempText.length() - MAX_CHARS;
                
                // Tìm khoảng trắng gần nhất sau điểm cắt để không chém đôi từ
                int nextSpace = tempText.indexOf(" ", cutOffIndex);
                
                if (nextSpace != -1 && nextSpace < tempText.length() - 10) {
                     tempText = "..." + tempText.substring(nextSpace);
                }
            }
            
            final String finalDisplayText = tempText; // Biến final để dùng trong Lambda
            // ----------------------------------------------

            subtitleLabel.setText(finalDisplayText);
            subtitleLabel.setStyle("-fx-text-fill: white; -fx-background-color: rgba(0,0,0,0.6); -fx-padding: 15px; -fx-font-size: 26px; -fx-background-radius: 10px;");

            // Auto-hide logic (Reset nếu không có update mới sau 3s)
            new Thread(() -> {
                try { Thread.sleep(3000); } catch (InterruptedException e) {}
                Platform.runLater(() -> {
                    // Chỉ ẩn nếu text trên màn hình vẫn là text cũ (chưa có câu mới đè lên)
                    if (subtitleLabel.getText().endsWith(finalDisplayText.substring(Math.max(0, finalDisplayText.length() - 10)))) {
                        subtitleLabel.setText("");
                        subtitleLabel.setStyle("-fx-background-color: transparent;");
                    }
                });
            }).start();
        });
    }

    public void stop() {
        isRunning = false;
        if (listenerThread != null) {
            listenerThread.interrupt();
        }
        if (pythonProcess != null) {
            pythonProcess.destroy();
        }
        updateStatus("Stopped");
    }
}
