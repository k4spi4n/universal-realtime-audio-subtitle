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

        System.out.println("Received: " + text);

        Platform.runLater(() -> {
            subtitleLabel.setText(text);
            subtitleLabel.setStyle("-fx-text-fill: white; -fx-background-color: rgba(0,0,0,0.6); -fx-padding: 10px; -fx-font-size: 24px;");

            // Auto-hide logic
            new Thread(() -> {
                try { Thread.sleep(3000); } catch (InterruptedException e) {}
                Platform.runLater(() -> {
                    if (subtitleLabel.getText().equals(text)) {
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
