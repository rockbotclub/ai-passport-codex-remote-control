"""Owned, loopback-only Whisper worker and per-recording sentence boundaries."""
from contextlib import closing
import http.client
import io
import json
from pathlib import Path
import socket
import subprocess
import tempfile
import time
import uuid
import wave


def finish_sentence(text):
    text = text.strip()
    if not text:
        return text
    # A closing quote/bracket may follow an existing sentence terminator.
    core = text.rstrip('"\'”’」』)]）】').rstrip()
    if not core or core[-1] in '.。?!？！…':
        return text
    ending = '。' if any('\u3400' <= c <= '\u9fff' for c in text) else '.'
    return text.rstrip(',，;；:：') + ending


class WhisperWorker:
    """Load once; never retain cross-recording context or expose audio on the LAN."""
    def __init__(self, model, executable):
        self.model, self.executable = Path(model).resolve(), executable
        self.process = self.directory = None
        self.port = None

    def start(self):
        if self.process is not None and self.process.poll() is None:
            return
        self.close()
        self.directory = tempfile.TemporaryDirectory(prefix='passport-whisper-')
        with closing(socket.socket()) as reservation:
            reservation.bind(('127.0.0.1', 0))
            self.port = reservation.getsockname()[1]
        try:
            self.process = subprocess.Popen(
                [self.executable, '-m', str(self.model), '-l', 'auto', '-nt', '-mc', '0',
                 '--host', '127.0.0.1', '--port', str(self.port),
                 '--public', self.directory.name], cwd=self.directory.name,
                stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
            deadline = time.monotonic() + 25
            while time.monotonic() < deadline:
                if self.process.poll() is not None:
                    raise OSError('Local Whisper worker exited during startup')
                try:
                    with closing(http.client.HTTPConnection('127.0.0.1', self.port, timeout=0.5)) as connection:
                        connection.request('GET', '/health')
                        response = connection.getresponse()
                        if response.status == 200 and json.loads(response.read(4096)).get('status') == 'ok':
                            return
                except (OSError, http.client.HTTPException, ValueError):
                    pass
                time.sleep(0.1)
            raise OSError('Local Whisper worker startup timed out')
        except BaseException:
            self.close()
            raise

    def __call__(self, pcm):
        if len(pcm) % 2 or not 16000 <= len(pcm) <= 960000:
            raise ValueError('Invalid recording size')
        started = time.monotonic()
        self.start()
        audio = io.BytesIO()
        with wave.open(audio, 'wb') as wav:
            wav.setparams((1, 2, 16000, 0, 'NONE', 'not compressed'))
            wav.writeframes(pcm)
        boundary = 'passport-' + uuid.uuid4().hex
        body = bytearray()
        for name, value in (('language', 'auto'), ('response_format', 'json')):
            body.extend((f'--{boundary}\r\nContent-Disposition: form-data; name="{name}"\r\n\r\n'
                         f'{value}\r\n').encode('ascii'))
        body.extend((f'--{boundary}\r\nContent-Disposition: form-data; name="file"; '
                     'filename="voice.wav"\r\nContent-Type: audio/wav\r\n\r\n').encode('ascii'))
        body.extend(audio.getvalue())
        body.extend(f'\r\n--{boundary}--\r\n'.encode('ascii'))
        try:
            # HTTPConnection ignores proxy environment variables: audio stays on loopback.
            # Restart time shares the original transcription budget, before desktop prefill.
            remaining = max(0.1, 65 - (time.monotonic() - started))
            with closing(http.client.HTTPConnection('127.0.0.1', self.port, timeout=remaining)) as connection:
                connection.request('POST', '/inference', body,
                                   {'Content-Type': 'multipart/form-data; boundary=' + boundary})
                response = connection.getresponse()
                data = response.read(65537)
                if response.status != 200 or len(data) > 65536:
                    raise ValueError('Local transcription failed')
                result = json.loads(data)
                text = result.get('text') if isinstance(result, dict) else None
                if not isinstance(text, str) or len(text) > 12000:
                    raise ValueError('Invalid local transcript')
                return text
        except (OSError, http.client.HTTPException, ValueError):
            self.close()
            raise ValueError('Local transcription failed') from None

    def close(self):
        if self.process is not None:
            if self.process.poll() is None:
                self.process.terminate()
                try:
                    self.process.wait(timeout=3)
                except subprocess.TimeoutExpired:
                    self.process.kill()
                    self.process.wait(timeout=3)
            self.process = None
        if self.directory is not None:
            self.directory.cleanup()
            self.directory = None
        self.port = None
