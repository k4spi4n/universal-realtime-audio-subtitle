package com.caas;

import javafx.application.Platform;
import javafx.geometry.Pos;
import javafx.scene.control.Label;
import org.zeromq.SocketType;
import org.zeromq.ZContext;
import org.zeromq.ZMQ;
import javafx.animation.PauseTransition;
import javafx.util.Duration;

public class BackendConnector {

    private final Label subtitleLabel;
    private final Label statusLabel;
    private volatile boolean isRunning = false;
    private Thread listenerThread;
    private Process pythonProcess;
    private PauseTransition autoHideTimer;

    public BackendConnector(Label subtitleLabel, Label statusLabel) {
        this.subtitleLabel = subtitleLabel;
        this.statusLabel = statusLabel;

        // Initialize Auto-hide Timer
        Platform.runLater(() -> {
            this.autoHideTimer = new PauseTransition(Duration.seconds(3));
            this.autoHideTimer.setOnFinished(e -> {
                this.subtitleLabel.setText("");
                // Khi ẩn, ta đưa về trong suốt
                this.subtitleLabel.setStyle("-fx-background-color: transparent;");
                // Reset kích thước để không chiếm chỗ vô hình (nếu cần)
                // Tuy nhiên để mượt mà, ta có thể giữ nguyên hoặc chỉ ẩn màu nền.
            });
        });
    }

    public void start() {
        if (isRunning) return;
        isRunning = true;
        updateStatus("Starting Python Backend...");

        // 2. Start ZMQ Listener
        listenerThread = Thread.ofVirtual().name("zmq-virtual-worker").start(() -> {
            try (ZContext context = new ZContext()) {
                updateStatus("Connecting to ZMQ Server (Virtual Thread)...");
                ZMQ.Socket subscriber = context.createSocket(SocketType.SUB);
                subscriber.connect("tcp://localhost:5555");
                subscriber.subscribe(ZMQ.SUBSCRIPTION_ALL); 

                updateStatus("Connected & Listening...");

                while (isRunning && !Thread.currentThread().isInterrupted()) {
                    String msg = subscriber.recvStr(0); 
                    if (msg != null) {
                        processResult(msg);
                    }
                }
            } catch (Exception e) {
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

        Platform.runLater(() -> {
            // --- CẤU HÌNH CỐ ĐỊNH KÍCH THƯỚC (Fixed Layout) ---
            subtitleLabel.setWrapText(true);
            
            // Cố định chiều rộng và chiều cao
            // 900px chiều rộng
            // 120px chiều cao (đủ cho 2 dòng font 26px + padding)
            subtitleLabel.setPrefWidth(900);
            subtitleLabel.setMinWidth(900);
            subtitleLabel.setPrefHeight(120); 
            subtitleLabel.setMinHeight(120);
            
            // Căn giữa nội dung trong khung
            subtitleLabel.setAlignment(Pos.CENTER); 

            // --- XỬ LÝ TEXT ---
            int MAX_CHARS = 130; // Giảm nhẹ limit để đảm bảo vừa đẹp 2 dòng
            String tempText = text; 

            if (tempText.length() > MAX_CHARS) {
                int cutOffIndex = tempText.length() - MAX_CHARS;
                int nextSpace = tempText.indexOf(" ", cutOffIndex);
                if (nextSpace != -1 && nextSpace < tempText.length() - 10) {
                     tempText = "..." + tempText.substring(nextSpace);
                }
            }
            
            final String finalDisplayText = tempText; 

            subtitleLabel.setText(finalDisplayText);
            
            // Style cố định: padding rộng hơn để chữ nằm giữa đẹp mắt
            subtitleLabel.setStyle(
                "-fx-text-fill: white; " + 
                "-fx-background-color: rgba(0,0,0,0.6); " + 
                "-fx-padding: 10px; " + 
                "-fx-font-size: 26px; " + 
                "-fx-font-weight: bold; " + // Thêm bold cho rõ
                "-fx-background-radius: 15px; " + // Bo tròn mềm mại hơn
                "-fx-effect: dropshadow(three-pass-box, rgba(0,0,0,0.8), 10, 0, 0, 0);" // Thêm bóng đổ cho chữ nổi
            );

            // Auto-hide logic (Reset timer)
            if (autoHideTimer != null) {
                autoHideTimer.playFromStart();
            }
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
