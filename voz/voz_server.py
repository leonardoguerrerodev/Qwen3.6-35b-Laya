#!/usr/bin/env python3
"""Servidor HTTP local de voz (TTS) para Qwen. Independiente de TTSiro: sin
imports, rutas, sockets, venv ni modelo compartidos con ese repo.

Motores, elegidos por el campo `motor` del perfil (CPU o GPU según `dispositivo`):
  piper  — en este proceso; carga cada .onnx perezosamente.
  kokoro — Kokoro-82M en un worker persistente (kokoro_worker.py, venv VOZ_KOKORO_PY).
  f5     — F5-Spanish, clona la voz de voz/refs/; worker persistente (f5_worker.py, VOZ_F5_PY).
  s2     — Fish Audio S2 Pro, un proceso por petición (VOZ_FISH_DIR); interpreta las
           etiquetas [sigh] [laughing]...; lento (~100× el audio) y pide ~20 GB de RAM.
Para piper, kokoro y f5 las etiquetas se quitan antes de sintetizar.
Sintetiza por HTTP en 127.0.0.1 — nunca en 0.0.0.0: web_server.py (el único que escucha
en la LAN) hace de proxy para todo esto, igual que ya hacía con /hablar.
Se ejecuta con el python del venv propio: voz/.venv/bin/python voz/voz_server.py

Endpoints:
  GET  /health         -> 200 "ok" (el proceso está arriba; no implica ninguna voz cargada)
  POST /api/saltar     -> 200 {ok:true}: corta la síntesis en curso y lo que esté sonando
                          (aplay/paplay de voz-hook.ts); /hablar responde vacío, /api/probar 409
  GET  /api/progreso   -> text/plain "<activo 0|1> <pct|-> <seg> <motor> <perfil>" (barra de qwen-web-desktop)
  GET  /api/estado      -> {voces, rangos, activo, perfiles}
  GET  /api/catalogo    -> voces es_* del catálogo de HF que faltan instalar
  POST /api/probar      {perfil, texto}   -> 200 audio/wav (prueba suelta, no toca perfiles.json)
  POST /api/descargar   {voz}             -> 200 {ok:true} (descarga a QWEN_MODELS_DIR)
  POST /api/guardar     {activo, perfiles}-> 200 {ok:true} (persiste perfiles.json)
  POST /hablar          {texto}           -> 200, headers X-Sample-Rate, X-Canales: 1,
                                             body PCM s16le mono crudo, con el perfil ACTIVO
                                          -> 500 {"error": "..."}

Contrato congelado para una fase futura (no implementada aún): una extension de Pi
que quiera leer en voz alta solo necesita hacer
  POST http://127.0.0.1:$VOZ_PORT/hablar {"texto": "<respuesta final de Pi>"}
Nada de esto cambia para soportar eso: /hablar sigue devolviendo PCM crudo tal cual.
"""
import array
import atexit
import ctypes
import http.client
import json
import os
import re
import shutil
import signal
import socket
import subprocess
import sys
import tempfile
import threading
import time
import urllib.error
import urllib.request
import wave
from pathlib import Path

# GPU solo si el perfil la pide (dispositivo=gpu): piper la usa en este proceso vía
# onnxruntime-gpu, kokoro/f5/s2.cpp en su hijo. S2 (Python) va siempre en CPU, ver _s2_tts.

from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

import voz_config
from piper import PiperVoice, SynthesisConfig

PORT = int(os.environ.get("VOZ_PORT", "8778"))
RUBBERBAND = shutil.which("rubberband")
HERE = Path(__file__).resolve().parent
KOKORO_PY = os.environ.get("VOZ_KOKORO_PY", "")
F5_PY = os.environ.get("VOZ_F5_PY", "")
FISH_DIR = Path(os.environ.get("VOZ_FISH_DIR", "") or "/nonexistent")
S2_RAM_MB = int(os.environ.get("VOZ_S2_RAM_MB", "20000"))   # medido: ~19,6 GB en CPU

_voces_cargadas = {}  # ruta (str) -> PiperVoice, cache perezoso
# Síntesis en curso, para la barra de la terminal (GET /api/progreso). frac None = sin % (s2).
# ponytail: un solo estado global; si dos síntesis se pisan, la barra muestra la última.
_prog = {"activo": False, "frac": 0.0, "t0": 0.0, "motor": ""}


class Saltado(Exception):
    """La síntesis se cortó con POST /api/saltar."""


_saltar = threading.Event()   # lo levanta /api/saltar; cada síntesis lo baja al empezar
_s2cpp_sock = None            # socket de la síntesis s2gguf en curso (cerrarlo la cancela)
_s2_proc = None               # proceso de fish de la síntesis s2 en curso


def _chequear_salto():
    if _saltar.is_set():
        raise Saltado()


def saltar():
    """Corta la síntesis en curso (cualquier motor) y la reproducción local de voz-hook.ts."""
    _saltar.set()
    s = _s2cpp_sock
    if s is not None:   # s2.cpp ve la conexión caída y aborta en el cuadro siguiente
        try:
            s.shutdown(socket.SHUT_RDWR)
        except OSError:
            pass
    p = _s2_proc
    if p is not None and p.poll() is None:
        p.kill()
    # ponytail: por línea de comandos — son los argumentos exactos con que voz-hook.ts lanza
    # aplay/paplay; si algún día reproduce otra cosa, pasarle el PID por /hablar.
    subprocess.run(["pkill", "-f", "^(aplay -q -r [0-9]+ -f S16_LE -c 1|paplay --raw --rate=[0-9]+ --format=s16le)"],
                   stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)

# Etiquetas de audio de la skill voz-etiquetas ([sigh], [short pause]...): solo S2 Pro las
# interpreta; piper y kokoro las leerían como palabras. No toca enlaces markdown [x](url).
_ETIQUETA = re.compile(r"\[[a-z][a-z ]*\](?!\()")


def sin_etiquetas(texto):
    return re.sub(r"[ \t]{2,}", " ", _ETIQUETA.sub("", texto)).strip()


def _morir_con_el_padre():
    """preexec_fn: el hijo recibe SIGTERM si muere el hilo que lo lanzó — o sea, si
    voz_server.py muere (kill, qwen-stop...) mientras espera al hijo. Sin esto un S2 a
    medias seguiría ~10 min ocupando ~20 GB de RAM. Solo para hijos que el hilo espera."""
    ctypes.CDLL("libc.so.6", use_errno=True).prctl(1, signal.SIGTERM)   # PR_SET_PDEATHSIG


def _piper_cuda():
    import onnxruntime as ort
    if hasattr(ort, "preload_dlls"):   # CUDA/cuDNN de los wheels nvidia-* (onnxruntime-gpu[cuda,cudnn])
        ort.preload_dlls()
    if "CUDAExecutionProvider" not in ort.get_available_providers():
        raise RuntimeError("piper en GPU necesita onnxruntime-gpu (corre qwen-voz-motores)")


def _voice_for(nombre, gpu=False):
    ruta = str(voz_config.ruta_voz(nombre))
    voz = _voces_cargadas.get((ruta, gpu))
    if voz is None:
        if gpu:
            _piper_cuda()
        voz = PiperVoice.load(ruta, use_cuda=gpu)
        _voces_cargadas[(ruta, gpu)] = voz
    return voz


def _pcm_a_wav(pcm, tasa):
    with tempfile.NamedTemporaryFile(suffix=".wav", delete=False) as tmp:
        ruta = tmp.name
    try:
        with wave.open(ruta, "wb") as w:
            w.setnchannels(1)
            w.setsampwidth(2)
            w.setframerate(tasa)
            w.writeframes(pcm)
        return open(ruta, "rb").read()
    finally:
        os.unlink(ruta)


def _wav_a_pcm(datos):
    with tempfile.NamedTemporaryFile(suffix=".wav", delete=False) as tmp:
        tmp.write(datos)
        ruta = tmp.name
    try:
        with wave.open(ruta, "rb") as w:
            return w.readframes(w.getnframes()), w.getframerate()
    finally:
        os.unlink(ruta)


def _aplicar_tono(pcm, tasa, semitonos, tempo=1.0):
    """Post-proceso con rubberband: tono en semitonos y, para s2gguf (que no tiene
    velocidad propia), tempo = factor de velocidad sin cambiar el tono."""
    if not semitonos and tempo == 1:
        return pcm, tasa
    if not RUBBERBAND:
        raise RuntimeError("tono/velocidad distintos de lo normal pero no encuentro 'rubberband' en PATH")
    entrada, salida = tempfile.mktemp(suffix=".wav"), tempfile.mktemp(suffix=".wav")
    try:
        with wave.open(entrada, "wb") as w:
            w.setnchannels(1); w.setsampwidth(2); w.setframerate(int(tasa)); w.writeframes(pcm)
        subprocess.run([RUBBERBAND, "--quiet", "--pitch", str(semitonos), "--tempo", str(tempo),
                        entrada, salida],
                        check=True, capture_output=True, timeout=120)
        with wave.open(salida, "rb") as w:
            return w.readframes(w.getnframes()), w.getframerate()
    finally:
        for f in (entrada, salida):
            if os.path.exists(f):
                os.unlink(f)


def _volumen(pcm, factor):
    if factor == 1:
        return pcm
    a = array.array("h", pcm)
    for i, v in enumerate(a):
        a[i] = max(-32768, min(32767, int(v * factor)))
    return a.tobytes()


def _lineas(texto):
    return [l.strip() for l in texto.splitlines() if l.strip()]


def _piper(perfil, texto):
    voz = _voice_for(perfil["voz"], perfil.get("dispositivo") == "gpu")
    cfg = SynthesisConfig(
        length_scale=100 / perfil["velocidad"],
        noise_scale=perfil["expresividad"],
        noise_w_scale=perfil["ritmo"],
        volume=perfil["volumen"] / 100,
    )
    tasa = voz.config.sample_rate
    silencio = bytes(int(tasa * perfil["pausa"]) * 2)
    partes = []
    lineas = _lineas(texto)
    for i, linea in enumerate(lineas):
        _chequear_salto()
        if i:
            partes.append(silencio)
        for trozo in voz.synthesize(linea, cfg):
            partes.append(trozo.audio_int16_bytes)
        _prog["frac"] = (i + 1) / len(lineas)
    return b"".join(partes), tasa


class _Worker:
    """Worker persistente por stdin/stdout (kokoro_worker.py, f5_worker.py), arrancado la
    primera vez que se usa: una petición JSON por línea → "OK <tasa> <n>\n" + PCM s16le
    | "ERR <msg>\n". Se reinicia si el perfil cambia de dispositivo (cpu/gpu)."""

    def __init__(self, nombre, py, script):
        self.nombre, self.py, self.script = nombre, py, script
        self.proc = self.disp = None
        self.lock = threading.Lock()

    def listo(self):
        return self.proc is not None and self.proc.poll() is None

    def pide(self, peticion, disp="cpu"):
        if self.proc is not None and self.disp != disp:
            self.parar()
        if not self.listo():
            if not (self.py and os.access(self.py, os.X_OK)):
                raise RuntimeError(f"{self.nombre} no está instalado (corre qwen-voz-motores)")
            # Sin _morir_con_el_padre: PDEATHSIG se dispara al morir el *hilo* que lo creó (cada
            # petición es un hilo) y mataría al worker tras la primera frase. Si voz_server.py
            # muere, el worker igual termina: se le cierra el stdin y su bucle acaba.
            self.proc = subprocess.Popen([self.py, str(HERE / self.script)], stdin=subprocess.PIPE,
                                         stdout=subprocess.PIPE, stderr=subprocess.DEVNULL,
                                         env={**os.environ, "VOZ_WORKER_DEVICE": disp})
            self.disp = disp
        self.proc.stdin.write((json.dumps(peticion) + "\n").encode())
        self.proc.stdin.flush()
        cabeza = self.proc.stdout.readline().decode().split(" ", 2)
        if cabeza[0] != "OK":
            raise RuntimeError(f"{self.nombre}: " + (" ".join(cabeza[1:]).strip() or "el worker terminó"))
        tasa, n = int(cabeza[1]), int(cabeza[2])
        return self.proc.stdout.read(n), tasa

    def parar(self):
        if self.listo():
            self.proc.stdin.close()   # el worker termina al cerrarse su stdin
            try:
                self.proc.wait(10)
            except subprocess.TimeoutExpired:
                self.proc.kill()
        self.proc = self.disp = None


_kokoro = _Worker("kokoro", KOKORO_PY, "kokoro_worker.py")   # Kokoro-82M, ~2 GB de RAM
_f5 = _Worker("f5", F5_PY, "f5_worker.py")                    # F5-Spanish, clona voz/refs/
_WORKERS = (_kokoro, _f5)


def _peticion(perfil, linea):
    """Lo que el worker del motor necesita para sintetizar una línea."""
    pet = {"texto": linea, "velocidad": perfil["velocidad"] / 100}
    if perfil["motor"] == "f5":
        ref_wav, ref_txt = voz_config.ruta_ref(perfil["voz"])
        pet.update(ref_wav=str(ref_wav), ref_txt=ref_txt, pasos=int(perfil["pasos"]))
    else:
        pet.update(voz=perfil["voz"], idioma=perfil.get("idioma", "auto"))
    return pet


def _worker_tts(perfil, texto):
    w = _kokoro if perfil["motor"] == "kokoro" else _f5
    partes, tasa = [], 24000
    with w.lock:
        lineas = _lineas(texto)
        for i, linea in enumerate(lineas):
            _chequear_salto()
            pcm, tasa = w.pide(_peticion(perfil, linea), perfil.get("dispositivo", "cpu"))
            if i:
                partes.append(bytes(int(tasa * perfil["pausa"]) * 2))
            partes.append(pcm)
            _prog["frac"] = (i + 1) / len(lineas)
    return _volumen(b"".join(partes), perfil["volumen"] / 100), tasa


# S2 Pro: un proceso por petición (carga ~11 GB, usa ~20 GB de RAM y los libera al
# terminar); de a una por vez. En CPU tarda ~100× la duración del audio.
_s2_lock = threading.Lock()


def _ram_libre_mb():
    with open("/proc/meminfo") as f:
        for linea in f:
            if linea.startswith("MemAvailable:"):
                return int(linea.split()[1]) // 1024
    return 0


def _s2_tts(perfil, texto):
    py = FISH_DIR / ".venv/bin/python"
    snap = voz_config._hf_snapshot("fishaudio/s2-pro")
    if not py.is_file() or snap is None:
        raise RuntimeError("s2 no está instalado (corre qwen-voz-motores)")
    ref_wav, ref_txt = voz_config.ruta_ref(perfil["voz"])
    _prog["frac"] = None   # un proceso opaco: no hay cómo medir el avance
    with _s2_lock:
        libre = _ram_libre_mb()
        if libre < S2_RAM_MB:   # sin esto el kernel mata procesos al azar (o a llama-server)
            raise RuntimeError(f"s2 necesita ~{S2_RAM_MB // 1000} GB de RAM libre y hay {libre // 1000} GB: "
                               "apaga el modelo grande o usa «Qwen 9B»/«Ninguno»")
        with tempfile.TemporaryDirectory(prefix="voz-s2-") as tmp:
            salida = Path(tmp) / "s2.wav"
            global _s2_proc
            _chequear_salto()
            p = _s2_proc = subprocess.Popen(
                [str(py), "fish_speech/models/text2semantic/inference.py", "--checkpoint-path", str(snap),
                 "--device", "cpu", "--text", texto, "--prompt-audio", str(ref_wav),
                 "--prompt-text", ref_txt, "--output", str(salida), "--output-dir", tmp],
                cwd=FISH_DIR, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
                preexec_fn=_morir_con_el_padre,
                env={**os.environ, "HF_HUB_OFFLINE": "1", "CUDA_VISIBLE_DEVICES": ""})
            try:
                p.wait()
            finally:
                _s2_proc = None
            _chequear_salto()
            if p.returncode or not salida.is_file():
                # sin la salida de fish: puede citar el texto (privacidad, incógnito incluido)
                raise RuntimeError(f"s2 falló (código {p.returncode})")
            pcm, tasa = _wav_a_pcm(salida.read_bytes())
    return _volumen(pcm, perfil["volumen"] / 100), tasa


# s2gguf: S2 Pro cuantizado en un servidor s2.cpp persistente (modelo cargado una vez).
# Se reinicia si el perfil pide otra variante (cuantización / dispositivo).
S2CPP_PORT = int(os.environ.get("VOZ_S2CPP_PORT", "8779"))
S2CPP_LOG = Path(os.environ.get("QWEN_DATA") or os.path.expanduser("~/.local/share/qwen")) / "s2cpp.log"
_s2cpp = None            # Popen del servidor
_s2cpp_variante = None   # (cuant, dispositivo) cargada
_s2cpp_lock = threading.Lock()


def _s2cpp_parar():
    global _s2cpp, _s2cpp_variante
    if _s2cpp is not None and _s2cpp.poll() is None:
        _s2cpp.terminate()
        try:
            _s2cpp.wait(10)
        except subprocess.TimeoutExpired:
            _s2cpp.kill()
    _s2cpp, _s2cpp_variante = None, None


def _s2cpp_log_cola():
    try:
        return " | ".join(S2CPP_LOG.read_text(errors="replace").strip().splitlines()[-4:])
    except OSError:
        return "(sin log)"


def _s2cpp_asegurar(cuant, dispositivo):
    """Deja corriendo el servidor s2.cpp con esa variante (llamar con _s2cpp_lock tomado)."""
    global _s2cpp, _s2cpp_variante
    if _s2cpp is not None and _s2cpp.poll() is None and _s2cpp_variante == (cuant, dispositivo):
        return
    _s2cpp_parar()
    binario = voz_config.s2cpp_bin()
    if binario is None:
        raise RuntimeError("s2.cpp no está compilado (corre qwen-voz-motores)")
    gguf, tok = voz_config.ruta_gguf(cuant)
    disp = ["--cuda", "0", "-ngl", "-1"] if dispositivo == "gpu" else ["-ngl", "0", "--codec-cpu"]
    S2CPP_LOG.parent.mkdir(parents=True, exist_ok=True)
    env = {k: v for k, v in os.environ.items() if k != "CUDA_VISIBLE_DEVICES"}   # el dispositivo lo fija `disp`
    with open(S2CPP_LOG, "wb") as log:
        _s2cpp = subprocess.Popen([str(binario), "--server", "-H", "127.0.0.1", "-P", str(S2CPP_PORT),
                                   "-m", str(gguf), "-t", str(tok), *disp],
                                  stdout=log, stderr=subprocess.STDOUT, start_new_session=True, env=env)
    _s2cpp_variante = (cuant, dispositivo)
    for _ in range(240):   # cargar el GGUF puede tardar; tope 120 s
        if _s2cpp.poll() is not None:
            _s2cpp_variante = None
            raise RuntimeError("s2.cpp no arrancó: " + _s2cpp_log_cola())
        try:
            socket.create_connection(("127.0.0.1", S2CPP_PORT), 0.5).close()
            return
        except OSError:
            time.sleep(0.5)
    _s2cpp_parar()
    raise RuntimeError("s2.cpp no abrió el puerto en 120 s: " + _s2cpp_log_cola())


def _multipart(campos, archivos):
    """multipart/form-data con stdlib. campos: {nombre: str}; archivos: {nombre: (archivo, bytes)}."""
    limite = "----voz" + os.urandom(12).hex()
    partes = []
    for k, v in campos.items():
        partes.append(f'--{limite}\r\nContent-Disposition: form-data; name="{k}"\r\n\r\n{v}\r\n'.encode())
    for k, (nombre, datos) in archivos.items():
        partes.append(f'--{limite}\r\nContent-Disposition: form-data; name="{k}"; filename="{nombre}"\r\n'
                      f"Content-Type: application/octet-stream\r\n\r\n".encode() + datos + b"\r\n")
    partes.append(f"--{limite}--\r\n".encode())
    return b"".join(partes), f"multipart/form-data; boundary={limite}"


def _s2gguf_tts(perfil, texto):
    ref_wav, ref_txt = voz_config.ruta_ref(perfil["voz"])
    with _s2cpp_lock:
        _s2cpp_asegurar(perfil.get("cuant", "q4_k_m"), perfil.get("dispositivo", "cpu"))
        # PCM s16le crudo: el WAV por defecto de s2.cpp es float32 (formato 3), que `wave` no lee
        params = json.dumps({"stream": True, "output_format": "pcm_s16le",
                             "temperature": perfil.get("temperatura", 0.8),
                             "top_p": perfil.get("top_p", 0.8),
                             # tope contra síntesis desbocadas (sin EOS llegaba a 1024 frames ≈ 47 s):
                             # medido ~6 frames/palabra; 15 deja holgura para etiquetas y pausas
                             "max_new_tokens": min(1024, max(150, 15 * len(texto.split()))),
                             "segment_sentences": True,   # frase a frase: pausa fija + mejor en textos largos
                             "sentence_pause_ms": int(perfil.get("pausa", 0.2) * 1000)})
        cuerpo, ctype = _multipart({"text": texto, "reference_text": ref_txt, "params": params},
                                   {"reference": (ref_wav.name, ref_wav.read_bytes())})
        global _s2cpp_sock
        _chequear_salto()
        conn = http.client.HTTPConnection("127.0.0.1", S2CPP_PORT, timeout=30 * 60)
        try:
            # 503 = sigue ocupado con una síntesis recién saltada (cancela en el cuadro
            # siguiente, pero tarda un instante en soltarla): reintenta hasta ~10 s.
            for _ in range(20):
                conn.connect()
                _s2cpp_sock = conn.sock   # saltar() lo cierra y s2.cpp cancela
                conn.request("POST", "/generate", body=cuerpo, headers={"Content-Type": ctype})
                r = conn.getresponse()
                if r.status != 503:
                    break
                r.read()
                conn.close()
                _chequear_salto()
                time.sleep(0.5)
            if r.status != 200:
                raise RuntimeError(f"s2.cpp respondió {r.status}: {r.read()[:300].decode(errors='replace')}")
            tasa = int(r.headers.get("X-Audio-Sample-Rate") or 44100)
            # ponytail: % estimado — audio recibido vs ~14 caracteres por segundo de habla
            # (+ pausas); tope 99 % hasta que termina. Medirlo por frase si se queda corto.
            frases = max(1, len(re.findall(r"[.!?…]+", texto)))
            esperado = (len(sin_etiquetas(texto)) / 14 + frases * perfil.get("pausa", 0.2)) * tasa * 2
            trozos = []
            while trozo := r.read(32768):
                trozos.append(trozo)
                _prog["frac"] = min(0.99, sum(map(len, trozos)) / max(esperado, 1))
            pcm = b"".join(trozos)
            _chequear_salto()
        except (OSError, http.client.HTTPException) as e:
            _chequear_salto()   # el corte lo provocó saltar(): no es un error
            raise RuntimeError(f"s2.cpp no responde ({e}): " + _s2cpp_log_cola())
        finally:
            _s2cpp_sock = None
            conn.close()
    return _volumen(pcm[: len(pcm) // 2 * 2], perfil["volumen"] / 100), tasa


def precargar():
    """Deja listo el motor del perfil activo y libera los demás (RAM/VRAM).
    Devuelve el estado `cargado`. Lo llama POST /api/precargar y el arranque del servidor."""
    perfil = voz_config.limpiar(voz_config.perfil_activo())
    motor = perfil["motor"]
    if motor != "s2gguf":
        with _s2cpp_lock:
            _s2cpp_parar()
    for w in _WORKERS:
        if motor != w.nombre:
            with w.lock:
                w.parar()
    gpu = perfil.get("dispositivo") == "gpu"
    if motor != "piper" or not gpu:   # suelta las sesiones de piper en GPU (VRAM)
        for k in [k for k in _voces_cargadas if k[1]]:
            del _voces_cargadas[k]
    if motor in ("kokoro", "f5"):
        w = _kokoro if motor == "kokoro" else _f5
        with w.lock:
            w.pide(_peticion(perfil, "hola"), perfil["dispositivo"])
    elif motor == "s2gguf":
        with _s2cpp_lock:
            _s2cpp_asegurar(perfil["cuant"], perfil["dispositivo"])
    elif motor == "piper":
        _voice_for(perfil["voz"], gpu)
    return cargado()


def cargado():
    """Qué motor está caliente ahora (para la UI)."""
    perfil = voz_config.perfil_activo()
    motor = perfil.get("motor", "piper")
    if motor == "s2gguf":
        listo = _s2cpp is not None and _s2cpp.poll() is None
        return {"motor": motor, "listo": listo,
                "variante": "{}·{}".format(*_s2cpp_variante) if listo and _s2cpp_variante else None}
    if motor in ("kokoro", "f5"):
        w = _kokoro if motor == "kokoro" else _f5
        return {"motor": motor, "listo": w.listo(), "variante": w.disp if w.listo() else None}
    if motor == "piper":
        return {"motor": motor, "listo": True, "variante": perfil.get("dispositivo", "cpu")}
    return {"motor": motor, "listo": motor == "s2"}   # s2 (Python) no se precarga


def _parar_hijos(*_):
    with _s2cpp_lock:
        _s2cpp_parar()
    for w in _WORKERS:
        w.parar()


def sintetizar(perfil, texto):
    """perfil: dict ya validado por voz_config.limpiar(). Devuelve (pcm_s16le_mono, tasa)."""
    motor = perfil.get("motor", "piper")
    if motor not in ("s2", "s2gguf"):   # solo S2 Pro interpreta [sigh] [laughing]...
        texto = sin_etiquetas(texto)
    if not texto.strip():
        return b"", 22050
    _saltar.clear()
    _prog.update(activo=True, frac=0.0, t0=time.time(), motor=motor)
    try:
        pcm, tasa = {"piper": _piper, "kokoro": _worker_tts, "f5": _worker_tts, "s2": _s2_tts,
                     "s2gguf": _s2gguf_tts}[motor](perfil, texto)
    finally:
        _prog["activo"] = False
    tempo = perfil["velocidad"] / 100 if motor == "s2gguf" else 1.0   # los demás ya la aplican al generar
    return _aplicar_tono(pcm, tasa, perfil["tono"], tempo)


class Handler(BaseHTTPRequestHandler):
    def _send(self, code, body, ctype="application/json"):
        if isinstance(body, (dict, list)):
            body = json.dumps(body).encode("utf-8")
        data = body if isinstance(body, bytes) else body.encode("utf-8")
        self.send_response(code)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)

    def _leer_json(self):
        n = int(self.headers.get("Content-Length", "0") or "0")
        if not 0 < n <= 1 << 20:
            raise ValueError("cuerpo inválido")
        return json.loads(self.rfile.read(n))

    def do_GET(self):
        if self.path == "/health":
            return self._send(200, "ok", "text/plain")
        if self.path == "/api/progreso":
            if _prog["activo"]:
                pct = "-" if _prog["frac"] is None else str(int(_prog["frac"] * 100))
                linea = f"1 {pct} {int(time.time() - _prog['t0'])} {_prog['motor']}"
            else:
                perfil = voz_config.perfil_activo()
                linea = f"0 - 0 {perfil.get('motor', 'piper')} {voz_config.leer_perfiles().get('activo', '')}"
            return self._send(200, linea + "\n", "text/plain")
        if self.path == "/api/estado":
            doc = voz_config.leer_perfiles()
            return self._send(200, {"voces": voz_config.voces_por_motor(), "rangos": voz_config.RANGOS,
                                    "motores": voz_config.motores_instalados(), "corriendo": True,
                                    "cargado": cargado(), **doc})
        if self.path == "/api/catalogo":
            try:
                instaladas = set(voz_config.voces())
                lista = [{"clave": k, "calidad": v["calidad"], "mb": v["mb"]}
                          for k, v in sorted(voz_config.catalogo().items()) if k not in instaladas]
                return self._send(200, lista)
            except OSError as e:
                return self._send(502, {"error": f"sin acceso al catálogo: {e}"})
        self._send(404, {"error": "no existe"})

    def do_POST(self):
        try:
            if self.path == "/hablar":
                datos = self._leer_json()
                texto = str(datos.get("texto", ""))
                try:
                    pcm, tasa = sintetizar(voz_config.perfil_activo(), texto)
                except Saltado:
                    pcm, tasa = b"", 22050   # voz-hook.ts no reproduce nada
                self.send_response(200)
                self.send_header("Content-Type", "audio/x-raw")
                self.send_header("X-Sample-Rate", str(tasa))
                self.send_header("X-Canales", "1")
                self.send_header("Content-Length", str(len(pcm)))
                self.end_headers()
                self.wfile.write(pcm)
                return
            if self.path == "/api/probar":
                datos = self._leer_json()
                texto = str(datos.get("texto", "")).strip()[:3000]
                if not texto:
                    raise ValueError("texto vacío")
                perfil = voz_config.limpiar(datos.get("perfil") or {})
                pcm, tasa = sintetizar(perfil, texto)
                return self._send(200, _pcm_a_wav(pcm, tasa), "audio/wav")
            if self.path == "/api/saltar":
                saltar()
                return self._send(200, {"ok": True})
            if self.path == "/api/precargar":
                return self._send(200, {"ok": True, "cargado": precargar()})
            if self.path == "/api/descargar":
                datos = self._leer_json()
                voz_config.descargar(str(datos.get("voz", "")))
                return self._send(200, {"ok": True})
            if self.path == "/api/guardar":
                datos = self._leer_json()
                doc = voz_config.guardar_perfiles(datos.get("activo"), datos.get("perfiles") or {})
                return self._send(200, {"ok": True, **doc})
            self._send(404, {"error": "no existe"})
        except Saltado:
            self._send(409, {"error": "saltado"})
        except (ValueError, KeyError, TypeError, json.JSONDecodeError) as e:
            print(f"error en {self.path}: {e!r}", file=sys.stderr, flush=True)
            self._send(400, {"error": str(e)})
        except OSError as e:
            print(f"error en {self.path}: {e!r}", file=sys.stderr, flush=True)
            self._send(502, {"error": str(e)})
        except (subprocess.SubprocessError, RuntimeError, wave.Error) as e:
            print(f"error en {self.path}: {e!r}", file=sys.stderr, flush=True)
            self._send(500, {"error": str(e)})

    def log_message(self, *args):  # sin log de cada petición
        pass


if __name__ == "__main__":
    srv = ThreadingHTTPServer(("127.0.0.1", PORT), Handler)
    # Al apagarse (qwen-stop, «Apagar», _voz_down) se lleva el servidor s2.cpp y los workers.
    atexit.register(_parar_hijos)
    signal.signal(signal.SIGTERM, lambda *_: sys.exit(0))   # sys.exit → corre atexit
    print(f"voz: lista en 127.0.0.1:{PORT}", flush=True)

    def _precarga_inicial():   # `qwen` + Voz: deja listo el perfil activo sin esperar la 1ª frase
        try:
            precargar()
        except Exception as e:  # noqa: BLE001 — la voz sigue sirviendo; el error vuelve en /hablar
            print(f"voz: precarga falló: {e}", file=sys.stderr, flush=True)
    threading.Thread(target=_precarga_inicial, daemon=True).start()
    try:
        srv.serve_forever()
    except (KeyboardInterrupt, SystemExit):
        pass
