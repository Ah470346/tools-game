# Fix: Mất target giữa chừng khi đánh quái (panel-authoritative targeting)

## Context

Bot đang đánh quái A (chưa chết) thì YOLO mất detect vài giây (nhân vật che khuất khi cận chiến / detection flicker ở conf 0.40) → bot đứng khựng ("Holding fire"), rồi sau 6s (`target_give_up_sec`) **bỏ cuộc và blacklist quái A dù panel HP mục tiêu vẫn hiện** (quái còn sống), sau đó chọn quái gần **tâm màn hình** nhất → chạy sang quái B. Log `test5` chứng minh: `Target ID 71 unseen for >6.0s. Giving up` → 1.8s sau `Panel visible without lock — re-acquired target ID 76`.

Nguyên nhân gốc (đã verify trong code):
1. `features/combat.py:342-352` — give-up 6s bắn cả khi panel còn hiện → blacklist quái còn sống.
2. `vision/tracker.py:199` — tracker chỉ trả về track có `lost_count == 0`; track "coasting" bị ẩn nên re-association không dùng được; track bị xoá hẳn sau 15 frame (~1.5s) → ID cũ không bao giờ quay lại.
3. `features/combat.py:236-242` — `_select_best_target` chọn quái gần tâm màn hình, không phải gần vị trí quái cũ/xác quái.
4. Phụ: `has_target()` trả False khi "Holding fire" làm `main.py:218-221` chuyển FSM sang LOOTING giữa trận.

**Hướng giải quyết (không đổi sang phương thức aim khác):** giữ YOLO nhưng lấy **panel HP mục tiêu làm nguồn chân lý** cho trạng thái "đang giao chiến" — panel còn hiện = quái còn sống, tuyệt đối không give-up/blacklist/đổi mục tiêu. Tách "có target không" (panel quyết định) khỏi "có an toàn để click không" (độ tươi của vị trí). User đã chọn: **đánh mù có giới hạn** khi YOLO tạm mù (chi tiết §3).

## Changes

### 1. `vision/tracker.py` — expose coasting tracks (opt-in)

- `TargetTracker.__init__`: thêm param `coast_output_frames: int = 0` (0 = tắt, giữ behavior cũ cho test/script hiện có).
- Tách helper `_build_output()`: trả track `lost_count == 0` như cũ (thêm key `"coasting": False`), và nếu `coast_output_frames > 0` trả thêm track `0 < lost_count <= coast_output_frames` với `"coasting": True` (box = box cuối cùng thấy được — quái bị che khi cận chiến đứng yên cạnh nhân vật nên không cần motion model).
- Dùng `_build_output()` ở **cả 2 đường return**: return chính (dòng 196-207) và early-return `if not detections:` (dòng 89-94 — hiện trả `[]`; đây chính là ca mất detect toàn bộ do che khuất, bắt buộc phải sửa).
- Callers: chỉ `features/combat.py`, `tests/test_tracker.py`, `scripts/test_tracker_visual.py` — default 0 nên không vỡ gì.

### 2. `config/settings.json`

`combat`:
| Key | Default | Lý do |
|---|---|---|
| `blind_attack_max_sec` | 3.0 | Sau khi stale 1.5s, tiếp tục đánh vị trí cuối tối đa đến mốc 3.0s kể từ lần confirm cuối |
| `blind_attack_max_dist_ratio` | 0.15 | Chỉ đánh mù nếu vị trí cuối cách tâm màn hình ≤0.15 (quái cận chiến đứng cạnh nhân vật; click trượt xuống đất cũng chỉ nhích 1 bước) |
| `engagement_max_sec` | 45.0 | Van an toàn thay give-up cũ: giao chiến kéo dài bất thường → clear target (KHÔNG blacklist) |
| `next_target_anchor_sec` | 5.0 | Sau khi giết, vị trí xác quái là anchor chọn mục tiêu kế trong 5s |
| `target_give_up_sec` | **xoá** | Việc của nó được thay bằng panel-authority + van 45s; ca "failed lock" đã có nhánh panel-gone xử lý |

`tracker`: thêm `coast_output_frames: 15` (= `max_lost_frames`).

### 3. `features/combat.py` — thay decision ladder trong `has_target()` (nhánh YOLO, dòng 261-412)

**`__init__` (91-119):** truyền `coast_output_frames` vào `TargetTracker`; thay `_give_up_sec` bằng `_engagement_max_sec`; thêm `_blind_attack_max_sec`, `_blind_attack_max_dist`, `_next_target_anchor_sec`; state mới: `_engagement_start_time`, `_last_kill_pos`, `_last_kill_time`, `_blind_attack_active`. Helper `_lock_confirmed()` = `_panel_last_seen_time >= _last_yolo_target_time` (biểu thức đã có sẵn ở dòng 372, tái dùng).

**Ladder mới trong nhánh `panel_visible or is_grace or panel_recent`:**
```
tracked = tracker.update(detections)          # giờ có cả coasting
visible  = [t for t in tracked if not t["coasting"]]
coasting = [t for t in tracked if t["coasting"]]

1. Active ID trong `visible`         → cập nhật pos + _last_pos_confirm_time (như cũ)
2. MỚI: Active ID trong `coasting`   → cập nhật pos theo box tracker nhớ,
                                       KHÔNG refresh confirm_time (vị trí là "nhớ", không phải "thấy")
3. Re-associate (logic cũ 293-317)   → chỉ xét candidates từ `visible` (không adopt box coasting cũ)
4. Bootstrap khi chưa engaged (324-333) → _select_best_target(visible, anchor=_recent_kill_anchor());
                                          khi acquire, set _engagement_start_time

Nếu _yolo_target_pos is None → return False
since_confirm = now - _last_pos_confirm_time

Nếu _lock_confirmed():                        # PANEL LÀ CHÂN LÝ
    - KHÔNG BAO GIỜ give-up/blacklist ở đây (xoá block 342-352)
    - now - _engagement_start_time > 45s → warning, clear id+pos (KHÔNG blacklist), return False
    - since_confirm <= _stale_timeout → return True (đánh bình thường)
    - Stale: nếu panel_visible (frame hiện tại, không debounce)
             AND dist(pos, tâm) <= 0.15 AND since_confirm <= 3.0s
             → _blind_attack_active = True
    - return True dù đang hold hay blind  → FSM không nhảy sang LOOTING giữa trận
Nếu chưa confirm lock (grace window):
    - return since_confirm <= _stale_timeout  (như hiện tại)
```

**Nhánh panel-gone (366-408):** giữ nguyên "Failed to lock → blacklist" và "panel gone → kill bình thường"; bổ sung khi kill: lưu `_last_kill_pos`/`_last_kill_time`; chọn target mới bằng `_select_best_target(tracked, anchor=_recent_kill_anchor())`; khi acquire set `_engagement_start_time`.

**`_select_best_target()` (217-242):** thêm param `anchor: Optional[list] = None`; metric = khoảng cách tới `anchor or (0.5, 0.5)`; check `engage_range_ratio` vẫn đo từ tâm (giới hạn quãng chạy của nhân vật). Helper `_recent_kill_anchor()` trả `_last_kill_pos` nếu trong `next_target_anchor_sec`.

**`execute_combat_actions()` (414-452):** đổi gate stale ở dòng ~427 thành:
```python
if now - self._last_pos_confirm_time > self._stale_timeout and not self._blind_attack_active:
    return  # hold fire
```
Còn lại giữ nguyên (click qua `IInputBackend`, cooldown qua humanizer — đúng golden rules).

## Tests

### pytest (chạy được không cần game)

`tests/test_tracker.py`:
- `test_coasting_disabled_by_default` — default ctor, `update([])` trả `[]`.
- `test_coasting_returns_lost_tracks` — `coast_output_frames=5`: mất detect → track trả về với `coasting=True`, box đóng băng; detect lại → `coasting=False`, cùng ID.
- `test_coasting_window_boundary` — biến mất khỏi output sau `coast_output_frames` nhưng ID hồi sinh khi detect lại trong `max_lost_frames`.
- `test_coasting_on_empty_detections_branch` — exercise đường early-return `update([])`.

`tests/test_combat.py` (YOLO mode, dùng pattern có sẵn: inject `FakeDetector` qua ctor `detector=` ở combat.py:30, frame 100x100 tô đỏ/đen vùng `target_check.region` để giả panel, monkeypatch `time.time`):
- `test_occlusion_never_blacklists_while_panel_visible` — mù 10s, panel đỏ: không blacklist, giữ anchor, `has_target` vẫn True, không click quái thứ 2.
- `test_blind_attack_window` — pos (0.55,0.55): giữa 1.5s-3.0s stale có click vào pos cuối; quá 3.0s ngừng click, vẫn không blacklist.
- `test_blind_attack_refused_far_from_center` — anchor (0.2,0.2): không bao giờ blind-click.
- `test_reassociate_to_new_id_after_occlusion` — quái hiện lại cách 0.12 (ID mới) → adopt ID mới, đánh tiếp.
- `test_kill_picks_next_target_near_corpse` — quái chết ở (0.3,0.3), ứng viên (0.34,0.34) vs (0.52,0.52) → chọn con gần xác.
- `test_failed_lock_still_blacklists` — panel không bao giờ đỏ, hết grace → có blacklist (regression guard).
- `test_engagement_max_sec_valve` — panel đỏ 46s, detector mù → clear engagement, không blacklist.

### Manual validation (theo workflow rule — agent không tự verify với game thật)

Tạo `scripts/test_targeting_persistence.py` (mô phỏng theo `scripts/test_combat_run.py`): chạy `CombatController` thật với game, log dòng có tag `ACQUIRE / CONFIRMED / COASTING / BLIND_ATTACK / HOLD / REASSOC / KILL / NEXT_TARGET dist_to_corpse / BLACKLIST`. Tiêu chí in ra khi start:
- **PASS**: đánh quái cận chiến để sprite che ≥3s — log có COASTING/BLIND_ATTACK rồi REASSOC/CONFIRMED trên cùng trận; **0** dòng "Giving up and blacklisting" khi panel còn hiện; nhân vật không chạy sang quái khác giữa trận.
- **PASS**: sau kill, NEXT_TARGET chọn quái gần xác hơn quái gần tâm (khi có cả 2).
- **PASS**: click quái không với tới được → vẫn có "Failed to lock … Blacklisting" trong `lock_grace + panel_gone_confirm`.
- **FAIL**: bất kỳ BLACKLIST nào khi panel đang hiện, đổi target giữa trận, hoặc nhân vật đi >~1/4 màn hình vì blind click.

## Thứ tự thực hiện

1. `vision/tracker.py` coasting + tests tracker → `pytest tests/test_tracker.py`
2. `config/settings.json` keys mới
3. `features/combat.py`: `__init__`, `_select_best_target(anchor)`, helpers
4. `features/combat.py`: ladder `has_target()` + gate `execute_combat_actions()`
5. Tests combat → chạy full `pytest`
6. `scripts/test_targeting_persistence.py` → **dừng, giao user chạy với game thật**

## Rủi ro cần lưu ý

- `has_target` giờ trả True cả khi đang hold → FSM chuyển LOOTING muộn hơn (chỉ khi panel thật sự tắt) — đây là hành vi mong muốn nhưng thay đổi nhịp loot nhẹ.
- Blind click trúng đất có thể làm nhân vật nhích 1 bước — đã giới hạn bằng gate gần-tâm 0.15 + cửa sổ 3s + yêu cầu panel đỏ ở frame hiện tại.
