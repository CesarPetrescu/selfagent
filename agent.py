import os
from flask import Flask, request, jsonify

app = Flask(__name__)

# Placeholder environment variables
LLM_API_BASE_URL = os.getenv("LLM_API_BASE_URL", "http://localhost:8000/v1")
LLM_MODEL = os.getenv("LLM_MODEL", "dummy-model")

@app.route('/api/chat', methods=['POST'])
def chat():
    data = request.get_json(force=True)
    prompt = data.get('prompt', '')
    # TODO: connect to LLM and sandbox here
    reply = f"Received: {prompt} (model={LLM_MODEL})"
    return jsonify({'reply': reply})

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5000)
