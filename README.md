# selfagent

Autonomous Self Agent - Everything self-hosted.

## Overview

This project recreates the idea of [E2B's Desktop Sandbox](https://e2b.dev) entirely on a single host using Docker. Three containers work together:

- **GUI sandbox** – provides an isolated desktop environment via VNC
- **Agent** – connects to your OpenAI-compatible API and controls the sandbox
- **Chat interface** – lets you send instructions and watch the agent act

## Prerequisites

- Linux host with Docker and Docker Compose
- Access to an OpenAI-compatible API
- Copy `.env.example` to `.env` and fill in your credentials:

```bash
LLM_API_BASE_URL="http://192.168.10.142:80/v1"
LLM_MODEL="gpt-4-vision"
LLM_API_KEY="YOUR_API_BEARER_TOKEN"
VNC_PASSWORD="password"
```

## Step 1: Build the GUI Sandbox

Create `Dockerfile`:

```Dockerfile
FROM ubuntu:22.04
ENV DEBIAN_FRONTEND=noninteractive
RUN apt-get update && apt-get install -y --no-install-recommends \
    xfce4 xfce4-terminal x11vnc tigervnc-standalone-server \
    novnc websockify wget net-tools ca-certificates && \
    apt-get clean && rm -rf /var/lib/apt/lists/*
ENV VNC_PASSWORD=password
COPY start.sh /start.sh
RUN chmod +x /start.sh
EXPOSE 5900 6080
CMD ["/start.sh"]
```

`start.sh` launches Xfce, VNC and noVNC:

```bash
#!/bin/bash
export DISPLAY=:0
Xvfb :0 -screen 0 1280x720x24 &
startxfce4 &
sleep 2
echo "$VNC_PASSWORD" | vncpasswd -f > /root/.vnc/passwd
chmod 600 /root/.vnc/passwd
tigervncserver -geometry 1280x720 :0
websockify --web=/usr/share/novnc/ --prefer-ipv4 6080 localhost:5900
```

Add the service to `docker-compose.yml`:

```yaml
services:
  sandbox:
    build: .
    container_name: sandbox
    ports:
      - "5900:5900"
      - "6080:6080"
    environment:
      - VNC_PASSWORD=password
    networks:
      - ai_desktop_net
```

The sandbox exposes its VNC server on port `5900`. Use a VNC client or the
provided noVNC interface on port `6080` to view the desktop.

## Step 2: Build the Agent

`Dockerfile.agent`:

```Dockerfile
FROM python:3.10-slim
WORKDIR /app
COPY requirements.txt .
RUN pip install -r requirements.txt
COPY agent.py .
ENV PYTHONUNBUFFERED=1
CMD ["python", "agent.py"]
```

`requirements.txt`:

```text
requests
vncdotool
Pillow
```

The agent connects to the sandbox VNC server, captures screenshots and queries the LLM API for actions. See `agent.py` for the full loop.

Add the service:

```yaml
  agent:
    build:
      context: .
      dockerfile: Dockerfile.agent
    container_name: agent
    depends_on:
      - sandbox
    environment:
      - LLM_API_BASE_URL=${LLM_API_BASE_URL}
      - LLM_MODEL=${LLM_MODEL}
      - LLM_API_KEY=${LLM_API_KEY}
      - VNC_PASSWORD=${VNC_PASSWORD:-password}
    networks:
      - ai_desktop_net
```

## Step 3: Chat Interface

Create `index.html`:

```html
<!DOCTYPE html>
<html>
<body>
  <h2>LLM Desktop Agent Interface</h2>
  <div style="border:1px solid #ccc; width:1280px; height:720px;">
    <iframe src="http://sandbox:6080/vnc.html?autoconnect=true&password=password" width="1280" height="720" frameborder="0"></iframe>
  </div>
  <div>
    <input type="text" id="userInput" placeholder="Type your instruction..." size="50">
    <button onclick="sendPrompt()">Send</button>
  </div>
  <pre id="chatLog" style="background:#f0f0f0; padding:10px; width:600px; height:200px; overflow:auto;"></pre>
  <script>
    function appendToLog(role, text) {
      const log = document.getElementById('chatLog');
      log.textContent += role + ': ' + text + '\n';
      log.scrollTop = log.scrollHeight;
    }
    async function sendPrompt() {
      const inputEl = document.getElementById('userInput');
      const prompt = inputEl.value;
      if (!prompt.trim()) return;
      appendToLog('User', prompt);
      inputEl.value = '';
      try {
        const res = await fetch('http://agent:5000/api/chat', {
          method: 'POST',
          headers: {'Content-Type': 'application/json'},
          body: JSON.stringify({prompt})
        });
        const data = await res.json();
        appendToLog('Agent', data.reply || '(No response)');
      } catch (err) {
        appendToLog('Error', 'Failed to send prompt: ' + err);
      }
    }
  </script>
</body>
</html>
```

Serve it with Nginx:

```Dockerfile
FROM nginx:alpine
COPY index.html /usr/share/nginx/html/index.html
```

Add the service:

```yaml
  frontend:
    build:
      context: .
      dockerfile: Dockerfile.frontend
    container_name: frontend
    depends_on:
      - sandbox
      - agent
    networks:
      - ai_desktop_net
    ports:
      - "8080:80"
```

## Running the System

Start everything with:

```bash
docker-compose up -d --build
```

After a short wait, open [http://<your-host>:8080](http://<your-host>:8080) and interact with the agent through the chat box while watching the sandboxed desktop.

## License

This project is released under the [MIT License](LICENSE).

## Conclusion

This setup runs an AI-controlled desktop entirely with Docker containers. Customize the agent logic or sandbox environment to experiment with your own self-hosted AI workflows.
