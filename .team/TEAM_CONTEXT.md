# JET · Contexto compartido del equipo

> Archivo generado automáticamente por JET. No lo edites a mano.
> Proyecto: **Equipo** · Actualizado: `2026-11-23T17:40:47.970937975+00:00`

**Resumen:** 2 abiertas · 2 en curso · 0 bloqueadas · 2 completadas · 3 personas

## Reglas obligatorias para agentes de IA

1. Antes de tocar código, ejecuta `.team/bin/jet status` (o `jet status`) y lee tu bandeja local.
2. Trabaja únicamente en tareas asignadas a tu identidad local. Si no tienes tareas, pide instrucciones; no inventes trabajo.
3. Actúa como un compañero senior: entiende, planifica, verifica con pruebas y revisa tu diff. No declares terminado sin evidencia.
4. Respeta los archivos y ramas bloqueados por otras personas. Si necesitas uno, coordina primero.
4. Registra el avance con `jet log <ID> "nota"` y cierra con `jet done <ID> --note "..."`.
6. No edites `.team/state.json` ni este archivo manualmente. Usa siempre el CLI. JET sincroniza el estado automáticamente.
7. Antes de crear código o una rama, revisa las tareas completadas para no duplicar trabajo.

## Tareas activas

### @Alberto

- **JET-52KWHJ** · Validar la terminal con OpenCode — `En curso` · rama `feat/terminal`
  - Contexto: Abrir OpenCode desde la barra de la terminal y comprobar que el PTY responde.
  - Prioridad: Alta
  - Archivos sensibles: src/terminal.rs
- **JET-NURE3K** · Preparar la conexión con GitHub — `En curso` · rama `feat/github`
  - Contexto: Configurar origin y validar la sincronización de la rama team-sync.
  - Archivos sensibles: src/sync.rs

### @Beto Lima

- **JET-EF3EEC** · Revisar accesibilidad del editor — `Abierta` · rama `audit/a11y`
  - Contexto: Auditar navegación por teclado y contraste del editor.
  - Archivos sensibles: src/editor.rs

### @Carlos Ruiz

- **JET-G6WKVN** · Preparar migración de datos — `Abierta` · rama `chore/datos`
  - Contexto: Script reversible y prueba en staging antes del release.
  - Prioridad: Alta
  - Archivos sensibles: migrations/0093.sql

## Bloqueos de archivos y ramas

- **BLOQUEO** `src/sync.rs` → JET-NURE3K (@Alberto, En curso)
- **BLOQUEO** `src/terminal.rs` → JET-52KWHJ (@Alberto, En curso)
- **RAMA** `feat/github` → JET-NURE3K (@Alberto)
- **RAMA** `feat/terminal` → JET-52KWHJ (@Alberto)

## Completadas recientemente

- **JET-VNRKNH** · Pulir la bandeja de tareas — completada por @Alberto · rama `feat/bandeja` · commit `d994833f`
  - Resultado: Scroll y estados revisados; falta pulir el espaciado.
- **JET-QF5K38** · Crear estructura del repositorio — completada por @Alberto · rama `chore/bootstrap` · commit `d994833` · https://github.com/acme/equipo/pull/1
  - Resultado: Estructura lista y verificada.

## Últimos eventos

- `2026-04-02T23:22:06+00:00` · **GIT** · @ekbfjefbfb — 5efdf345: chore: actualizar requirements.txt con dependencias certificadas para AutoGen (Producción Render)
- `2026-04-02T23:26:43+00:00` · **GIT** · @ekbfjefbfb — 0f825b3e: feat: Orquestación Autónoma v7.0 y Aislamiento Multi-Usuario Nivel Dios
- `2026-04-02T23:29:41+00:00` · **GIT** · @ekbfjefbfb — 7a39569c: feat: Omnipresencia Agéntica v8.0 - Integración en Documentos y Búsqueda Profunda
- `2026-04-02T23:32:35+00:00` · **GIT** · @ekbfjefbfb — 1715430c: feat: Omnipresencia Agéntica Total - Infiltración en Voz, Sesiones y Memoria Semántica
- `2026-04-02T23:39:57+00:00` · **GIT** · @ekbfjefbfb — cf2c950c: fix: SmartCache resilience and final agentic orchestration tuning
- `2026-04-02T23:54:07+00:00` · **GIT** · @ekbfjefbfb — e9f0fe91: Fix NameError: define messages variable before use and fix streaming logic
- `2026-04-03T00:23:05+00:00` · **GIT** · @ekbfjefbfb — 97c8036b: fix: rollback sessions on error + agent await + timeout
- `2026-04-03T00:43:12+00:00` · **GIT** · @ekbfjefbfb — d7e23580: fix: core authentication syntax and user context resilience v9.5.1
- `2026-04-03T00:54:52+00:00` · **GIT** · @ekbfjefbfb — b9d514c5: fix: agentic resilience with heartbeat keep-alive and synchronize timers v9.8.5
- `2026-04-03T01:18:28+00:00` · **GIT** · @ekbfjefbfb — 6a577645: feat: Contextual Memory and Multipart Resilience v11.0. Fix 422 errors and robust conversation threads.
- `2026-04-03T01:27:17+00:00` · **GIT** · @ekbfjefbfb — e3ecc5d3: feat: Autonomous Research Agents v12.0. Integrated search_web tool and resilient heartbeat streaming.
- `2026-04-03T01:31:49+00:00` · **GIT** · @ekbfjefbfb — d15ea71b: feat: Balanced God-Level Optimization. Locked T=0.0 with 6 reasoning turns for perfect speed/intelligence balance.
- `2026-04-03T14:46:08+00:00` · **GIT** · @ekbfjefbfb — 4d1c3736: feat: Autonomous Pedagogical Tutor v15.0. Integrated self-correction, academic feedback, and deep student memory.
- `2026-04-03T14:51:01+00:00` · **GIT** · @ekbfjefbfb — 71afde5a: feat: Incredible Helper Persona v16.0. Integrated empathy labeling, analogies, and actionable academic value.
- `2026-04-03T14:57:26+00:00` · **GIT** · @ekbfjefbfb — 8e0810b2: feat: Elite Academic Tutor v17.2. Global synchronization of empathy, LaTeX formulas, orjson speed boost, and token batching.
- `2026-04-03T15:08:02+00:00` · **GIT** · @ekbfjefbfb — 3f1676b7: feat: Project Iris v20.0. Unified AI identity under the name 'Iris' across all core modules and streaming states.
- `2026-04-03T15:14:05+00:00` · **GIT** · @ekbfjefbfb — b45f2cd1: feat: Subtle Iris Identity v21.0. Reverted to generic 'Tutor' labels in stream and adjusted prompts for natural name disclosure.
- `2026-04-03T15:27:51+00:00` · **GIT** · @ekbfjefbfb — 5922e1d7: fix: Resolve NameError length_rule in chat_ai.py and restore LLM streaming stability.
- `2026-04-03T15:31:05+00:00` · **GIT** · @ekbfjefbfb — 92054cc0: feat: Hybrid Resilience Armor v23.0. Pedagogical error messages with hidden technical debug info for development. Unified Iris identity during fallbacks.
- `2026-04-03T15:43:48+00:00` · **GIT** · @ekbfjefbfb — b337b8ef: fix: Restored conversation memory in streaming and disabled destructive topic-cache clearing. Iris is no longer repetitive and intro rules now respect history.
- `2026-04-03T15:45:40+00:00` · **GIT** · @ekbfjefbfb — 209258da: fix: Ultimate Stability Armor. Deduplication, smart fallback, and context hygiene to prevent AI loops and repetitions.
- `2026-04-03T15:47:16+00:00` · **GIT** · @ekbfjefbfb — c97c97a9: fix: Final Precision Stability Armor. Enabled Continuity Mode and Deduplication across all chat paths. Verified history and fallback awareness.
- `2026-04-03T18:32:55+00:00` · **GIT** · @ekbfjefbfb — ebc1962a: FIX ROOT: import time and thread-safe loop capture for Iris v30.0
- `2026-04-03T18:56:49+00:00` · **GIT** · @ekbfjefbfb — 69eeedaf: FIX: NoneType role in agents + Full support for JSON/Base64 media v31.3
- `2026-04-03T18:58:24+00:00` · **GIT** · @ekbfjefbfb — 8a2eb75f: OMNI-CAPABLE FIX: Full document/image support for WS & HTTP + Agent Stability v31.4

## Equipo

- @Alberto · id `alberto` · rol **Jefe** · última señal `2026-11-23T17:39:22.775545718+00:00`
- @Beto Lima · id `beto-lima` · rol **Colaborador** · última señal `sin actividad`
- @Carlos Ruiz · id `carlos-ruiz` · rol **Colaborador** · última señal `sin actividad`

## CLI JET

```bash
.team/bin/team status --json        # mi bandeja + bloqueos del equipo
.team/bin/team list --all --json    # todas las tareas y estado
.team/bin/team create --to "Nombre" --title "..." --context "..." --branch "feat/..." --files "a,b"
.team/bin/team take JET-XXXX        # empezar una tarea asignada a mí
.team/bin/team log JET-XXXX "avance"
.team/bin/team done JET-XXXX --note "resultado" --pr "https://..."
.team/bin/team sync                  # forzar sincronización con GitHub
```

_La sincronización de JET usa una rama dedicada `team-sync`; la rama de trabajo nunca se modifica._
