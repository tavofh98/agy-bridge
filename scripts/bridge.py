"""Puente para delegar tareas al CLI de Antigravity (agy) con hilos con nombre.

Vive dentro de la carpeta de la skill y se referencia con ${CLAUDE_SKILL_DIR},
de modo que la carpeta entera es portatil: copiala a ~/.claude/skills/ y sirve
en todos los proyectos, o a <proyecto>/.claude/skills/ y sirve solo en ese.

Por eso NADA cuelga de la ubicacion de este archivo. El proyecto sobre el que
agy trabaja es el directorio actual, o el que se pase con --project, y ahi
mismo vive el estado de los hilos.
"""
import json
import os
import pathlib
import re
import shutil
import subprocess
import sys
from datetime import datetime

# La consola de Windows suele ser cp1252 y las respuestas de agy traen flechas y
# comillas tipograficas: sin esto, imprimir la respuesta revienta con
# UnicodeEncodeError despues de que el trabajo ya se hizo.
for _stream in (sys.stdout, sys.stderr):
    if hasattr(_stream, "reconfigure"):
        _stream.reconfigure(encoding="utf-8", errors="replace")

WINDOWS_AGY_PATH = pathlib.Path(os.environ.get("LOCALAPPDATA", "")) / "agy" / "bin" / "agy.exe"
AGY_BIN = shutil.which("agy") or (str(WINDOWS_AGY_PATH) if WINDOWS_AGY_PATH.exists() else "agy")

MODEL = "gemini-3.7-flash-high"
TIMEOUT_SECS = 1380

VALUE_FLAGS = ("--thread", "--id", "--project")
BARE_FLAGS = ("--continue", "--list")

STATE_DIR = None  # se fija en main() a partir del proyecto


def has_pretooluse_hook(start_dir: pathlib.Path) -> bool:
    """¿Hay un `.agents/hooks.json` utilizable en `start_dir` o en algun ancestro?

    Replica la busqueda que hace agy al descubrir el workspace (CONTRATO_AGY §1).
    Un JSON invalido cuenta como ausencia: agy cargaria cero hooks en silencio.

    Comprueba la precondicion, no que agy haya cargado el hook. Solo informa; la
    decision de correr sin el es de quien invoca.
    """
    for base in [start_dir, *start_dir.parents]:
        candidate = base / ".agents" / "hooks.json"
        if not candidate.is_file():
            continue
        try:
            hooks_data = json.loads(candidate.read_text(encoding="utf-8-sig"))
        except (OSError, ValueError):
            continue
        if isinstance(hooks_data, dict):
            for group in hooks_data.values():
                if isinstance(group, dict) and group.get("PreToolUse"):
                    return True
    return False


def sanitize_thread_name(name: str) -> str:
    clean = re.sub(r"[^A-Za-z0-9_-]", "_", name.strip()).strip("_")
    return clean if clean else "principal"


def load_thread_state(thread: str) -> dict:
    target = STATE_DIR / f"{thread}.json"
    if not target.exists():
        return {}
    try:
        return json.loads(target.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}


def save_thread_state(thread: str, conversation_id: str, input_tokens: int) -> None:
    STATE_DIR.mkdir(parents=True, exist_ok=True)
    target = STATE_DIR / f"{thread}.json"
    temp = STATE_DIR / f"{thread}.json.tmp.{os.getpid()}"
    payload = {
        "conversation_id": conversation_id,
        "input_tokens": input_tokens,
        "updated_at": datetime.now().isoformat(timespec="seconds"),
    }
    try:
        temp.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
        os.replace(temp, target)
    except OSError:
        if temp.exists():
            try:
                temp.unlink()
            except OSError:
                pass


def list_threads() -> int:
    state_files = sorted(STATE_DIR.glob("*.json")) if STATE_DIR.exists() else []
    if not state_files:
        print(f"No hay hilos registrados en {STATE_DIR.parent}.")
        return 0
    print(f"Hilos registrados en {STATE_DIR.parent}:")
    for path in state_files:
        try:
            info = json.loads(path.read_text(encoding="utf-8"))
            conversation_id = (info.get("conversation_id") or "").strip() or "(sin id)"
            # `actualizado` es la clave que escribian las versiones anteriores.
            updated = info.get("updated_at") or info.get("actualizado") or "(desconocido)"
            print(f"  - {path.stem}: id={conversation_id} | "
                  f"tokens={info.get('input_tokens') or 0} | actualizado={updated}")
        except Exception:
            print(f"  - {path.stem}: (archivo corrupto)")
    return 0


def main() -> int:
    global STATE_DIR
    args = sys.argv[1:]

    raw_thread, explicit_thread = "principal", False
    explicit_id = None
    should_continue = False
    wants_list = False
    raw_project = None
    prompt_args = []

    i = 0
    while i < len(args):
        arg = args[i]
        if arg == "--continue":
            should_continue = True
            i += 1
        elif arg == "--list":
            wants_list = True
            i += 1
        elif arg in VALUE_FLAGS and i + 1 < len(args):
            value = args[i + 1]
            if arg == "--thread":
                raw_thread, explicit_thread = value, True
            elif arg == "--id":
                explicit_id = value
            else:
                raw_project = value
            i += 2
        elif arg.startswith(tuple(f"{flag}=" for flag in VALUE_FLAGS)):
            key, value = arg.split("=", 1)
            if key == "--thread":
                raw_thread, explicit_thread = value, True
            elif key == "--id":
                explicit_id = value
            else:
                raw_project = value
            i += 1
        elif arg.startswith("--"):
            # Sin esto, un flag mal escrito se colaria dentro del prompt y se
            # enviaria a agy como texto, en silencio.
            known = ", ".join(BARE_FLAGS + VALUE_FLAGS)
            print(f"Error: opción desconocida '{arg}'. Conocidas: {known}.", file=sys.stderr)
            return 2
        else:
            prompt_args.append(arg)
            i += 1

    # El proyecto es el directorio actual salvo que se diga otra cosa. Nunca la
    # ubicacion de este script: la carpeta de la skill es portatil.
    project = (pathlib.Path(raw_project).expanduser().resolve() if raw_project
               else pathlib.Path.cwd().resolve())
    if not project.is_dir():
        print(f"Error: el proyecto '{project}' no existe o no es un directorio.", file=sys.stderr)
        return 2
    STATE_DIR = project / ".agy_state"

    if wants_list:
        return list_threads()

    prompt = " ".join(prompt_args).strip()
    if not prompt and not sys.stdin.isatty():
        prompt = sys.stdin.read().strip()
    if not prompt:
        print("Error: Se requiere una instrucción.", file=sys.stderr)
        return 2

    thread = sanitize_thread_name(raw_thread)
    is_ephemeral = bool(explicit_id and not explicit_thread)

    if is_ephemeral:
        previous_input_tokens = 0
        target_conversation_id = (explicit_id or "").strip()
        is_resumed = True
    else:
        state = load_thread_state(thread)
        saved_id = (state.get("conversation_id") or "").strip()
        try:
            previous_input_tokens = int(state.get("input_tokens") or 0)
        except (ValueError, TypeError):
            previous_input_tokens = 0
        target_conversation_id, is_resumed = None, False
        if explicit_id:
            target_conversation_id, is_resumed = explicit_id.strip(), True
            if target_conversation_id != saved_id:
                previous_input_tokens = 0
        elif should_continue:
            if saved_id:
                target_conversation_id, is_resumed = saved_id, True
            else:
                print(f"[AGY_WARNING] hilo '{thread}' sin ID previo; se abre conversación nueva")
                previous_input_tokens = 0
        else:
            previous_input_tokens = 0

    # Solo informa. En headless nadie aprueba nada, asi que sin hook agy corre
    # con permisos totales; quien invoca decide si eso es aceptable aqui.
    if not has_pretooluse_hook(project):
        print(f"[AGY_NO_GUARDIAN] No hay .agents/hooks.json en {project} ni en sus ancestros: "
              "agy correrá sin hook, sin clasificador y sin captura previa.", file=sys.stderr)

    cmd = [
        AGY_BIN, "-p", prompt,
        "--model", MODEL,
        "--add-dir", str(project),
        "--output-format", "json",
        "--dangerously-skip-permissions",
        "--print-timeout", "20m",
    ]
    if target_conversation_id:
        cmd.extend(["--conversation", target_conversation_id])

    # Un solo intento: los fallos observados son deterministas (binario ausente,
    # hook roto, error del agente) y reintentar solo gasta tiempo.
    response_data, error_message = None, ""
    proc = None
    try:
        proc = subprocess.run(
            cmd, cwd=str(project), capture_output=True, text=True,
            encoding="utf-8", errors="replace",
            stdin=subprocess.DEVNULL, timeout=TIMEOUT_SECS,
        )
        if proc.stdout:
            try:
                log_dir = STATE_DIR / "bitacora"
                log_dir.mkdir(parents=True, exist_ok=True)
                tag = "efimero" if is_ephemeral else thread
                stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
                (log_dir / f"{stamp}_{tag}.json").write_text(proc.stdout, encoding="utf-8")
            except OSError:
                pass
        response_data = json.loads(proc.stdout)
        if response_data.get("status") != "SUCCESS":
            error_message = response_data.get("error") or proc.stderr or proc.stdout
    except subprocess.TimeoutExpired:
        error_message = f"Timeout ({TIMEOUT_SECS}s) excedido."
    except (json.JSONDecodeError, TypeError):
        error_message = (proc.stderr or proc.stdout if proc else "") or "Salida no JSON"
    except (FileNotFoundError, OSError) as exc:
        error_message = f"No se pudo invocar el ejecutable '{AGY_BIN}': {exc}"

    if not response_data or response_data.get("status") != "SUCCESS":
        print(f"\n[AGY_FAILED] agy no completó la tarea.\nDetalle: {error_message.strip()[:300]}")
        return 1

    print(response_data.get("response", ""))

    stats = (response_data.get("stats") or response_data.get("usage")
             or response_data.get("metadata", {}).get("usage") or {})
    input_tokens = int(stats.get("input_tokens") or stats.get("prompt_tokens") or 0)
    output_tokens = int(stats.get("output_tokens") or stats.get("completion_tokens") or 0)
    total_tokens = int(stats.get("total_tokens") or (input_tokens + output_tokens))
    cached_tokens = int(stats.get("cache_read_tokens") or stats.get("cached_content_token_count")
                        or response_data.get("cache_read_tokens") or 0)

    final_conversation_id = response_data.get("conversation_id") or target_conversation_id or ""
    if not is_ephemeral:
        save_thread_state(thread, final_conversation_id, input_tokens)
        if not final_conversation_id:
            print(f"[AGY_WARNING] respuesta sin conversation_id; el hilo '{thread}' no quedó fijado")

    print("\n---")
    print(f"[AGY_THREAD] hilo: {'(efimero)' if is_ephemeral else thread} | "
          f"id: {final_conversation_id or '(sin id)'} | "
          f"modo: {'retomado' if is_resumed else 'nuevo'}")
    print(f"[AGY_METRICS] Input: {input_tokens} | Output: {output_tokens} | Total: {total_tokens}")
    print(f"[AGY_DELTA] Input nuevo: {max(input_tokens - previous_input_tokens, 0)} | "
          f"Output: {output_tokens} | Cache leido: {cached_tokens}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
