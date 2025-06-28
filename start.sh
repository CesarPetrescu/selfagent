#!/bin/bash
export DISPLAY=:0
# Start a virtual framebuffer X server (Xvfb) in the background
Xvfb :0 -screen 0 1280x720x24 &

# Start the Xfce4 desktop session (this will connect to DISPLAY :0)
startxfce4 &

# Wait a few seconds for Xfce to start...
sleep 2

# Launch the VNC server on DISPLAY :0 with the given password
echo "$VNC_PASSWORD" | vncpasswd -f > /root/.vnc/passwd
chmod 600 /root/.vnc/passwd
tigervncserver -geometry 1280x720 :0

# Launch noVNC to serve a web interface on port 6080
websockify --web=/usr/share/novnc/ --prefer-ipv4 6080 localhost:5900
