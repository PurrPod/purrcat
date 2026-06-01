# /// script
# requires-python = ">=3.10"
# dependencies = [
#     "SpeechRecognition",
#     "pyttsx3",
#     "openai-whisper",
#     "pyaudio",
#     "soundfile"
# ]
# ///

import sys
import json
import threading
import pyttsx3
import speech_recognition as sr
import os

_REAL_STDOUT = sys.stdout
sys.stdout = sys.stderr

def send_json_to_main(method: str, params: dict):
    _REAL_STDOUT.write(json.dumps({"method": method, "params": params}, ensure_ascii=False) + "\n")
    _REAL_STDOUT.flush()

WHISPER_MODEL = os.environ.get("WHISPER_MODEL", "base")
LANGUAGE = os.environ.get("LANGUAGE", "zh")
TTS_RATE = int(os.environ.get("TTS_RATE", "150"))
TTS_VOLUME = float(os.environ.get("TTS_VOLUME", "1.0"))

recognizer = sr.Recognizer()
recognizer.pause_threshold = 2.5
tts_lock = threading.Lock()

def listen_loop():
    with sr.Microphone() as source:
        print("🔊 [Audio Sensor] 正在校准环境噪音...")
        recognizer.adjust_for_ambient_noise(source, duration=3)
        print("✅ [Audio Sensor] 校准完成，开始静默监听")
        while True:
            try:
                audio = recognizer.listen(source, phrase_time_limit=60)
                text = recognizer.recognize_whisper(audio, model=WHISPER_MODEL, language=LANGUAGE).strip()
                if text:
                    print(f"🎤 [Audio Sensor] 听到: {text}")
                    send_json_to_main("observe", {"content": text})
            except sr.UnknownValueError:
                pass
            except Exception as e:
                print(f"⚠️ [Audio Sensor] 监听报错: {e}")

threading.Thread(target=listen_loop, daemon=True).start()

for line in sys.stdin:
    if not line.strip(): continue
    try:
        req = json.loads(line)
        if req.get("method") == "express":
            message = str(req["params"].get("message", "")).replace("#", "").replace("*", "")

            def _speak():
                with tts_lock:
                    try:
                        print(f"🔊 [Audio Sensor] 正在播放: {message}")
                        engine = pyttsx3.init()
                        engine.setProperty("rate", TTS_RATE)
                        engine.setProperty("volume", TTS_VOLUME)
                        engine.say(message)
                        engine.runAndWait()
                        engine.stop()
                    except Exception as e:
                        print(f"❌ [Audio Sensor] 播放失败: {e}")

            threading.Thread(target=_speak, daemon=True).start()
    except json.JSONDecodeError:
        pass