package com.uras.client;

import org.zeromq.SocketType;
import org.zeromq.ZContext;
import org.zeromq.ZMQ;

import javafx.animation.PauseTransition;
import javafx.application.Platform;
import javafx.scene.control.Label;
import javafx.util.Duration;

public class BackendConnector {

    private final javafx.scene.layout.Pane backgroundPane;
    private final javafx.scene.text.TextFlow subtitleFlow;
    private final Label statusLabel;
    private volatile boolean isRunning = false;
    private Thread listenerThread;
    private Process pythonProcess;
    private PauseTransition autoHideTimer;
    private String currentDisplayedText = "";

    public BackendConnector(javafx.scene.layout.Pane backgroundPane, javafx.scene.text.TextFlow subtitleFlow, Label statusLabel) {
        this.backgroundPane = backgroundPane;
        this.subtitleFlow = subtitleFlow;
        this.statusLabel = statusLabel;

        // Initialize Auto-hide Timer
        Platform.runLater(() -> {
            this.autoHideTimer = new PauseTransition(Duration.seconds(3));
            this.autoHideTimer.setOnFinished(e -> {
                this.subtitleFlow.getChildren().clear();
                this.currentDisplayedText = "";
                // Hide the entire background container
                this.backgroundPane.setVisible(false);
            });
        });
    }

    public void start() {
        if (isRunning) {
            return;
        }
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
        if (text == null || text.trim().isEmpty()) {
            return;
        }

        Platform.runLater(() -> {
            // Ensure background is visible and styled
            backgroundPane.setVisible(true);
            backgroundPane.setStyle(
                    "-fx-background-color: rgba(0,0,0,0.5); "
                    + "-fx-background-radius: 15px; "
                    + "-fx-effect: dropshadow(three-pass-box, rgba(0,0,0,0.8), 10, 0, 0, 0);"
            );

            // Fixed Size for Background
            if (backgroundPane instanceof javafx.scene.layout.Region) {
                ((javafx.scene.layout.Region) backgroundPane).setPrefWidth(900);
                ((javafx.scene.layout.Region) backgroundPane).setMinWidth(900);
                ((javafx.scene.layout.Region) backgroundPane).setPrefHeight(120);
                ((javafx.scene.layout.Region) backgroundPane).setMinHeight(120);
            }

            // --- TEXT PROCESSING ---
            int MAX_CHARS = 130;
            String tempText = text;

            if (tempText.length() > MAX_CHARS) {
                int cutOffIndex = tempText.length() - MAX_CHARS;
                int nextSpace = tempText.indexOf(" ", cutOffIndex);
                if (nextSpace != -1 && nextSpace < tempText.length() - 10) {
                    tempText = "..." + tempText.substring(nextSpace);
                }
            }
            final String finalDisplayText = tempText;

            // --- INTELLIGENT DIFFING & ANIMATION ---
            // 1. Check if new text is an extension of old text
            if (finalDisplayText.startsWith(currentDisplayedText) && !currentDisplayedText.isEmpty()) {
                // APPEND MODE
                String newPart = finalDisplayText.substring(currentDisplayedText.length());
                if (!newPart.isEmpty()) {
                    javafx.scene.text.Text textNode = createStyledText(newPart);
                    textNode.setOpacity(0.0);
                    subtitleFlow.getChildren().add(textNode);
                    animateFadeIn(textNode);
                }
            } else {
                // REPLACE MODE (New sentence or correction)
                subtitleFlow.getChildren().clear();
                javafx.scene.text.Text textNode = createStyledText(finalDisplayText);
                textNode.setOpacity(0.0);
                subtitleFlow.getChildren().add(textNode);
                animateFadeIn(textNode);
            }

            currentDisplayedText = finalDisplayText;

            // Auto-hide logic (Reset timer)
            if (autoHideTimer != null) {
                autoHideTimer.playFromStart();
            }
        });
    }

    private javafx.scene.text.Text createStyledText(String content) {
        javafx.scene.text.Text t = new javafx.scene.text.Text(content);
        t.setFill(javafx.scene.paint.Color.WHITE);
        t.setFont(javafx.scene.text.Font.font("System", javafx.scene.text.FontWeight.BOLD, 25));
        return t;
    }

    private void animateFadeIn(javafx.scene.Node node) {
        javafx.animation.FadeTransition fade = new javafx.animation.FadeTransition(Duration.millis(50), node);
        fade.setFromValue(0.0);
        fade.setToValue(1.0);
        fade.play();
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
