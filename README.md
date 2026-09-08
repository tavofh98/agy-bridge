# agy-bridge

Skill de Claude Code que delega trabajo al CLI de Antigravity (`agy`, Gemini). `agy` corre
en su propio sandbox, ve de verdad las imágenes que escribe y busca en internet mejor.
Claude diseña, verifica y sintetiza; `agy` ejecuta.

## Instalación

```bash
git clone <url-de-este-repo> ~/.claude/skills/agy-bridge
```

Nada que editar tras clonar. `SKILL.md` resuelve las rutas con `${CLAUDE_SKILL_DIR}` y
`bridge.py` deriva el proyecto del directorio actual, nunca de su propia ubicación: la
skill es portable entre máquinas y nombres de usuario.

En Windows la ruta es `C:\Users\<usuario>\.claude\skills\agy-bridge`.

## Requisitos que no viajan en el repo

- **El binario `agy` instalado y autenticado.** Las credenciales viven en
  `~/.gemini/oauth_creds.json`, que es local a cada máquina: hay que iniciar sesión allá.
- **`python` o `python3` en el PATH**, tal como lo declara `allowed-tools` en `SKILL.md`.
  Si en la máquina solo existe como `py`, la skill no se dispara.

## Aviso de seguridad

`bridge.py` invoca `agy` con `--dangerously-skip-permissions`, porque en modo headless no
hay nadie que apruebe. **El único freno es un hook `PreToolUse`** declarado en un
`hooks.json` de Antigravity: en el `.agents/` del proyecto, o en `~/.gemini/config/` para
que aplique a todos.

En una máquina recién clonada, sin ese hook, `agy` corre sin ningún freno. El puente avisa
con `[AGY_NO_GUARDIAN]` por consola, pero avisa **después** de que ya invocaste. El
guardián se distribuye aparte de este repositorio.

## Señales que devuelve

| Señal | Significado |
|---|---|
| `[AGY_THREAD]` | Hilo, ID y si fue nuevo o retomado |
| `[AGY_METRICS]` / `[AGY_DELTA]` | Consumo. Con `--continue` el `Input` reenvía la conversación entera; el `[AGY_DELTA]` aísla lo nuevo |
| `[AGY_WARNING]` | El hilo no quedó fijado |
| `[AGY_NO_GUARDIAN]` | No hay hook: `agy` corre sin freno |
| `[AGY_FAILED]` | No completó la tarea |
