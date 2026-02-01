package com.uras.client;

import javafx.application.Application;
import javafx.application.Platform;
import javafx.geometry.Pos;
import javafx.scene.Scene;
import javafx.scene.control.Button;
import javafx.scene.control.Label;
import javafx.scene.layout.HBox;
import javafx.scene.layout.StackPane;
import javafx.scene.layout.VBox;
import javafx.scene.paint.Color;
import javafx.stage.Stage;
import javafx.stage.StageStyle;

public class App extends Application {

    private BackendConnector engine;
    private Stage subtitleStage;
    private Process pythonProcess;

    @Override
    public void start(Stage controlStage) {
        // --- 1. Subtitle Window (Transparent) ---
        // Container for background (Visible box)
        StackPane subtitleContainer = new StackPane();
        subtitleContainer.setStyle("-fx-background-color: rgba(0, 0, 0, 0.5); -fx-background-radius: 15px;");
        subtitleContainer.setMaxSize(900, 120); 

        // TextFlow for advanced text handling (Karaoke style)
        javafx.scene.text.TextFlow subtitleFlow = new javafx.scene.text.TextFlow();
        subtitleFlow.setTextAlignment(javafx.scene.text.TextAlignment.CENTER);
        subtitleFlow.setPadding(new javafx.geometry.Insets(10));
        subtitleFlow.setStyle("-fx-background-color: transparent;");

        // Initial loading text
        javafx.scene.text.Text loadingText = new javafx.scene.text.Text("URAS Engine Loading...");
        loadingText.setFill(Color.WHITE);
        loadingText.setFont(javafx.scene.text.Font.font("System", javafx.scene.text.FontWeight.BOLD, 24));
        subtitleFlow.getChildren().add(loadingText);
        
        subtitleContainer.getChildren().add(subtitleFlow);

        StackPane subRoot = new StackPane(subtitleContainer);
        subRoot.setStyle("-fx-background-color: transparent;");

        // Draggable logic
        final double[] xOffset = new double[1];
        final double[] yOffset = new double[1];
        subRoot.setOnMousePressed(event -> {
            xOffset[0] = event.getSceneX();
            yOffset[0] = event.getSceneY();
        });
        subRoot.setOnMouseDragged(event -> {
            subtitleStage.setX(event.getScreenX() - xOffset[0]);
            subtitleStage.setY(event.getScreenY() - yOffset[0]);
        });

        Scene subScene = new Scene(subRoot, 1000, 150);
        subScene.setFill(Color.TRANSPARENT);

        subtitleStage = new Stage();
        subtitleStage.initStyle(StageStyle.TRANSPARENT);
        subtitleStage.setAlwaysOnTop(true);
        subtitleStage.setScene(subScene);

        // Position at bottom
        javafx.geometry.Rectangle2D screenBounds = javafx.stage.Screen.getPrimary().getVisualBounds();
        subtitleStage.setX((screenBounds.getWidth() - 1000) / 2);
        subtitleStage.setY(screenBounds.getHeight() - 200);
        subtitleStage.show();

        // --- 2. Control Panel Window ---
        Label statusLabel = new Label("Status: Ready");
        statusLabel.setStyle("-fx-font-weight: bold;");

        Button btnStart = new Button("Start");
        Button btnStop = new Button("Stop");
        Button btnReset = new Button("Reset");

        // Engine Setup (ZMQ Listener)
        engine = new BackendConnector(subtitleContainer, subtitleFlow, statusLabel);

        // Start Python Backend Automatically
        startPythonBackend();

        // Button Actions
        btnStart.setOnAction(e -> engine.start());
        
        btnStop.setOnAction(e -> engine.stop());
        
        btnReset.setOnAction(e -> {
            engine.stop();
            Platform.runLater(() -> subtitleFlow.getChildren().clear()); // Clear text
            new Thread(() -> { 
                try { Thread.sleep(500); } catch (InterruptedException ex) {}
                Platform.runLater(engine::start);
            }).start();
        });

        HBox buttons = new HBox(10, btnStart, btnStop, btnReset);
        buttons.setAlignment(Pos.CENTER);

        VBox controlLayout = new VBox(20, new Label("Universal Realtime Audio Subtitle"), statusLabel, buttons);
        controlLayout.setAlignment(Pos.CENTER);
        controlLayout.setStyle("-fx-padding: 20px;");

        Scene controlScene = new Scene(controlLayout, 350, 200);
        controlStage.setTitle("URAS Controller");
        controlStage.setScene(controlScene);
        controlStage.show();

        // Auto-start listener
        engine.start();

        // Exit handler
        controlStage.setOnCloseRequest(e -> {
            engine.stop();
            if (pythonProcess != null) pythonProcess.destroy();
            Platform.exit();
            System.exit(0);
        });
    }

    private void startPythonBackend() {
        new Thread(() -> {
            try {
                // Adjust path as needed. Assuming running from project root or having 'python-backend' sibling.
                // We will try to find the script relative to current working dir.
                String scriptPath = "python-backend/server.py";
                java.io.File scriptFile = new java.io.File(scriptPath);
                
                // Fallback check if we are in 'audio-test' directory
                if (!scriptFile.exists()) {
                    scriptPath = "../python-backend/server.py";
                }

                System.out.println("Launching Python backend: " + scriptPath);
                
                ProcessBuilder pb = new ProcessBuilder("python", scriptPath);
                pb.inheritIO(); // Show python logs in Java console
                pythonProcess = pb.start();
            } catch (Exception e) {
                e.printStackTrace();
                Platform.runLater(() -> new javafx.scene.control.Alert(javafx.scene.control.Alert.AlertType.ERROR, "Failed to start Python backend: " + e.getMessage()).show());
            }
        }).start();
    }

    public static void main(String[] args) {
        launch();
    }
}