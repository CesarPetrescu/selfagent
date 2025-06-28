import os
import base64
import io
import logging
from typing import Optional

import requests
from flask import Flask, request, jsonify
from PIL import Image
from vncdotool import api

app = Flask(__name__)

# Environment variables used for the LLM API and sandbox
LLM_API_BASE_URL = os.getenv("LLM_API_BASE_URL", "http://localhost:8000/v1")
LLM_MODEL = os.getenv("LLM_MODEL", "gpt-4")
LLM_API_KEY = os.getenv("LLM_API_KEY")

# VNC connection information
VNC_SERVER = os.getenv("VNC_SERVER", "sandbox::5901")
VNC_PASSWORD = os.getenv("VNC_PASSWORD", "password")

logging.basicConfig(level=logging.INFO)


def capture_screenshot() -> Optional[bytes]:
    """Capture the sandbox screen via VNC and return PNG bytes."""
    try:
        with api.connect(VNC_SERVER, password=VNC_PASSWORD, timeout=10) as client:
            buf = io.BytesIO()
            client.captureScreen(buf)
            buf.seek(0)
            return buf.read()
    except Exception as exc:
        logging.warning("Failed to capture screenshot: %s", exc)
        return None


def call_llm(prompt: str, image: Optional[bytes]) -> str:
    """Send prompt and optional screenshot to the LLM API."""
    headers = {"Authorization": f"Bearer {LLM_API_KEY}"} if LLM_API_KEY else {}
    payload = {
        "model": LLM_MODEL,
        "messages": [
            {
                "role": "user",
                "content": [
                    {"type": "text", "text": prompt},
                ],
            }
        ],
    }

    if image:
        b64 = base64.b64encode(image).decode("utf-8")
        payload["messages"][0]["content"].append(
            {"type": "image_url", "image_url": f"data:image/png;base64,{b64}"}
        )

    url = f"{LLM_API_BASE_URL}/chat/completions"
    logging.info("Calling LLM at %s", url)
    r = requests.post(url, json=payload, headers=headers, timeout=60)
    r.raise_for_status()
    data = r.json()
    return data.get("choices", [{}])[0].get("message", {}).get("content", "")


def execute_actions(actions: str) -> None:
    """Very small action parser to demonstrate keyboard/mouse usage."""
    try:
        with api.connect(VNC_SERVER, password=VNC_PASSWORD, timeout=10) as client:
            for line in actions.splitlines():
                line = line.strip()
                if line.upper().startswith("TYPE "):
                    text = line[5:]
                    for ch in text:
                        if ch == "\n":
                            client.keyPress("enter")
                        else:
                            client.keyPress(ch.lower())
                elif line.upper().startswith("CLICK "):
                    try:
                        _, x, y = line.split()
                        x, y = int(x), int(y)
                        client.mouseMove(x, y)
                        client.mousePress(1)
                        client.mouseUp(1)
                    except Exception as e:
                        logging.warning("Invalid CLICK command '%s': %s", line, e)
    except Exception as exc:
        logging.warning("Failed executing actions: %s", exc)

@app.route('/api/chat', methods=['POST'])
def chat():
    data = request.get_json(force=True)
    prompt = data.get('prompt', '')
    screenshot = capture_screenshot()
    try:
        reply = call_llm(prompt, screenshot)
    except Exception as exc:
        logging.error("LLM call failed: %s", exc)
        return jsonify({"reply": f"LLM error: {exc}"})

    # Attempt to execute any actions described in the reply
    execute_actions(reply)

    return jsonify({'reply': reply})

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5000)
