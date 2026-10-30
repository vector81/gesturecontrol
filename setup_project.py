"""Download the public hand model once; runtime never downloads or uploads."""
import hashlib
import json
import urllib.request
from config import ROOT, CONFIG, load, save

MODEL_URL = 'https://storage.googleapis.com/mediapipe-models/hand_landmarker/hand_landmarker/float16/1/hand_landmarker.task'
MODEL_SHA256 = 'fbc2a30080c3c557093b5ddfc334698132eb341044ccee322ccf8bcf3607cde1'

def main():
    folder=ROOT/'models'
    folder.mkdir(exist_ok=True)
    model=folder/'hand_landmarker.task'
    if not model.exists():
        print('Downloading the public MediaPipe hand model from Google (no camera access).')
        temp=model.with_suffix('.download')
        with urllib.request.urlopen(MODEL_URL, timeout=60) as response:
            temp.write_bytes(response.read())
        if hashlib.sha256(temp.read_bytes()).hexdigest() != MODEL_SHA256:
            raise RuntimeError('Model checksum mismatch; run Setup.bat again.')
        temp.replace(model)
    digest=hashlib.sha256(model.read_bytes()).hexdigest()
    if digest != MODEL_SHA256:
        raise RuntimeError('Local model checksum mismatch. Remove only models/hand_landmarker.task and run Setup.bat again.')
    (folder/'model-info.txt').write_text(f'Source: {MODEL_URL}\nSHA256: {digest}\n')
    example = ROOT / 'config.example.json'
    save(load() if CONFIG.exists() or not example.exists() else json.loads(example.read_text()))
    print(f'Model ready: {model}\nSHA256: {digest}')

if __name__=='__main__': main()
