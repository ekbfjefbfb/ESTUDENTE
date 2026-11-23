# JET · Contexto compartido del equipo

> Archivo generado automáticamente por JET. No lo edites a mano.
> Proyecto: **Equipo** · Actualizado: `2026-11-23T17:39:22.775546725+00:00`

**Resumen:** 3 abiertas · 1 en curso · 0 bloqueadas · 2 completadas · 3 personas

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
- **JET-NURE3K** · Preparar la conexión con GitHub — `Abierta` · rama `feat/github`
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

- **BLOQUEO** `src/terminal.rs` → JET-52KWHJ (@Alberto, En curso)
- **RAMA** `feat/terminal` → JET-52KWHJ (@Alberto)

## Completadas recientemente

- **JET-VNRKNH** · Pulir la bandeja de tareas — completada por @Alberto · rama `feat/bandeja` · commit `d994833f`
  - Resultado: Scroll y estados revisados; falta pulir el espaciado.
- **JET-QF5K38** · Crear estructura del repositorio — completada por @Alberto · rama `chore/bootstrap` · commit `d994833` · https://github.com/acme/equipo/pull/1
  - Resultado: Estructura lista y verificada.

## Últimos eventos

- `2026-11-23T15:44:35+00:00` · **RAMA** · @Alberto — rama main (d994833f)
- `2026-11-23T15:44:35+00:00` · **RAMA** · @Alberto — rama origin/main (d994833f)
- `2026-11-23T15:44:35+00:00` · **GIT** · @Alberto — d994833f: feat: base del proyecto local
- `2026-11-23T15:44:35.240824889+00:00` · **EQUIPO** · @Alberto — Alberto se unió al espacio de equipo
- `2026-11-23T15:44:35.269231991+00:00` · **TAREA CREADA** · @Alberto · JET-VNRKNH — creó «Pulir la bandeja de tareas» para @Alberto
- `2026-11-23T15:44:35.535758051+00:00` · **TAREA TOMADA** · @Alberto · JET-VNRKNH — tomó «Pulir la bandeja de tareas» y comenzó a trabajar
- `2026-11-23T15:44:35.676501060+00:00` · **AVANCE** · @Alberto · JET-VNRKNH — avanzó «Pulir la bandeja de tareas»: Scroll y estados revisados; falta pulir el espaciado.
- `2026-11-23T15:44:35.813754412+00:00` · **TAREA CREADA** · @Alberto · JET-52KWHJ — creó «Validar la terminal con OpenCode» para @Alberto
- `2026-11-23T15:44:35.949960719+00:00` · **TAREA CREADA** · @Alberto · JET-NURE3K — creó «Preparar la conexión con GitHub» para @Alberto
- `2026-11-23T15:44:36.088636953+00:00` · **TAREA CREADA** · @Alberto · JET-G6WKVN — creó «Preparar migración de datos» para @Carlos Ruiz
- `2026-11-23T15:44:36.227558800+00:00` · **TAREA CREADA** · @Alberto · JET-EF3EEC — creó «Revisar accesibilidad del editor» para @Beto Lima
- `2026-11-23T15:44:36.366147559+00:00` · **TAREA CREADA** · @Alberto · JET-QF5K38 — creó «Crear estructura del repositorio» para @Alberto
- `2026-11-23T15:44:36.638182423+00:00` · **TAREA TOMADA** · @Alberto · JET-QF5K38 — tomó «Crear estructura del repositorio» y comenzó a trabajar
- `2026-11-23T15:44:36.776756086+00:00` · **AVANCE** · @Alberto · JET-QF5K38 — avanzó «Crear estructura del repositorio»: Workspace y CI listos.
- `2026-11-23T15:44:36.917423086+00:00` · **COMPLETADA** · @Alberto · JET-QF5K38 — completó «Crear estructura del repositorio», rama chore/bootstrap, commit d994833, PR
- `2026-11-23T15:47:16.564578778+00:00` · **COMPLETADA** · @Alberto · JET-VNRKNH — completó «Pulir la bandeja de tareas», rama feat/bandeja, commit d994833f
- `2026-11-23T16:51:57.308383186+00:00` · **TAREA TOMADA** · @Alberto · JET-52KWHJ — tomó «Validar la terminal con OpenCode» y comenzó a trabajar

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
