---
name: agy-bridge
description: Usa esta skill para delegar trabajo a `agy` (el CLI de Antigravity, Gemini) siempre que el usuario nombre agy, Gemini o Antigravity, pida una segunda opinión o una crítica de un plan, un diseño o un análisis, necesite investigar en internet, o encargue trabajo mecánico y voluminoso sobre muchos archivos: análisis de datos, barridos, refactores repetitivos. Úsala aunque no pida delegar explícitamente. Lo que se delega no ocupa el contexto de esta conversación y los entregables quedan en disco.
allowed-tools: Bash(python ${CLAUDE_SKILL_DIR}/scripts/bridge.py *), Bash(python3 ${CLAUDE_SKILL_DIR}/scripts/bridge.py *)
---

# Puente hacia agy

`agy` es el CLI de Antigravity (Gemini). Corre en su propio sandbox, así que su trabajo no
consume el contexto de esta conversación y los entregables quedan en disco. **Tú diseñas,
verificas y sintetizas; él ejecuta.**

Delegar cuesta el arranque del binario y el rato de redactar el encargo. Si escribir el brief
cuesta más que hacer la tarea, hazla tú.

## Invocación

```bash
python ${CLAUDE_SKILL_DIR}/scripts/bridge.py "<instrucción>"
```

| Qué | Bandera |
|---|---|
| Seguir el hilo activo | `--continue` |
| Hilo con nombre (líneas paralelas) | `--thread <nombre>` |
| Retomar por ID de conversación | `--id <uuid>` |
| Ver los hilos del proyecto | `--list` |
| Trabajar sobre otro proyecto | `--project <ruta>` |

Sin `--project`, el proyecto es el **directorio actual**: es lo que se declara a `agy` como
workspace y donde se guarda el estado. Las rutas de la instrucción se resuelven desde ahí. Una
opción desconocida da error y salida 2, en vez de colarse como texto del brief.

Para instrucciones largas o con datos, redirige la entrada estándar desde un archivo. `cat`
no existe en todas las shells de Windows:

```bash
python ${CLAUDE_SKILL_DIR}/scripts/bridge.py --thread analisis < brief.txt
```

## Riesgo: agy corre sin supervisión

`bridge.py` invoca `agy` en modo headless con `--dangerously-skip-permissions`, porque en
headless no hay nadie que apruebe nada. El único freno es un hook `PreToolUse`, declarado en
el `.agents/hooks.json` del proyecto o en un `hooks.json` global bajo `~/.gemini/config/`. La
señal `[AGY_NO_GUARDIAN]` avisa cuando no hay ninguno, aunque solo comprueba el del proyecto:
con un hook global puede avisar de más.

Eso gobierna cómo se redacta el brief: una vez enviado, `agy` no se detiene a pedir permiso a
mitad de camino.

## Cómo escribir el brief

El brief es lo único que `agy` recibe. No ve esta conversación ni puede pedirte aclaraciones
mientras trabaja, así que tiene que bastarse solo:

```
Objetivo: qué hay que averiguar o construir.
Archivos: las rutas concretas que debe mirar.
Restricciones: solo lectura; dónde guardar los scripts y los entregables.
Devuelve: qué formato esperas de vuelta.
```

Por el riesgo de la sección anterior, declara **solo lectura** de forma explícita en tareas de
análisis o de opinión, y confirma con el usuario antes de delegar cualquier cosa destructiva.

Como solo ves el resumen final y nunca su razonamiento intermedio, pide que sea concreto y
crítico en vez de complaciente, y que responda `NO SÉ` antes que inferir. En investigación,
exige la URL y la cita textual que sustenta cada afirmación: es lo único que te permite
verificar después sin repetir la búsqueda.

Reparte así el trabajo de investigación: `agy` descubre y recopila las fuentes; para verificar
una URL que ya tienes, baja la página tú y compruébalo sobre el texto crudo.

## Hilos

`--continue` retoma la conversación del hilo (sin `--thread`, opera sobre `principal`). Usa
hilos con nombre para líneas de trabajo que no deben contaminarse entre sí. Abre uno nuevo,
con brief compacto, cuando cambie la naturaleza del trabajo.

Para releer un bloque anterior, lee su JSON en `<proyecto>/.agy_state/bitacora/` en vez de
retomar el hilo: así no reinyectas todo el historial.

## Entregables

Los entregables viven en disco y el resumen que vuelve por el canal no los sustituye, así que
dile dónde guardarlos. Pide también que cada bloque analítico guarde el script que lo generó:
con eso puedes reproducirlo o corregirlo sin rehacer el análisis entero.

Para gráficos, pide dos verificaciones a su cargo: que aplique el verificador de layout del
proyecto si existe, y que abra el PNG y confirme que se lee. Ninguna sustituye a la tuya —
después abre tú el artefacto y juzga si sostiene el argumento.

## Señales de vuelta

| Señal | Significado |
|---|---|
| `[AGY_THREAD]` | Hilo, ID y si fue nuevo o retomado |
| `[AGY_METRICS]` / `[AGY_DELTA]` | Consumo. Con `--continue` el `Input` reenvía la conversación entera; el `[AGY_DELTA]` aísla lo nuevo |
| `[AGY_WARNING]` | El hilo no quedó fijado |
| `[AGY_NO_GUARDIAN]` | No hay hook que frene a `agy`. Es un aviso, no un error |
| `[AGY_FAILED]` + salida 1 | No completó la tarea |

Ante `[AGY_FAILED]`, haz el trabajo tú mismo y dile al usuario que `agy` falló y por qué. Los
fallos son deterministas, así que reintentar por delegación repite el mismo resultado. La
respuesta cruda del último intento queda en la bitácora aunque la ejecución falle.
