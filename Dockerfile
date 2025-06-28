FROM ubuntu:22.04

# Install Xfce desktop, VNC server, and noVNC web client
ENV DEBIAN_FRONTEND=noninteractive
RUN apt-get update && apt-get install -y --no-install-recommends \
    xfce4 xfce4-terminal x11vnc tigervnc-standalone-server \
    novnc websockify wget net-tools ca-certificates && \
    apt-get clean && rm -rf /var/lib/apt/lists/*

# Set a default VNC password (change as needed for security)
ENV VNC_PASSWORD=password

# Startup script to launch Xfce and VNC/noVNC
COPY start.sh /start.sh
RUN chmod +x /start.sh

# Expose VNC and noVNC ports
EXPOSE 5900 6080

# Start the desktop on container run
CMD ["/start.sh"]
