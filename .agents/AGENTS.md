<!-- code-review-graph MCP tools -->
## MCP Tools: code-review-graph

**IMPORTANT: This project has a knowledge graph. ALWAYS use the
code-review-graph MCP tools BEFORE using Grep/Glob/Read to explore
the codebase.** The graph is faster, cheaper (fewer tokens), and gives
you structural context (callers, dependents, test coverage) that file
scanning cannot.

### When to use graph tools FIRST

- **Exploring code**: `semantic_search_nodes` or `query_graph` instead of Grep
- **Understanding impact**: `get_impact_radius` instead of manually tracing imports
- **Code review**: `detect_changes` + `get_review_context` instead of reading entire files
- **Finding relationships**: `query_graph` with callers_of/callees_of/imports_of/tests_for
- **Architecture questions**: `get_architecture_overview` + `list_communities`

Fall back to Grep/Glob/Read **only** when the graph doesn't cover what you need.

### Key Tools

| Tool | Use when |
| ------ | ---------- |
| `detect_changes` | Reviewing code changes — gives risk-scored analysis |
| `get_review_context` | Need source snippets for review — token-efficient |
| `get_impact_radius` | Understanding blast radius of a change |
| `get_affected_flows` | Finding which execution paths are impacted |
| `query_graph` | Tracing callers, callees, imports, tests, dependencies |
| `semantic_search_nodes` | Finding functions/classes by name or keyword |
| `get_architecture_overview` | Understanding high-level codebase structure |
| `refactor_tool` | Planning renames, finding dead code |

### Workflow

1. The graph auto-updates on file changes (via hooks).
2. Use `detect_changes` for code review.
3. Use `get_affected_flows` to understand impact.
4. Use `query_graph` pattern="tests_for" to check coverage.

## Tools — Always Use

### agent-browser
For ALL web browser interactions — opening URLs, clicking, filling forms,
taking screenshots, reading page content, running accessibility snapshots —
always use the `agent-browser` CLI. Never use Playwright, Puppeteer, or
Selenium directly. Prefer `agent-browser snapshot` for page understanding
and `agent-browser read <url>` for fetching agent-readable text.

Reference: https://github.com/vercel-labs/agent-browser

### code-review-graph
When performing code reviews, analyzing blast radius of changes, checking
which tests are affected, or navigating large codebases, always use
`code-review-graph` MCP tools or CLI commands first. It provides precise,
token-efficient context by querying the structural graph instead of reading
entire files.

Useful commands:
- `code-review-graph build` — rebuild the graph after major changes
- Use MCP tools for blast-radius analysis during reviews
- Check affected tests and dependencies before suggesting changes

Reference: https://github.com/tirth8205/code-review-graph

---

# Andrej Karpathy Guidelines

Behavioral guidelines to reduce common LLM coding mistakes. Merge with project-specific instructions as needed.

**Tradeoff:** These guidelines bias toward caution over speed. For trivial tasks, use judgment.

## 1. Think Before Coding

**Don't assume. Don't hide confusion. Surface tradeoffs.**

Before implementing:
- State your assumptions explicitly. If uncertain, ask.
- If multiple interpretations exist, present them - don't pick silently.
- If a simpler approach exists, say so. Push back when warranted.
- If something is unclear, stop. Name what's confusing. Ask.

## 2. Simplicity First

**Minimum code that solves the problem. Nothing speculative.**

- No features beyond what was asked.
- No abstractions for single-use code.
- No "flexibility" or "configurability" that wasn't requested.
- No error handling for impossible scenarios.
- If you write 200 lines and it could be 50, rewrite it.

Ask yourself: "Would a senior engineer say this is overcomplicated?" If yes, simplify.

## 3. Surgical Changes

**Touch only what you must. Clean up only your own mess.**

When editing existing code:
- Don't "improve" adjacent code, comments, or formatting.
- Don't refactor things that aren't broken.
- Match existing style, even if you'd do it differently.
- If you notice unrelated dead code, mention it - don't delete it.

When your changes create orphans:
- Remove imports/variables/functions that YOUR changes made unused.
- Don't remove pre-existing dead code unless asked.

The test: Every changed line should trace directly to the user's request.

## 4. Goal-Driven Execution

**Define success criteria. Loop until verified.**

Transform tasks into verifiable goals:
- "Add validation" → "Write tests for invalid inputs, then make them pass"
- "Fix the bug" → "Write a test that reproduces it, then make it pass"
- "Refactor X" → "Ensure tests pass before and after"

For multi-step tasks, state a brief plan:
```
1. [Step] → verify: [check]
2. [Step] → verify: [check]
3. [Step] → verify: [check]
```

Strong success criteria let you loop independently. Weak criteria ("make it work") require constant clarification.

---

**These guidelines are working if:** fewer unnecessary changes in diffs, fewer rewrites due to overcomplication, and clarifying questions come before implementation rather than after mistakes.

---

# Project Guidelines: Priston Tale Auto Tool (v2)

This section serves as the "constitution" for the coding agent. The agent MUST comply with all "Golden Rules" listed below.

## 1. Project Overview
A gameplay automation tool for **Priston Tale VTC** designed using a **vision-only** approach: it only reads screen pixels + AI, and sends simulated mouse/keyboard inputs. It **never** reads/writes game RAM, nor does it hook/inject processes. Since the game uses kernel-level anti-cheat (GameGuard), the strategy is to **evade**, not **fight**.

## 2. GATE 0 — Mandatory Before Any Other Code
Before executing any tasks in Phase 1, you must run `scripts/poc_gameguard.py` against the real game client (with GameGuard active) and confirm that:
- Screen capture (DXcam or fallback PrintWindow/BitBlt) works and is not blocked.
- Simulated inputs (pydirectinput/SendInput) successfully reach the game.
- Capture FPS ≥ 20.

The agent **must not** assume Gate 0 has passed without explicit user confirmation of manual run results. If confirmation is not yet provided, the agent must prompt the user to run the POC script before continuing with Phase 1.

## 3. GOLDEN RULES (NEVER violate — violations require a rewrite)
1. **Vision-only:** Absolutely forbid any reading/writing of RAM, DLL injection, process hooking, or any actions that interfere with or disable GameGuard. Rely strictly on pixels + simulated/hardware inputs.
2. **All captures must go through `ICaptureBackend`; all inputs must go through `IInputBackend`.** Code in `core/`, `features/`, and `vision/` MUST NEVER import `dxcam` or `pydirectinput` directly. Only modules inside `backends/` are allowed to import backend-specific libraries. -> This is crucial for swapping in future backends (Session, Interception, Arduino) without touching the core logic.
3. **Always use normalized coordinates (0.0–1.0).** Do not hardcode screen pixels. Only convert to actual screen pixels at the very last moment via `core/coordinates.py`.
4. **Config-driven:** No "magic numbers" in the code. All percentage thresholds, hotkeys, scanning areas, and action rates must reside in `config/*.json`.
5. **Combat MUST NOT have class-specific combos.** Implement only 2 generic actions: left-click (LMB) and right-click (RMB), toggleable and configurable with interval rates, shared across all 11 classes. The agent must not implement custom class combos unless explicitly requested.
6. **Licensing is based on OFFLINE digitally signed keys.** There is no online server or database. Do not implement any server-side license architecture or kill switch unless explicitly requested.
7. **Session mode (Desktop Object) is POSTPONED.** Do not implement session_manager, capture_session, input_session, or preview_window unless explicitly requested. Keep only the two interfaces (`ICaptureBackend`, `IInputBackend`) ready to be plugged in later.
8. **Fail-safe:** Upon encountering anomalous or hazardous states (death, captcha, PK/Player Kill) -> halt safely; do not make guesses.
9. **Emergency Stop (F12) must release control within <200ms**, even when the main engine loop is busy.
10. **Do not block the main loop for >100ms** without sleep or yielding execution control.

## 4. Tech Stack & Constraints
- Python 3.11, running strictly on Windows (win32gui, dxcam, pydirectinput are Windows-only).
- Runtime dependencies (packaged for clients): dxcam, opencv-python, numpy, pywin32, pydirectinput, onnxruntime, (paddleocr OR pytesseract), keyboard, requests, pynacl or cryptography (for key signature verification).
- Training-only dependencies (NOT shipped to clients, listed separately in requirements-train.txt): ultralytics, torch.
- Runtime MUST NOT contain PyTorch. Run models using onnxruntime.
- Packaging: PyInstaller (dev builds), Nuitka (release builds).
- Testing: pytest. Every module must have at least one smoke test.

## 5. Project Directory Structure (maintain this layout strictly)
```
priston_auto_tool/
├── main.py                 # entry point + FSM loop
├── config/
│   ├── settings.json        # mode="direct" ("session" placeholder for future, unused for now)
│   └── profiles/             # class profiles: HP/MP regions, LMB/RMB intervals, pot thresholds
├── core/
│   ├── state_machine.py     # FSM — unaware of the active capture/input mode
│   ├── coordinates.py       # scaled coordinates + win32gui + border offset
│   └── humanizer.py         # Bezier curves, random delay/hitbox/jitter
├── backends/                 # only this layer can import specific capture/input libraries
│   ├── capture_base.py       # ICaptureBackend.grab_frame() — KEEP and use immediately
│   ├── capture_direct.py     # DXcam / fallback PrintWindow-BitBlt
│   ├── input_base.py         # IInputBackend.move/click/key — KEEP and use immediately
│   ├── input_direct.py       # pydirectinput
│   # (session/interception/arduino: UNIMPLEMENTED, will plug in later via the above 2 interfaces)
├── vision/
│   ├── detector.py          # YOLO ONNX inference (optional — see target_source)
│   ├── tracker.py            # ByteTrack (for yolo targeting)
│   ├── ocr.py                # HP/MP reading
│   └── color_filter.py       # color filter / gemstone template matching
├── features/
│   ├── auto_pot.py
│   ├── combat.py              # GENERIC: tab-target or yolo-target + LMB/RMB from config
│   ├── auto_buff.py  loot.py  navigation.py  inventory.py  safety.py
├── remote/    notifier.py  controller.py
├── security/  license.py     # offline key verification (Ed25519), NO server communication
├── models/    monster.onnx   # (only required if target_source="yolo")
├── ui/        app.py
└── scripts/   # manual testing scripts run against the real game (NOT shipped), including poc_gameguard.py
```

## 6. Coding Conventions
- Type hints + docstrings for all public functions. Keep modules small and single-responsibility.
- Log all FSM transitions (from_state -> to_state, reason).
- Do not swallow exceptions silently; log them clearly.
- Never invoke direct/hardcoded time.sleep inside feature code — all delays must go through the humanizer.

## 7. Workflow Rules (for the Agent)
- This is a solo project assisted by an AI agent. Prioritize the shortest path to a runnable version; do not proactively expand scope.
- Work on one task at a time. Once a task is done -> run tests/verify -> stop and wait for user confirmation. DO NOT automatically start the next task.
- For tasks requiring the actual game to verify (capture, input, FPS, anti-cheat, combat), the agent MUST NOT mark the task as "done" by itself. Create a validation script in `scripts/` for the user to run manually, specifying clear pass/fail criteria.
- If the user requests something that violates section 3 (class-specific combos, server license, session backend development) without explicitly stating that they want to deviate on purpose, ask for clarification before proceeding.
- Favor small, testable increments. If the output diff grows abnormally large, stop and propose splitting the task.

## 8. Immutable Development Roadmap (Lite Path for Solo)
```
Gate 0 (POC GameGuard) -> Backend Interfaces -> Emergency Stop -> Direct Capture
-> Coordinates -> Direct Input -> Auto Pot -> Combat (tab-target first, YOLO later)
-> Simple Licensing -> Minimal UI -> (Extensions: Humanizer/Loot/Safety/YOLO/remote/packaging)
```
Do not alter this order when proposing new tasks.
