The AI Pest cannon

https://drive.google.com/file/d/1ckHpSCwEQqAl_zVuAT-dxXGfUbC_3At0/view?usp=share_link

Introduction & How It Works

The AI Pest Cannon is a real-time pest detection application for MacOS, Windows, Raspberry Pi, and Linux. It uses a YOLO (You Only Look Once) neural network to analyse a live camera feed and identify animals and pests as they appear. When a pest is confirmed, it triggers an MQTT message and/or GPIO relay to your smart home system — activating a water cannon, sprinkler, siren, or any connected device.
The universal script ai_pest_cannon_universal_v1.py runs on all supported platforms from a single codebase.
The application detects the host platform at startup and displays only the controls relevant to that platform.
Key capabilities: Multi-class YOLO pest detection · Multiple ROI zones · Safe-class global suppression · MQTT / GPIO output · VLC or OpenCV RTSP backend · Hailo NPU on Raspberry Pi · Manual one-shot and timed cannon control · Settings persistence · Detection image saving · Custom alert sound

Detection pipeline:

• Capture — Frames are read from an RTSP network camera, USB webcam, or CSI camera.
• Inference — Each frame (or every Nth frame if skip_frames is set) is passed through the YOLO model, returning
bounding boxes, class labels, and confidence scores.
• Safe-class check — If any safe-class object (e.g. person) appears anywhere in the frame, the cannon is
suppressed — even if a pest is simultaneously in an ROI.
• ROI filtering — Pest detections are matched against your configured ROI zones.
• Confirmation — After confirm_frames consecutive confirmed frames the cannon fires.
• Output — MQTT ON is published and/or a GPIO relay closes. After fire_time seconds MQTT OFF is sent
automatically.
• Holdoff — A cooldown period prevents the cannon re-firing immediately.

Recommended Hardware:

Raspberry Pi 5 with AI HAT+ 26 TOPS plus optional relay board connected to GPIO
12V 1/2" water solenoid valve plus hoze-lock style water hose connectors.
Camera - RTSP, USB or CSI (raspberry Pi camera connector)
Optional - Home assistant running with MQTT server and wifi plugs Local or cloud based, recommend local control - I use Tuya plugs with Tuya local installed in HA via HACS.

Installation:

1.Create a new bootable Raspberry Pi Bookworm 64bit Desktop on a USB thumb drive/SSD or SD card (Do Not Use Trixie)

2.Copy the install folder 'AI Pest Cannon Dist' to your home/pi folder

3.Open a terminal in the install folder and make the installer file executable:
          chmod +x install_raspberry_pi_universal.sh

4.Run the installer file:
          ./install_raspberry_pi_universal.sh

You will be asked to press Y and couple of times while the dependencies are installed. 
Then you will be asked to reboot the Pi:
          sudo reboot

5. Then copy the relevant files to the following locations.

          hailo_models to the ~/home/pi folder (this has the hailo specific models .hef files)
          coco.txt to the ~/home/pi/ai_pest_cannon folder (this is the object class file)
          custom.wav to ~/home/pi/ai_pest_cannon folder (this is the sound played on detection)
          launch_ai_pest_cannon.sh to the ~/home/pi/ai_pest_cannon folder (main launcher file)
          launch_ai_pest_cannon_xcb.sh to the ~/home/pi/ai_pest_cannon folder (alternate main launcher file)

6. Make the launcher files executable:
          chmod +x launch_ai_pest_cannon.sh
          chmod +x launch_ai_pest_cannon_xcb.sh

You can now double click the launch_ai_pest_cannon.sh file or run it in a terminal:
          ./launch_ai_pest_cannon.sh

The App will now launch the GUI. Any detections will be saved in the ~/home/pi/detections folder.
Any logs are saved in the  ~/home/pi/cannon-logs folder.
system settings are saved in /home/pi/.config/ai_pest_cannon/settings.json (this is a hidden folder).

Tips:

Read the User Guide PDF file. (https://drive.google.com/file/d/1ckHpSCwEQqAl_zVuAT-dxXGfUbC_3At0/view?usp=share_link)

Create your own custom sound file, just make sure the name is custom.wav 

RSTP streams are very convenient but a USB or CSI camera gives the best performance 
for inference FPS and object detection. Use the smaller models if required (e.g yolo11n.hef - or yolo11n.pt if using cpu)

The App will function with CPU fallback but it is very slow. Use an AI Hat+ 26TOPS board or raspberry Pi AI Camera which has a Hailo NPU built in for best
performance. Slower than the HAT+ but way better than CPU fallback.

You can use flashing lights, horns or anything else that can be enabled/disabled via a relay to scare off the pests, but an impact sprinkler works very well. Choose your weapons wisely!

The Python Script is cross platform for MacOs(mps Apple Metal), Windows (Cuda) and General Linux. 

Apple MacBook Pro M4 Pro gives amazing results as does a recent RTX GPU on a Window PC.

The object detection is done using the Analytics YOLO Computer vision models. The ones supplied are the standard versions. You can train your own models, yolov8 or yolov11 on Pi with hailo, V8, V11 or V26 on Mac/Windows/Linux etc.

The manual Cannon fire button is linked to a timer. You set it for up to 60 minutes. Very useful if you want to water the garden lawn!

Have Fun and happy Pest Hunting :) 

UPDATES: 

V5 adds inference optimisations for CPU and and adds a log note about imgsz being ignored for Hailo models as the imgsz is fixed at 640.

V8 adds Inverted ROI option to ignore detections where the bounding box center is within the ROI region. This is good for ignoring false positives from features that trigger detections under changing lighting conditions or where a pest class is allowed to be within the full camera frame.

To run the updates, simply edit the launcher file to call the new updated file.



