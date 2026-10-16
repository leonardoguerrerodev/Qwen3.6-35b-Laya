# lib/voz.sh — ciclo de vida de voz (TTS con piper, servidor HTTP local).
# Requiere lib/config.sh. Voz es opcional y opt-in: si falta, falla o no hay modelo,
# qwen sigue funcionando sin ella (fail-open). Independiente de TTSiro: sin rutas,
# sockets, venv ni modelos compartidos con ese repo.
# Solo se mata la voz que arrancó esta sesión (VOZ_SPID); una ajena se respeta.

_voz_port_open() { (exec 3<>"/dev/tcp/127.0.0.1/$VOZ_PORT") 2>/dev/null; }

_voz_healthy() { curl -sf --max-time 1 "http://127.0.0.1:$VOZ_PORT/health" >/dev/null 2>&1; }

# Crea el venv con piper-tts la primera vez (una sola vez, necesita red).
_voz_ensure_venv() {
  [ -x "$VOZ_VENV/bin/python" ] && return 0
  echo "voz: creando venv en $VOZ_VENV ..." >&2
  mkdir -p "$(dirname "$VOZ_VENV")" || return 1
  python3 -m venv "$VOZ_VENV" || return 1
  "$VOZ_VENV/bin/pip" install --quiet piper-tts 2>&1 | tail -n 1 >&2
  [ -x "$VOZ_VENV/bin/python" ] || return 1
  echo "voz: venv listo." >&2
}

_voz_up() {
  [ "${QWEN_VOZ:-0}" = 1 ] || return 0
  if [ ! -f "$VOZ_SERVER" ]; then
    echo "voz: no encuentro $VOZ_SERVER (se continúa sin voz)" >&2
    return 0
  fi
  if _voz_port_open; then
    echo "voz: ya corriendo en 127.0.0.1:$VOZ_PORT"
    return 0
  fi
  local model
  model="$(_voz_model_path)" || {
    echo "voz: no encuentro ningún $VOZ_MODEL_GLOB en $QWEN_MODELS_DIR (se continúa sin voz)" >&2
    return 1
  }
  _voz_model_cfg_path >/dev/null || {
    echo "voz: falta $(basename "$model").json junto al modelo (se continúa sin voz)" >&2
    return 1
  }
  _voz_ensure_venv || { echo "voz: no se pudo preparar el venv (se continúa sin voz)" >&2; return 1; }

  echo "voz: arrancando en 127.0.0.1:$VOZ_PORT (modelo: $(basename "$model")) ..."
  VOZ_PORT="$VOZ_PORT" VOZ_MODEL="$model" VOZ_VELOCIDAD="$VOZ_VELOCIDAD" VOZ_RUIDO="$VOZ_RUIDO" \
    VOZ_RUIDO_W="$VOZ_RUIDO_W" VOZ_PAUSA="$VOZ_PAUSA" QWEN_DATA="$QWEN_DATA" \
    "$VOZ_VENV/bin/python" "$VOZ_SERVER" >/dev/null 2>&1 &
  VOZ_SPID=$!
  disown "$VOZ_SPID" 2>/dev/null || true

  local t0=$SECONDS
  until _voz_healthy; do
    if ! kill -0 "$VOZ_SPID" 2>/dev/null; then
      echo "voz: terminó prematuramente (se continúa sin voz)" >&2
      unset VOZ_SPID; return 1
    fi
    if (( SECONDS - t0 >= VOZ_TIMEOUT )); then
      echo "voz: timeout (${VOZ_TIMEOUT}s) (se continúa sin voz)" >&2
      kill "$VOZ_SPID" 2>/dev/null || true
      unset VOZ_SPID; return 1
    fi
    sleep 0.5
  done
  echo "voz: lista en 127.0.0.1:$VOZ_PORT"
}

_voz_down() {
  if [ -n "${VOZ_SPID:-}" ]; then
    kill "$VOZ_SPID" 2>/dev/null || true
    wait "$VOZ_SPID" 2>/dev/null || true
    # el proceso se lanzó con disown: wait no lo espera; sin esto el siguiente arranque ve una voz medio muerta
    local _t0=$SECONDS
    while kill -0 "$VOZ_SPID" 2>/dev/null; do
      if (( SECONDS - _t0 >= 30 )); then kill -9 "$VOZ_SPID" 2>/dev/null || true; break; fi
      sleep 0.5
    done
    unset VOZ_SPID
  fi
  return 0
}

# Instala los motores kokoro, f5 (F5-Spanish) y s2 (Fish Audio S2 Pro), cada uno en su venv, y la GPU opcional
# de piper/kokoro (onnxruntime-gpu / torch con CUDA; ambos corren igual en CPU).
# Necesita uv, git y red; idempotente. Pesos: Kokoro-82M (~330 MB), F5-Spanish (~1,4 GB) y s2-pro (~11 GB) al caché de HF.
_voz_motores_install() {
  command -v uv >/dev/null 2>&1 || { echo "voz: falta uv (https://docs.astral.sh/uv/)" >&2; return 1; }
  command -v git >/dev/null 2>&1 || { echo "voz: falta git" >&2; return 1; }
  mkdir -p "$QWEN_DATA" || return 1
  echo "voz: piper GPU (onnxruntime-gpu) → $VOZ_VENV"
  _voz_ensure_venv || return 1
  if ! "$VOZ_VENV/bin/pip" show -q onnxruntime-gpu 2>/dev/null; then
    # mismo módulo `onnxruntime`: hay que sacar el de CPU. ponytail: un `pip install -U piper-tts`
    # lo vuelve a traer y pisa al de GPU; si pasa, correr de nuevo qwen-voz-motores.
    "$VOZ_VENV/bin/pip" uninstall -y -q onnxruntime
    "$VOZ_VENV/bin/pip" install -q "onnxruntime-gpu[cuda,cudnn]" || return 1
  fi
  echo "voz: kokoro → $VOZ_KOKORO_VENV"
  [ -x "$VOZ_KOKORO_VENV/bin/python" ] || uv venv -q -p 3.12 "$VOZ_KOKORO_VENV" || return 1
  uv pip install -q -p "$VOZ_KOKORO_VENV/bin/python" --torch-backend auto kokoro soundfile \
    "en_core_web_sm @ https://github.com/explosion/spacy-models/releases/download/en_core_web_sm-3.8.0/en_core_web_sm-3.8.0-py3-none-any.whl" \
    || return 1   # en_core_web_sm: G2P en inglés (idioma en-us/en-gb); sin él misaki lo baja en la 1ª frase
  # venvs de antes traen torch +cpu: pasarlo a la build con CUDA (la GPU se elige por perfil)
  "$VOZ_KOKORO_VENV/bin/python" -c 'import sys, torch; sys.exit("+cpu" in torch.__version__)' ||
    uv pip install -q -p "$VOZ_KOKORO_VENV/bin/python" --torch-backend auto --reinstall-package torch torch || return 1
  echo "voz: f5 → $VOZ_F5_VENV"
  [ -x "$VOZ_F5_VENV/bin/python" ] || uv venv -q -p 3.12 "$VOZ_F5_VENV" || return 1
  uv pip install -q -p "$VOZ_F5_VENV/bin/python" --torch-backend auto f5-tts || return 1
  echo "voz: s2 (fish-speech) → $VOZ_FISH_DIR"
  [ -d "$VOZ_FISH_DIR/.git" ] || git clone -q --depth 1 https://github.com/fishaudio/fish-speech.git "$VOZ_FISH_DIR" || return 1
  # pyaudio (micrófono) no se usa para sintetizar y pide los headers de PortAudio
  (cd "$VOZ_FISH_DIR" && uv sync -q --extra cpu -p 3.12 --no-install-package pyaudio) || return 1
  echo "voz: s2gguf (s2.cpp) → $VOZ_S2CPP_DIR"
  [ -d "$VOZ_S2CPP_DIR/.git" ] || git clone -q --recurse-submodules --depth 1 --shallow-submodules \
    https://github.com/rodrigomatta/s2.cpp.git "$VOZ_S2CPP_DIR" || return 1
  # Privacidad (incógnito incluido): s2.cpp imprime el texto de cada síntesis en su log
  # (s2cpp.log); se cambia por su largo. Idempotente: corre igual tras un clone o un pull.
  sed -i 's|safe_print_ln("Text: " + params.text);|safe_print_ln("Text: (" + std::to_string(params.text.size()) + " bytes)");|' \
    "$VOZ_S2CPP_DIR/src/s2_pipeline.cpp"
  # «Saltar» (voz_server /api/saltar): en modo frase a frase s2.cpp solo mira la cancelación
  # entre frases; esto la mira en cada cuadro, como ya hace el modo sin segmentar.
  grep -q "qwen: saltar" "$VOZ_S2CPP_DIR/src/s2_server.cpp" || sed -i \
    's|^\( *\)segment_params.text = segments\[i\];|&\n\1segment_params.gen.on_frame = [\&sink](const s2::FrameCallbackData \&) { return !sink.is_cancelled(); };  // qwen: saltar|' \
    "$VOZ_S2CPP_DIR/src/s2_server.cpp"
  # cudart compartido: Fedora no trae libcudart_static (mismo ajuste que el llama.cpp de esta máquina)
  if ! (cd "$VOZ_S2CPP_DIR" && cmake -B build -DCMAKE_BUILD_TYPE=Release -DS2_CUDA=ON \
          -DCMAKE_CUDA_RUNTIME_LIBRARY=Shared -DCMAKE_CUDA_FLAGS="--cudart shared" >/dev/null \
        && cmake --build build --parallel "$(nproc)" >/dev/null); then
    echo "voz: s2.cpp no compiló con CUDA; se compila solo para CPU" >&2
    (cd "$VOZ_S2CPP_DIR" && rm -rf build && cmake -B build -DCMAKE_BUILD_TYPE=Release >/dev/null \
      && cmake --build build --parallel "$(nproc)" >/dev/null) || return 1
  fi
  echo "voz: pesos (caché de HF: ${HF_HOME:-~/.cache/huggingface})"
  "$VOZ_KOKORO_VENV/bin/python" -c 'from huggingface_hub import snapshot_download as d
d("hexgrad/Kokoro-82M", allow_patterns=["config.json", "kokoro-v1_0.pth", "voices/e*.pt"] +
  [f"voices/{v}.pt" for v in ("af_heart", "af_bella", "af_nicole", "af_sky", "af_aoede", "bf_emma")])
d("jpgallegoar/F5-Spanish", allow_patterns=["model_1250000.safetensors", "vocab.txt"])
d("charactr/vocos-mel-24khz")
d("rodrigomt/s2-pro-gguf", allow_patterns=["s2-pro-q4_k_m.gguf", "s2-pro-q8_0.gguf", "tokenizer.json"])
d("fishaudio/s2-pro")' || { echo "voz: falló la descarga (s2-pro pide aceptar su licencia en HF + hf auth login)" >&2; return 1; }
  echo "voz: motores listos. Elige el motor del perfil en /voz.html o con la tecla Z del menú."
}

# Modo independiente (comando `qwen-voz`): voz sola, hasta pulsar Enter.
_voz_standalone() {
  QWEN_VOZ=1 _voz_up || return $?
  if [ -z "${VOZ_SPID:-}" ] && _voz_port_open; then
    echo "voz: ya estaba corriendo fuera de esta sesión; no la detengo."
    return 0
  fi
  read -r -p "Pulsa Enter para detener voz... " _
  _voz_down
  echo "voz: detenida."
}
