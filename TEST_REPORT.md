# Validation

Developed on Windows with Python 3.12 and a Pixel 5 using DroidCam. Recognition accuracy and latency depend on camera angle, lighting, hand shape and connection quality.

## Automated coverage

The suite currently contains 60 tests covering:

- Initial pause, deliberate pinch clicks, repeat suppression, cooldown and dwell.
- Drag release on hand loss, palm, ambiguous input, stop and watchdog interruption.
- Relative smoothing/speed limiting, direct mapping and calibration boundaries.
- Automatic resume without overriding emergency/manual stop.
- Relaxed poses, synthetic landmark classification and pinch hysteresis.
- Persistent hand identity, reordered detections, other-hand rejection and switching.
- Real OpenCV capture from a generated loopback MJPEG server and bounded failures.
- Dashboard commands, calibration cancellation, settings, Showcase and navigation.

Mouse actions use fake sinks. Tests do not move or click the physical mouse.

## Runtime and UI checks

- Model loading and blank-frame inference succeeded.
- Live Pixel Wi-Fi capture succeeded at 640×480, visually verified without an HD watermark.
- Embedded preview, Enable, latched Stop and Showcase were exercised with real video and fake mouse output.
- Closing Studio stopped the tracking thread and capture child process.
- Default and minimum-size layouts were visually inspected. Settings scroll while Stop remains accessible.
- Dependency checks passed in the development environment.

These are development checks, not a guarantee on other systems. Physical F8 behavior, calibration, gestures, USB setup, long-session stability and end-to-end latency should be checked on each new installation. Primary-monitor control is supported; secure-desktop interaction is not.
