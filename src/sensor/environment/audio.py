import threading
from typing import Any, Optional

import pyttsx3
import speech_recognition as sr

from src.sensor.base import BaseSensor
from src.sensor.gateway import get_gateway


class EnvironmentSensor(BaseSensor):
    config_key = "environment"

    def __init__(self, config_dict: dict):
        super().__init__(
            sensor_type="audio", sensor_name="environment", config_dict=config_dict
        )
        self.recognizer = sr.Recognizer()
        self.whisper_model = self.config_dict.get("whisper_model", "base")
        self.language = self.config_dict.get("language", "zh")

        self.max_record_seconds = self.config_dict.get("max_record_seconds", 60)
        self.recognizer.pause_threshold = self.config_dict.get("pause_threshold", 2.5)
        self.recognizer.non_speaking_duration = 0.5

        self.tts_rate = self.config_dict.get("tts_rate", 150)
        self.tts_volume = self.config_dict.get("tts_volume", 1.0)
        self._tts_lock = threading.Lock()

    def _observe(self, *args, **kwargs) -> Optional[Any]:
        threading.Thread(target=self._listen_loop, daemon=True).start()
        print(f"🟢 [Environment Sensor] 麦克风监听已启动 (停顿阈值 {self.recognizer.pause_threshold}s, 上限 {self.max_record_seconds}s)")

    def _listen_loop(self):
        with sr.Microphone() as source:
            print("🔊 [Environment Sensor] 正在校准环境噪音...")
            self.recognizer.adjust_for_ambient_noise(source, duration=3)
            print(f"✅ [Environment Sensor] 校准完成，基准底噪能量值: {self.recognizer.energy_threshold}")

            while True:
                try:
                    audio = self.recognizer.listen(
                        source,
                        phrase_time_limit=self.max_record_seconds
                    )

                    text = self.recognizer.recognize_whisper(
                        audio,
                        model=self.whisper_model,
                        language=self.language
                    )

                    text = text.strip()
                    if text:
                        print(f"🎤 [Environment Sensor] 听到内容: {text}")
                        get_gateway().push(self, text)

                except sr.UnknownValueError:
                    pass
                except sr.RequestError as e:
                    print(f"⚠️ [Environment Sensor] Whisper 识别异常: {e}")
                except Exception as e:
                    print(f"❌ [Environment Sensor] 麦克风监听发生未知错误: {e}")

    def _express(self, message: Any, **kwargs) -> bool:
        if not isinstance(message, str):
            message = str(message)

        clean_message = message.replace("#", "").replace("*", "")

        def _speak():
            with self._tts_lock:
                try:
                    engine = pyttsx3.init()
                    engine.setProperty("rate", self.tts_rate)
                    engine.setProperty("volume", self.tts_volume)

                    print(f"🔊 [Environment Sensor] 正在播放: {clean_message}")
                    engine.say(clean_message)
                    engine.runAndWait()
                    engine.stop()
                except Exception as e:
                    print(f"❌ [Environment Sensor] 语音播放失败: {e}")

        threading.Thread(target=_speak, daemon=True).start()
        return True