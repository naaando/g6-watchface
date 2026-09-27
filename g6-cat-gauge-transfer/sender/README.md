# Dial Sender for Android

Android application to send custom watchfaces (dials) to supported smartwatches (e.g., Kronos Thunder) using the BLE protocol.

## Features

*   **BLE Connectivity**: Connects to supported smartwatches.
*   **Custom Protocol**: Implements the reverse-engineered transfer protocol used by Co-Fit/STF apps.
*   **Optimized Transfer**: Uses 1012-byte payload chunks with correct header alignment for reliable transfer.
*   **Auth & Setup**: Handles the specific handshake, binding, and login sequence required by the device.

## Usage

1.  Build the APK using Android Studio or Gradle (`./gradlew assembleDebug`).
2.  Install on an Android device.
3.  Ensure Bluetooth is enabled and the watch is paired (or discoverable).
4.  Open the app, scan/connect to the watch.
5.  Select a valid `.bin` dial file.
6.  The app will handle authentication and transfer the file.

## Technical Details

*   **Protocol**: STF/Co-Fit proprietary BLE protocol.
*   **Chunk Size**: 1012 bytes payload + 9 bytes header = 1021 bytes (approx).
*   **Verification**: Uses file size as ID in the stream header.

## G6 test asset

The project includes `dials/cat-gauge-analog-test.bin`, built from the G6 `AM05` block layout. When the app is built and installed, it appears in the built-in dial list and can be selected for a controlled transfer test. The transfer should be attempted only while AuraFit is disconnected from the G6; do not run it during firmware or resource updates.

## Disclaimer

This software is for educational and research purposes. Use at your own risk.
