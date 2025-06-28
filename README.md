# selfagent
Autonomous Self Agent, Everything self hosted



Self-Hosting an E2B-Inspired LLM Desktop Agent with Docker
Overview and Goal
E2B’s Desktop Sandbox provides a secure cloud VM with a full Ubuntu GUI that can be controlled by AI agents
reddit.com
. In our self-hosted setup, we’ll recreate this concept locally using Docker containers instead of Firecracker microVMs or Terraform provisioning. The goal is to run a virtual desktop environment in one container, an AI agent (powered by your chosen LLM/VLM) in another, and a chat interface in a third container for user interaction. This setup will let an LLM receive your instructions via chat and manipulate a sandboxed GUI desktop (opening applications, clicking, typing, running commands, etc.) similar to the open-source Open Computer Use project
github.com
. By the end, you'll have a local “AI computer use” environment: a browser-based desktop stream with a chat box to command the AI agent. Key Points & Constraints: We will avoid any VM-based sandboxing or cloud services – everything runs on a single host using Docker. The LLM/VLM is assumed to be accessible via an OpenAI-compatible API endpoint (configured via .env with base URL, model name, and API token). Each component of the system will be containerized for isolation and clarity. (E2B’s official self-hosting uses Terraform to deploy cloud infra
github.com
, but here we’ll do it manually with Docker Compose on a single machine.)
System Architecture
High-level architecture of an AI agent controlling a desktop sandbox. The agent uses vision and language models to decide on actions (mouse, keyboard, commands) based on the screen, similar to the Open Computer Use design. Our setup comprises three Docker containers working together (inspired by the Open Computer Use design
github.com
github.com
):
1. GUI Sandbox Container: A Linux desktop environment (Ubuntu with Xfce, etc.) running inside a container. This provides a virtual display (with a window manager and common applications) that the agent can control. We will expose a VNC server (and a web VNC client) to stream the desktop’s GUI. Each sandbox is isolated from the host and other containers
github.com
, so any AI-driven actions (clicks, file operations, etc.) stay sandboxed. This is analogous to E2B’s Firecracker-based VM sandbox, but here it’s just a Docker container running a desktop environment.
2. Agent Container: This container runs the controller logic – it connects to the LLM/VLM API, interprets user instructions (and the desktop screen), and sends commands to the sandbox (keyboard strokes, mouse moves, shell commands). Essentially, it’s the “brain” of the system. For example, if you tell the agent “Open a browser and search for cats”, the agent will use the LLM to decide a sequence of actions: launch browser, focus address bar, type search query, etc., then execute those on the sandbox
github.com
. The agent will continually observe the sandbox’s state (by taking screenshots) and ask the LLM for next steps until the task is done
e2b.dev
. We will implement this logic in Python for simplicity.
3. Chat Interface Container: This provides a web-based interface for you (the human user) to interact with the agent. It serves a frontend with a chat box (to send instructions) and an embedded live stream of the sandbox’s GUI. The interface will forward your prompts to the agent’s API and display the agent’s responses. It also shows the real-time desktop feed (via noVNC or similar) so you can watch the agent’s actions. This component coordinates the user input, agent output, and the desktop view – similar to how E2B’s cloud service or the Open Computer Use demo let you pause and instruct the agent while watching the sandbox
github.com
.
Each service runs in a separate container, but they will be linked via a Docker network so they can communicate. For instance, the agent container will reach the sandbox’s VNC server over the internal network, and the chat frontend will call the agent’s API. We will use Docker Compose to define these services and their interactions for convenience.
Prerequisites and Configuration
Host requirements: A Linux host (or Linux VM) with Docker and Docker Compose installed. Ensure the host has a decent amount of RAM/CPU for running a desktop environment. No GPU is strictly required unless your chosen LLM/VLM deployment needs it (e.g. if you self-host a model). We also assume you have an OpenAI-compatible API endpoint for the LLM – this could be OpenAI’s own API or a self-hosted equivalent that accepts the same format. .env Setup: Create a file named .env in your project directory to store configuration for the LLM API and any other secrets. The agent will read these values at runtime. For example:
bash
Copy
# LLM/VLM API settings (OpenAI-compatible)
LLM_API_BASE_URL="http://192.168.10.142:80/v1"   # Base URL of your OpenAI-style API
LLM_MODEL="gpt-4-vision"                        # Model name (e.g., GPT-4 with vision support)
LLM_API_KEY="YOUR_API_BEARER_TOKEN"             # Bearer token or API key for the LLM service
Adjust these to point to your actual model endpoint and credentials. The above example assumes a locally hosted API at 192.168.10.142. The .env file will be loaded by Docker Compose so all containers can access these values. (If your LLM API requires specific environment variable names, include those as needed.) Networking: Docker Compose will by default create an isolated network for the containers to talk to each other. We’ll ensure the containers have predictable names (sandbox, agent, frontend) so they can resolve each other’s hostnames. No ports will be exposed externally except the ones needed to access the GUI and chat interface from your browser.
Step 1: Build the GUI Sandbox Container
First, we need a Docker image that runs a lightweight Linux desktop and a VNC server. You can either use a pre-built image (such as accetto/ubuntu-vnc-xfce or dorowu/ubuntu-desktop-lxde-vnc) which comes with Xfce/LXDE and noVNC configured, or create a custom Dockerfile. Here we’ll outline a custom Dockerfile to illustrate the components:
Dockerfile
Copy
# Dockerfile for sandbox GUI environment
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
In the above, we install the Xfce4 desktop environment, a VNC server (tigervnc-standalone-server), and noVNC (which provides an HTML5 VNC client served via websockify). We also copy in a start.sh script that will initialize the X11 server and launch the VNC servers. A simple start.sh could look like:
bash
Copy
#!/bin/bash
export DISPLAY=:1
# Start a virtual framebuffer X server (Xvfb) in the background
Xvfb :1 -screen 0 1280x720x24 &

# Start the Xfce4 desktop session (this will connect to DISPLAY :1)
startxfce4 &

# Wait a few seconds for Xfce to start...
sleep 2

# Launch the VNC server on DISPLAY :1 with the given password
echo "$VNC_PASSWORD" | vncpasswd -f > /root/.vnc/passwd
chmod 600 /root/.vnc/passwd
tigervncserver -geometry 1280x720 :1

# Launch noVNC to serve a web interface on port 6080
websockify --web=/usr/share/novnc/ --prefer-ipv4 6080 localhost:5901
This script uses Xvfb to create a headless X11 display :1 at 1280×720 resolution, starts the Xfce desktop on it, then runs a VNC server (TigerVNC) on that display. Finally, it runs websockify to bridge VNC to an HTML5 page on port 6080 (noVNC serves localhost:5901 which is the VNC port for display :1). The result: when this container runs, it will start an Ubuntu desktop environment in memory and you can connect to it via VNC on port 5900 or via a web browser on port 6080 for the noVNC web client. Docker Compose Service: In your docker-compose.yml, define the sandbox service using the above Dockerfile. For example:
yaml
Copy
services:
  sandbox:
    build:
      context: . 
      dockerfile: Dockerfile  # path to the sandbox Dockerfile
    container_name: sandbox
    ports:
      - "5900:5900"   # VNC port (for optional direct VNC client use)
      - "6080:6080"   # noVNC web port (to view in browser)
    environment:
      - VNC_PASSWORD=password
    networks:
      - ai_desktop_net
    volumes:
      - ./sandbox-data:/home   # (Optional) mount for persistence
We expose port 6080 to the host so you can access the noVNC web UI in your browser. Port 5900 is optional (if you want to connect using a VNC client application). We also mount a volume sandbox-data to /home as an example of persisting state – this could allow the agent’s changes (like downloaded files or installed programs) to persist across container restarts. You can adjust the volume path or remove it if persistence isn’t needed. Verify the Sandbox: Build and start the sandbox container (e.g. docker-compose up -d sandbox). After a minute, open http://<your-host>:6080 in a web browser. You should see the noVNC interface loading – click “Connect” (if it doesn’t auto-connect) and enter the VNC password (default "password" as set above). You should then see the Ubuntu desktop environment. Try interacting with it manually: open the menu, etc., just to ensure the GUI is running. This is our isolated desktop that the AI agent will soon control. (If you prefer, you can also connect with a VNC desktop client at vnc://<host>:5900.)
Step 2: Build the AI Agent Container
Next, we create the agent that will interface between the LLM and the sandbox. We’ll use Python for the agent logic, leveraging the OpenAI-compatible API for reasoning and possibly vision. The agent needs the ability to:
Receive user instructions (from the chat interface or CLI).
Capture the sandbox’s screen (to give the LLM visual context, if using a vision model).
Query the LLM/VLM with the instruction and screen context.
Parse the LLM’s response to determine an action (e.g., “Click at coordinates (x,y)”, “Type 'hello' into the text field”, or “No action needed, task complete”).
Execute the action on the sandbox (via mouse/keyboard events or shell commands).
Loop back to capture the new screen and continue the cycle until the task is done or a set number of steps is reached.
We can utilize existing tools to simplify implementation. For example, the vncdotool library or command-line can connect to a VNC server and send mouse/keyboard events and even capture screenshots of the remote screen. Another approach is installing xdotool in the sandbox container and invoking it via SSH or Docker exec from the agent. For clarity, we’ll choose the VNC control route here. Dockerfile for Agent: Create a Dockerfile (e.g., Dockerfile.agent) with the necessary runtime and libraries:
Dockerfile
Copy
FROM python:3.10-slim

WORKDIR /app
COPY requirements.txt . 
RUN pip install -r requirements.txt

COPY agent.py .  # Our agent controller script
ENV PYTHONUNBUFFERED=1

# The agent will be run as a service (possibly with an API server)
CMD ["python", "agent.py"]
Agent Requirements: In requirements.txt, include libraries like requests (to call the LLM API), Pillow or opencv-python (to handle image data if needed), and vncdotool (for VNC automation). For example:
text
Copy
requests
vncdotool
Pillow
Agent Logic (Outline): The agent.py will utilize the environment variables and perform the loop described. A simplified pseudo-code outline is:
python
Copy
import os, base64, requests
from vncdotool import api as vnc_api

LLM_API = os.getenv("LLM_API_BASE_URL")
LLM_MODEL = os.getenv("LLM_MODEL")
LLM_TOKEN = os.getenv("LLM_API_KEY")

# Connect to the sandbox VNC server
vnc = vnc_api.connect(host="sandbox", port=5900, password=os.getenv("VNC_PASSWORD", "password"))

def capture_screen():
    # Capture the screen to an image file or bytes
    filename = "screen.png"
    vnc.captureScreen(filename)  # vncdotool saves a screenshot
    with open(filename, "rb") as f:
        img_data = f.read()
    return img_data

def send_to_llm(user_prompt, image_bytes):
    # Prepare payload for OpenAI-compatible API (e.g., /v1/chat/completions)
    # Using an image in prompt: could encode as base64 or use OpenAI image parameters if supported
    prompt = user_prompt
    if image_bytes:
        b64 = base64.b64encode(image_bytes).decode('ascii')
        prompt = f"Image:{b64}\nInstruction:{user_prompt}"
    payload = {
        "model": LLM_MODEL,
        "messages": [{"role": "user", "content": prompt}]
    }
    headers = {"Authorization": f"Bearer {LLM_TOKEN}"}
    resp = requests.post(f"{LLM_API}/chat/completions", json=payload, headers=headers)
    resp.raise_for_status()
    reply = resp.json()
    # Extract the assistant's response text
    return reply["choices"][0]["message"]["content"]

def interpret_and_act(llm_reply):
    # Very basic parsing example (the reply might be something like "Click 100 200" or "Type Hello")
    # In practice, you'd implement a robust parser or use a structured format.
    command = llm_reply.strip().lower()
    if command.startswith("click"):
        _, x, y = command.split()
        vnc.mouseMove(int(x), int(y))
        vnc.mousePress()  # click
    elif command.startswith("type"):
        text = command.partition(" ")[2]
        vnc.keyPress(text)  # types the given text
    # ... handle other actions ...
    elif command.startswith("done"):
        return False  # stop the loop
    return True

# Main loop
print("Agent is running. Waiting for instructions...")
while True:
    user_input = get_next_user_message()  # This could be from a queue, API call, or just input() for testing
    # (For a real chat server, this loop could be event-driven instead)
    image = capture_screen()
    llm_reply = send_to_llm(user_input, image)
    print(f"LLM reply: {llm_reply}")
    cont = interpret_and_act(llm_reply)
    while cont:
        # continue looping with updated screenshot until LLM says "done"
        image = capture_screen()
        llm_reply = send_to_llm("", image)  # you might send an empty user prompt or a special token indicating "next step"
        print(f"LLM reply: {llm_reply}")
        cont = interpret_and_act(llm_reply)
In a real implementation, the agent would likely run as a web service. For instance, it could expose a small Flask API (/api/chat) that accepts user prompts, then triggers the above process and streams back the LLM’s actions. This would integrate with our front-end. The above pseudocode is a simplification: it assumes the LLM responds with direct low-level actions. In practice, you might have the LLM output a JSON with structured commands or use separate “vision” and “action” models as in the Open Computer Use project
github.com
github.com
. For example, Open Computer Use uses OS-Atlas to interpret the screen and find UI element coordinates, and another model for deciding actions
github.com
. However, if your chosen model is multimodal (e.g. GPT-4 with vision or CLIP + GPT combo), you can send the screenshot and prompt together to a single API. Docker Compose Service: Define the agent service in docker-compose.yml:
yaml
Copy
  agent:
    build:
      context: .
      dockerfile: Dockerfile.agent
    container_name: agent
    depends_on:
      - sandbox    # ensure sandbox is up first
    environment:
      - LLM_API_BASE_URL=${LLM_API_BASE_URL}
      - LLM_MODEL=${LLM_MODEL}
      - LLM_API_KEY=${LLM_API_KEY}
      - VNC_PASSWORD=${VNC_PASSWORD:-password}
    networks:
      - ai_desktop_net
We pass the LLM configuration and VNC password from the .env file into the agent. The agent’s code will use these to connect and authenticate. We set depends_on: sandbox so that Docker starts the sandbox before the agent (so the VNC server is ready). Both services join the ai_desktop_net network, allowing the agent to reach sandbox:5900. After building, you can test the agent container in isolation by opening a shell (docker-compose run agent bash). For example, you might run a quick vncdotool command to ensure it can grab a screenshot from the sandbox (vncdotool -s sandbox:5900 -p password capture test.png). If that works, the connectivity is good. The agent’s logs (via docker-compose up agent or docker logs agent) will show its printouts. For now, keep the agent running and waiting for instructions – next we’ll set up the interface to send those instructions.
Step 3: Set up the Chat Interface Container
Finally, we need a user-facing interface to chat with the agent and view the desktop. We’ll create a simple web frontend that accomplishes two things:
Provides a chat input/output area to send messages to the agent and display the agent’s replies or status.
Shows the live desktop stream from the sandbox container.
We can achieve the latter by embedding the noVNC client or by proxying the sandbox’s VNC stream. A straightforward way is to use the noVNC web client that’s already served by the sandbox on port 6080 – we can embed it in an <iframe> or even fetch the noVNC scripts to create a custom viewer. For the chat itself, we can have the front-end make AJAX calls or WebSocket connections to the agent. Frontend implementation: We’ll use a simple static HTML/JavaScript approach for brevity. The interface might not be fancy, but will be functional. We’ll serve an index.html that:
Opens a WebSocket connection to the sandbox’s noVNC endpoint (or simply iframes the existing noVNC page) to display the desktop.
Has a text input and send button that calls the agent’s API (we might expose the agent’s Flask server on a port, e.g. 5000, within the Docker network). We could also use a simple polling or Server-Sent Events to get real-time responses from the agent if needed.
Example index.html:
html
Copy
<!DOCTYPE html>
<html>
<head><title>AI Desktop Agent</title></head>
<body>
  <h2>LLM Desktop Agent Interface</h2>
  <!-- Video feed via noVNC iframe -->
  <div style="border:1px solid #ccc; width: 1280px; height: 720px;">
    <iframe src="http://sandbox:6080/vnc.html?autoconnect=true&password=password" 
            width="1280" height="720" frameborder="0"></iframe>
  </div>
  <!-- Chat controls -->
  <div>
    <input type="text" id="userInput" placeholder="Type your instruction..." size="50">
    <button onclick="sendPrompt()">Send</button>
  </div>
  <pre id="chatLog" style="background:#f0f0f0; padding:10px; width:600px; height:200px; overflow:auto;"></pre>

  <script>
    function appendToLog(role, text) {
      const log = document.getElementById('chatLog');
      log.textContent += role + ": " + text + "\\n";
      log.scrollTop = log.scrollHeight;
    }
    async function sendPrompt() {
      const inputEl = document.getElementById('userInput');
      const prompt = inputEl.value;
      if(prompt.trim() === "") return;
      appendToLog("User", prompt);
      inputEl.value = "";
      // Send prompt to agent API
      try {
        const res = await fetch('http://agent:5000/api/chat', {
          method: 'POST',
          headers: {'Content-Type': 'application/json'},
          body: JSON.stringify({ prompt: prompt })
        });
        const data = await res.json();
        if(data.reply) {
          appendToLog("Agent", data.reply);
        } else {
          appendToLog("Agent", "(No response)");
        }
      } catch(err) {
        appendToLog("Error", "Failed to send prompt: " + err);
      }
    }
  </script>
</body>
</html>
In this example, we embed the sandbox’s noVNC web client by pointing an iframe to sandbox:6080/vnc.html. This uses the container name sandbox, which works because the frontend container will be on the same Docker network. We also pass autoconnect=true&password=password in the URL so it connects automatically to the VNC (adjust the password if you changed it). For chat, when the user clicks Send, we POST the prompt to http://agent:5000/api/chat. This assumes we modify our agent.py to run a simple web server (for instance, using Flask or FastAPI) on port 5000 that accepts POST /api/chat and returns the LLM’s reply (after performing the steps of capturing screen, querying the model, etc.). Setting up that Flask server in the agent is straightforward and left as an exercise (essentially, wrap the earlier loop logic into an endpoint so it runs one cycle per prompt, or maintain a conversation state). The agent would then respond with JSON like {"reply": "I opened the browser as you asked."} or stream partial actions. Serving the Frontend: We can serve this static HTML using a lightweight web server container. For example, we can use an Nginx or httpd container, or even Python’s built-in server. Let’s use Nginx for reliability. Create a Dockerfile Dockerfile.frontend:
Dockerfile
Copy
FROM nginx:alpine
COPY index.html /usr/share/nginx/html/index.html
This will build an Nginx image that simply serves our index.html on port 80. Add the service to docker-compose.yml:
yaml
Copy
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
      - "8080:80"   # expose frontend UI on port 8080
We map container’s port 80 to host 8080 (so you can open the interface in your browser via http://<host>:8080). The frontend container can reach sandbox:6080 and agent:5000 internally by name, thanks to the shared network. (Note: We expose agent’s API only to the front-end via the internal network. We did not publish agent’s port to the host for security, so external access to the agent must go through the frontend.)
Running the System
With all services defined (sandbox, agent, frontend) in your docker-compose.yml, you can now start the whole system. Ensure the Docker Compose file, Dockerfiles, and scripts are all in place, then run:
bash
Copy
docker-compose up -d --build
This builds the images and starts all containers in the background. Give it a bit of time on first launch (the sandbox needs ~15–30 seconds to fully start Xfce, and the agent might also take a few seconds to be ready). Access the Interface: Open your browser to http://<your-host>:8080 (replace <your-host> with the IP or hostname of your machine, or use localhost if local). You should see the web interface with the embedded desktop and the chat controls. The sandbox’s desktop will be streaming in the top frame (it may initially show the Ubuntu desktop background). You can type a message in the input box. For example, try: “Open a terminal and create a file on the desktop.” Then click Send.
Agent Processing: The agent container will receive the prompt via the /api/chat call. It will capture the current screen, send the prompt + screenshot to the LLM API, get a response, and attempt to execute an action. For instance, the LLM might reply with an action like “Launch Terminal” which the agent interprets by simulating the appropriate keystrokes (e.g., pressing the menu key and typing ‘Terminal’). You will see the cursor move and the Terminal window open on the virtual desktop if all goes well. The agent might then reply with a message like “Terminal opened.” which would appear in the chat log on the interface. It would then continue (depending on how the agent code is written – some might wait for further user input, others might proactively complete a multi-step task).
Verify Actions: You should observe the desktop updating in real time. For example, if the instruction was to create a file, you might see the agent open a text editor or use a shell command in the terminal. The new file would appear on the desktop. You can also manually intervene via the VNC control if needed (e.g., moving the mouse yourself – though the agent might not expect that). The Open Computer Use demo similarly streams the display and allows user interruption
github.com
.
Agent Logs: If something isn’t working, check docker-compose logs agent to see if the agent encountered errors (like inability to connect to the LLM API or parse a response). The front-end’s dev console (in your browser) might also show CORS issues or fetch errors if the agent API didn’t respond. Make sure the container names and ports match what the front-end expects.
Internal Networking and Service Links
Docker Compose automatically sets up a network named (by default) after your project, here we used ai_desktop_net. All services attached to it can resolve each other by the service name. We referenced sandbox and agent hostnames in our configs/HTML – those are made possible by Compose’s internal DNS. The front-end iframe URL http://sandbox:6080/vnc.html fetches the VNC page from the sandbox container directly through this network (it won’t work from your host browser if you try to open that URL, because sandbox isn’t known to your host’s DNS – but within the frontend container and the browser running that iframe, it works because the iframe content is actually served by the front-end container’s Nginx as an intermediary). In our setup, Nginx is serving index.html to your browser, and that HTML instructs the browser to connect to sandbox:6080. Because sandbox:6080 is not on the same origin as the served page, you might run into a cross-origin issue. If that happens, a quick workaround is to proxy the VNC web socket through the front-end container (this can be done by configuring Nginx to route a path like /vnc to the sandbox). However, many noVNC setups allow specifying the target host, and since we loaded the page from Nginx on localhost:8080, the browser might attempt to resolve sandbox via DNS (which would fail). To avoid this, you can replace sandbox with the actual IP of the sandbox container. For example, find it via docker inspect sandbox and use that IP in the iframe src (or better, configure Nginx with an upstream). For simplicity, ensure both front-end and sandbox share the same origin: one approach is to serve the noVNC client files directly from the front-end. (In practice, using the sandbox’s noVNC as we did is easiest for a demo; for a production setup, integrate noVNC properly into the front-end to avoid any cross-origin restrictions.)
Persistent Agent State (Optional)
The Docker setup above is stateless by default – if the sandbox container is removed or restarted, any changes (installed programs, created files) vanish, since the container filesystem resets. If you want the AI’s environment to persist (so it “remembers” the files it created or retains installed software between sessions), use Docker volumes. We already showed an example of mounting ./sandbox-data to /home in the sandbox. You can extend that to other paths as needed (for instance, mount a volume at /opt or /usr if you plan on installing system packages persistently, though a better approach is baking common tools into the image). With the volume in place, the sandbox will save any new files in those directories on the host. This way, the agent’s state (e.g., a downloaded dataset or a configuration file it wrote) isn’t lost. Keep in mind security: the sandbox container should not mount any sensitive host directories; use a dedicated folder.
Conclusion and Next Steps
You now have a self-hosted AI agent with a virtual GUI it can control. You can experiment by issuing different commands via chat. The agent uses the LLM/VLM endpoint you configured to decide on actions, and it manipulates the desktop accordingly with mouse, keyboard, and shell commands
github.com
. This setup is highly extensible: you could swap in a more sophisticated agent logic or integrate specialized models (e.g., an OCR or “vision grounding” model to improve how it understands the screen, as done in Open Computer Use
github.com
). You could also run a full browser in the sandbox and let the agent surf the web on your behalf. Because everything is containerized, you can tweak each component in isolation. For instance, to upgrade the desktop environment, you might use a different base image or window manager. To improve the agent, you can modify its Python code without affecting the others. And if you have a different front-end in mind (say, a React app), you can replace the simple Nginx setup accordingly. By using Docker containers, we achieved strong isolation similar to E2B’s cloud sandboxes (without needing Firecracker VMs)
reddit.com
. Each sandbox is disposable and secure, and you can run multiple sandbox+agent pairs if you want parallel agents (just give each a separate VNC port and container name). This tutorial gives you a foundation for building your own “AI computer-use” platform locally. Happy hacking! Sources: The design is inspired by E2B’s open-source sandbox and the Open Computer Use agent, which demonstrate secure desktop sandboxes controlled by LLMs
reddit.com
github.com
. The multi-container approach aligns with similar projects that separate the virtual environment, AI logic, and interface into isolated services
github.com
github.com
. By using Docker in place of cloud VMs, we trade off some low-level isolation for convenience, but still maintain a safe playground for AI agents. For more details on how the agent reasons about UI elements and coordinates, see How I taught an AI to use a computer
e2b.dev
 and the Open Computer Use repository
github.com
github.com
. This self-hosted setup demonstrates the core idea: an AI agent can operate a GUI-based computer autonomously, and now you have full control to extend or customize it on your own machine. Enjoy your E2B-inspired AI desktop agent!


## License
This project is licensed under the [MIT License](LICENSE).

## Contributing
See [CONTRIBUTING.md](CONTRIBUTING.md) for guidelines on how to contribute to this project.
