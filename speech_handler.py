from vosk import Model, KaldiRecognizer
import json
import os
import wave
import base64
import struct

class SpeechHandler:
    def __init__(self, model_path="model"):
        if not os.path.exists(model_path):
            raise ValueError(f"Please download the Vosk model and place it in {model_path}")
        
        self.model = Model(model_path)
        self.recognizer = KaldiRecognizer(self.model, 8000)  # 8kHz for telephone audio
        
    def process_audio(self, audio_base64):
        """Process base64 encoded audio data from Twilio (u-law format)"""
        # Decode base64 audio
        audio_data = base64.b64decode(audio_base64)
        
        # Convert u-law to PCM
        audio_pcm = self.ulaw2linear(audio_data)
        
        # Process with Vosk
        if self.recognizer.AcceptWaveform(audio_pcm):
            result = json.loads(self.recognizer.Result())
            return result.get("text", "").strip()
        
        return None
    
    def reset(self):
        """Reset the recognizer state"""
        self.recognizer.Reset()
    
    @staticmethod
    def ulaw2linear(u_law_data):
        """Convert u-law audio to linear PCM"""
        u_law_data = bytearray(u_law_data)
        # u-law to linear conversion table
        u2l = [
            -32124, -31100, -30076, -29052, -28028, -27004, -25980, -24956,
            -23932, -22908, -21884, -20860, -19836, -18812, -17788, -16764,
            -15996, -15484, -14972, -14460, -13948, -13436, -12924, -12412,
            -11900, -11388, -10876, -10364, -9852, -9340, -8828, -8316,
            -7932, -7676, -7420, -7164, -6908, -6652, -6396, -6140,
            -5884, -5628, -5372, -5116, -4860, -4604, -4348, -4092,
            -3900, -3772, -3644, -3516, -3388, -3260, -3132, -3004,
            -2876, -2748, -2620, -2492, -2364, -2236, -2108, -1980,
            -1884, -1820, -1756, -1692, -1628, -1564, -1500, -1436,
            -1372, -1308, -1244, -1180, -1116, -1052, -988, -924,
            -876, -844, -812, -780, -748, -716, -684, -652,
            -620, -588, -556, -524, -492, -460, -428, -396,
            -372, -356, -340, -324, -308, -292, -276, -260,
            -244, -228, -212, -196, -180, -164, -148, -132,
            -120, -112, -104, -96, -88, -80, -72, -64,
            -56, -48, -40, -32, -24, -16, -8, 0,
            32124, 31100, 30076, 29052, 28028, 27004, 25980, 24956,
            23932, 22908, 21884, 20860, 19836, 18812, 17788, 16764,
            15996, 15484, 14972, 14460, 13948, 13436, 12924, 12412,
            11900, 11388, 10876, 10364, 9852, 9340, 8828, 8316,
            7932, 7676, 7420, 7164, 6908, 6652, 6396, 6140,
            5884, 5628, 5372, 5116, 4860, 4604, 4348, 4092,
            3900, 3772, 3644, 3516, 3388, 3260, 3132, 3004,
            2876, 2748, 2620, 2492, 2364, 2236, 2108, 1980,
            1884, 1820, 1756, 1692, 1628, 1564, 1500, 1436,
            1372, 1308, 1244, 1180, 1116, 1052, 988, 924,
            876, 844, 812, 780, 748, 716, 684, 652,
            620, 588, 556, 524, 492, 460, 428, 396,
            372, 356, 340, 324, 308, 292, 276, 260,
            244, 228, 212, 196, 180, 164, 148, 132,
            120, 112, 104, 96, 88, 80, 72, 64,
            56, 48, 40, 32, 24, 16, 8, 0
        ]
        
        # Convert each byte
        pcm_data = bytearray()
        for byte in u_law_data:
            pcm_data.extend(struct.pack('<h', u2l[byte]))
        
        return bytes(pcm_data)
