# AI-quiz-generator
An AI powered quiz generator from YouTube videos link.

## Run locally

1. Install dependencies:

```
pip3 install --break-system-packages -r requirements.txt
```

2. Start the server:

```
uvicorn app.main:app --host 0.0.0.0 --port 8000
```

3. Open http://localhost:8000

Optional: Set `OPENAI_API_KEY` to enable OpenAI-based generation.