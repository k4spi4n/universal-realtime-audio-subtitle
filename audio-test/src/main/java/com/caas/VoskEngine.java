package com.caas;

import com.google.gson.Gson;
import com.google.gson.JsonObject;
import javafx.application.Platform;
import javafx.scene.control.Label;
import org.vosk.LibVosk;
import org.vosk.LogLevel;
import org.vosk.Model;
import org.vosk.Recognizer;

import javax.sound.sampled.*;
import java.io.IOException;

public class VoskEngine {

    private final Label subtitleLabel;
    private final Label statusLabel; // Optional status label
    private volatile boolean isRunning = false;
    private TargetDataLine line;
    private final Gson gson = new Gson();
    private String modelPath = "model"; // Default
    private Thread workerThread;

    public VoskEngine(Label subtitleLabel, Label statusLabel) {
        this.subtitleLabel = subtitleLabel;
        this.statusLabel = statusLabel;
    }

    public void setModelPath(String path) {
        this.modelPath = path;
    }

    public void start() {
        if (isRunning) return;
        isRunning = true;
        updateStatus("Starting...");

        workerThread = new Thread(() -> {
            try {
                LibVosk.setLogLevel(LogLevel.WARNINGS);

                updateStatus("Loading Model from: " + modelPath);
                try (Model model = new Model(modelPath)) {

                    float sampleRate = 16000;
                    Recognizer recognizer = new Recognizer(model, sampleRate);

                    AudioFormat format = new AudioFormat(sampleRate, 16, 1, true, false);
                    DataLine.Info info = new DataLine.Info(TargetDataLine.class, format);

                    // --- MIXER SELECTION ---
                    Mixer.Info[] mixerInfos = AudioSystem.getMixerInfo();
                    Mixer mixer = null;

                    for (Mixer.Info mi : mixerInfos) {
                        String name = mi.getName();
                        String desc = mi.getDescription();
                        if (desc.toLowerCase().contains("port")) continue;
                        if (mixer == null && (name.contains("Stereo Mix") || name.contains("立体声混音"))) {
                            mixer = AudioSystem.getMixer(mi);
                        }
                    }

                    if (mixer == null) {
                        // Fallback logic
                        for (Mixer.Info mi : mixerInfos) {
                            try {
                                Mixer m = AudioSystem.getMixer(mi);
                                if (m.isLineSupported(info)) {
                                    mixer = m;
                                    break;
                                }
                            } catch (Exception e) {}
                        }
                    }
                    // -----------------------

                    if (mixer != null) {
                        updateStatus("Using Mixer: " + mixer.getMixerInfo().getName());
                        line = (TargetDataLine) mixer.getLine(info);
                    } else {
                        updateStatus("Using Default Audio System");
                        line = (TargetDataLine) AudioSystem.getLine(info);
                    }
                    
                    line.open(format);
                    line.start();
                    
                    updateStatus("Listening...");
                    System.out.println(">>> VOSK LISTENING");

                    byte[] buffer = new byte[4096];

                    while (isRunning) {
                        int nbytes = line.read(buffer, 0, buffer.length);
                        if (nbytes >= 0) {
                            if (recognizer.acceptWaveForm(buffer, nbytes)) {
                                processResult(recognizer.getResult(), true);
                            } else {
                                processResult(recognizer.getPartialResult(), false);
                            }
                        }
                    }
                }
            } catch (Exception e) {
                e.printStackTrace();
                updateStatus("Error: " + e.getMessage());
            } finally {
                isRunning = false;
                updateStatus("Stopped");
            }
        });
        workerThread.start();
    }

    private void updateStatus(String msg) {
        System.out.println("[Status] " + msg);
        if (statusLabel != null) {
            Platform.runLater(() -> statusLabel.setText(msg));
        }
    }

    private String lastText = "";

    private void processResult(String json, boolean isFinal) {
        JsonObject jsonObj = gson.fromJson(json, JsonObject.class);
        String text = "";

        if (isFinal) {
            if (jsonObj.has("text")) text = jsonObj.get("text").getAsString();
        } else {
            if (jsonObj.has("partial")) text = jsonObj.get("partial").getAsString();
        }

        if (!text.isEmpty()) {
            // System.out.println((isFinal ? "Final: " : "Partial: ") + text);
        }

        // Optimization: Don't update if text hasn't changed
        if (text.equals(lastText)) {
            return;
        }
        lastText = text;

        final String fullText = text;
        
        Platform.runLater(() -> {
            String displayText = fullText;

            // Nếu text rỗng (im lặng), ẩn background
            if (displayText.isEmpty()) {
                subtitleLabel.setText("");
                subtitleLabel.setStyle("-fx-background-color: transparent;");
                return;
            }

            // Xử lý Partial quá dài (Sliding Window)
            // Nếu câu chưa chốt mà dài quá 100 ký tự, chỉ hiện 100 ký tự cuối
            if (!isFinal && displayText.length() > 100) {
                displayText = "..." + displayText.substring(displayText.length() - 100);
            }

            subtitleLabel.setText(displayText);

            // Hiệu ứng màu
            if (isFinal) {
                // Final: Màu trắng, hiện full
                subtitleLabel.setStyle("-fx-text-fill: white; -fx-background-color: rgba(0,0,0,0.6); -fx-padding: 10px; -fx-font-size: 24px;");
                
                // Tự động xóa sau 3 giây (để màn hình đỡ vướng)
                new Thread(() -> {
                    try { Thread.sleep(3000); } catch (InterruptedException e) {}
                    Platform.runLater(() -> {
                        if (subtitleLabel.getText().equals(fullText)) {
                             subtitleLabel.setText("");
                             subtitleLabel.setStyle("-fx-background-color: transparent;");
                        }
                    });
                }).start();
                
            } else {
                // Partial: Màu vàng
                subtitleLabel.setStyle("-fx-text-fill: yellow; -fx-background-color: rgba(0,0,0,0.6); -fx-padding: 10px; -fx-font-size: 24px;");
            }
        });
    }

    public void stop() {
        isRunning = false;
        if (line != null) {
            line.stop();
            line.close();
        }
    }
}
