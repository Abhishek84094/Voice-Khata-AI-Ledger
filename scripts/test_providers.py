import os
import time

import dotenv
import httpx

dotenv.load_dotenv()
sarvam_key = os.getenv("SARVAM_API_KEY")
groq_key = os.getenv("GROQ_API_KEY")

print("--- Testing Groq Chat Completion (LLM) ---")
for model in ["openai/gpt-oss-20b", "qwen/qwen3.8-27b"]:
    try:
        t0 = time.perf_counter()
        r = httpx.post(
            "https://api.groq.com/openai/v1/chat/completions",
            headers={"Authorization": f"Bearer {groq_key}", "Content-Type": "application/json"},
            json={
                "model": model,
                "messages": [{"role": "user", "content": 'Respond with JSON: {"status": "ok"}'}],
                "response_format": {"type": "json_object"},
                "temperature": 0,
                "max_tokens": 50,
            },
            timeout=10.0,
        )
        dt = (time.perf_counter() - t0) * 1000
        print(f"Groq ({model}) status: {r.status_code} in {dt:.1f}ms")
        if r.status_code == 200:
            print(f"Groq content: {r.json()['choices'][0]['message']['content']}")
        else:
            print(f"Groq error body: {r.text[:200]}")
    except Exception as e:
        print(f"Groq error for {model}: {e}")

print("\n--- Testing Sarvam TTS ---")
test_configs = [
    ("bulbul:v4-flash", "amit_hi_conversational"),
    ("bulbul:v3", "aditya"),
]
for tts_model, speaker in test_configs:
    try:
        t0 = time.perf_counter()
        r = httpx.post(
            "https://api.sarvam.ai/text-to-speech",
            headers={"api-subscription-key": sarvam_key, "Content-Type": "application/json"},
            json={
                "inputs": ["रमेश, ₹340 उधार. हो गया."],
                "target_language_code": "hi-IN",
                "speaker": speaker,
                "model": tts_model,
            },
            timeout=10.0,
        )
        dt = (time.perf_counter() - t0) * 1000
        print(f"Sarvam TTS ({tts_model} / {speaker}) status: {r.status_code} in {dt:.1f}ms")
        if r.status_code == 200:
            data = r.json()
            audios = data.get("audios", [])
            print(
                f"Sarvam audios returned: {len(audios)}, first chunk b64 chars: "
                f"{len(audios[0]) if audios else 0}"
            )
        else:
            print(f"Sarvam TTS error body: {r.text[:300]}")
    except Exception as e:
        print(f"Sarvam TTS error: {e}")
