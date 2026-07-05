# BỘ PROMPT THỰC THI CHO AGENT — Vibe Code Tool Auto Priston Tale (v2)

> Dùng kèm `CLAUDE.md` (đặt ở gốc repo). Mỗi task dưới đây là một prompt copy-paste thẳng cho coding agent.
>
> **Thay đổi so với v1:** thêm Cổng 0 (POC GameGuard) trước Giai đoạn 1; Combat không còn combo theo class (chỉ LMB/RMB phổ dụng, hỗ trợ tab-target trước YOLO); Giai đoạn 4 gọn lại dùng key ký số offline thay License server/HWID DB/kill switch; Chế độ Session chuyển hẳn xuống mục "Hoãn — chỉ tham khảo".

## Cách vibe code (vòng lặp chuẩn)
1. Bỏ `CLAUDE.md` vào gốc repo.
2. Với mỗi task: copy nguyên khối trong khung → dán cho agent.
3. Agent viết code → bạn chạy phần "Verify".
4. Đạt "Done when" → git commit ngay (checkpoint để còn rollback).
5. Chưa đạt → mô tả sai lệch, cho agent sửa. Đừng sang task mới khi task hiện tại còn đỏ.

## Ký hiệu
- 🧑‍💻 Task cần game thật + bạn kiểm tay.
- 🔬 Spike/POC — mục tiêu là tìm ra câu trả lời, không phải hoàn thiện tính năng.

---

# 🚦 CỔNG 0 — POC GAMEGUARD (làm TRƯỚC MỌI THỨ, kể cả Task 1.1)

> Priston Tale VTC dùng anti-cheat kernel-level (GameGuard). Nó có thể chặn một số API DirectX/Windows. Phải biết capture + input có sống được với GameGuard không TRƯỚC KHI viết bất kỳ dòng engine nào.

### 🔬🧑‍💻 Task 0.0 — POC capture + input với GameGuard (time-box 3–5 ngày)
```
Đây là SPIKE nghiên cứu, KHÔNG phải build engine. Viết scripts/poc_gameguard.py, chạy khi Priston Tale VTC ĐANG MỞ và GameGuard đang bật:
1) CAPTURE: thử DXcam (Desktop Duplication) chụp cửa sổ game, lưu 1 frame ra PNG. Nếu đen/lỗi, thử fallback PrintWindow và GDI BitBlt, lưu kết quả so sánh.
2) INPUT: thử pydirectinput gửi 1 chuỗi phím/chuột đơn giản (ví dụ di chuột, nhấn 1 phím) và xác nhận game phản hồi thật.
3) FPS: đo FPS capture trung bình trong 100 frame.
4) Quan sát: game/GameGuard có báo lỗi, cảnh báo, hay đá ra ngoài không khi chỉ làm 2 việc trên?
KHÔNG can thiệp/vô hiệu hóa GameGuard dưới bất kỳ hình thức nào — chỉ quan sát xem API đọc màn hình + gửi input tiêu chuẩn có hoạt động không.
In báo cáo dạng bảng: capture (Y/N + phương pháp nào), input (Y/N), FPS=?, sự cố gì. Dừng lại, chờ tôi tự đánh giá Go/No-Go.
```
**Tiêu chí Go (tôi tự đánh giá với game thật):** capture được bằng ít nhất 1 phương pháp, input được, FPS ≥ 20, không có dấu hiệu GameGuard phản ứng bất thường khi chỉ đọc màn hình/gửi input.

**Nếu No-Go:** không viết engine ở Giai đoạn 1 cho tới khi có phương án thay thế khả thi (đổi phương pháp capture, hoặc leo thang input sang Interception/Arduino HID — xem phần "Phương án dự phòng" cuối file). Nếu không phương án nào khả thi → dừng dự án ở bước này, đỡ tốn công về sau.

---

# GIAI ĐOẠN 1 — NỀN TẢNG (MVP Lite, không cần AI)

> Mục tiêu: nhanh nhất tới bản chạy được, không cần train YOLO. Dùng tab-target của game để tìm mục tiêu.

### Task 1.1 — Khởi tạo dự án
```
Khởi tạo skeleton dự án theo đúng cấu trúc thư mục trong CLAUDE.md.
- Tạo tất cả thư mục + file rỗng có docstring mô tả trách nhiệm module.
- Tạo requirements.txt (runtime deps) và requirements-train.txt (train deps) theo CLAUDE.md.
- Tạo config/settings.json với mode="direct" và các key rỗng có comment: combat, thresholds, regions.
- main.py: in log "FSM boot ok" rồi thoát.
- Cấu hình pytest + 1 test smoke kiểm main.py chạy không lỗi.
Done when: pip install -r requirements.txt sạch; python main.py in "FSM boot ok"; pytest xanh.
```

### Task 1.2 — Interface backend trừu tượng (quan trọng nhất — giữ cho tương lai)
```
Định nghĩa 2 abstract base class:
- backends/capture_base.py: class ICaptureBackend(ABC) với @abstractmethod grab_frame() -> np.ndarray (BGR).
- backends/input_base.py: class IInputBackend(ABC) với move(x,y), click(x,y,button), key(name,action) — tọa độ nhận vào là RATIO 0.0–1.0.
- Viết 1 MockCapture trả frame đen cố định + 1 MockInput ghi log lệnh, để test engine không cần game.
- Test: gọi qua interface, xác nhận mock hoạt động.
Nhắc: core/features CHỈ được phụ thuộc vào 2 interface này. Đây là chỗ cắm sau này cho Session/Interception/Arduino mà không đụng core — nên dù chưa làm các backend đó, interface phải chuẩn ngay từ đầu.
Done when: pytest xanh; có mock backend chạy được.
```

### 🧑‍💻 Task 1.3 — Direct capture
```
Cài backends/capture_direct.py: class DirectCapture(ICaptureBackend).
- Ưu tiên DXcam nếu Task 0.0 xác nhận DXcam hoạt động với GameGuard; nếu không, dùng phương pháp đã pass ở Cổng 0 (PrintWindow/BitBlt).
- grab_frame() trả BGR numpy array, crop đúng vùng cửa sổ Priston Tale (region từ core/coordinates.py).
- Tạo scripts/test_capture.py: grab 100 frame, in FPS trung bình, lưu 1 frame ra PNG.
Done when (tôi tự chạy): scripts/test_capture.py in FPS đạt mức đã xác nhận ở Cổng 0 (≥20, lý tưởng ≥60); ảnh PNG chụp đúng cửa sổ game.
```

### 🧑‍💻 Task 1.4 — Tọa độ tỷ lệ + bù viền
```
Cài core/coordinates.py:
- Dùng win32gui.GetWindowRect lấy vị trí/kích thước cửa sổ PT liên tục.
- Hàm ratio_to_screen(x_ratio, y_ratio) bù title-bar và viền, trả tọa độ màn hình thật.
- Hàm lấy region để capture crop dùng chung.
- scripts/test_coords.py: cho danh sách 5 điểm ratio, di chuột tới từng điểm để tôi mắt kiểm.
Done when (tôi tự chạy): click 5 điểm ratio cố định, sai số ≤ 3px kể cả khi tôi di/zoom cửa sổ.
```

### 🧑‍💻 Task 1.5 — Direct input
```
Cài backends/input_direct.py: class DirectInput(IInputBackend) dùng phương pháp đã pass ở Cổng 0 (pydirectinput hoặc SendInput).
- move/click nhận RATIO, tự đổi sang pixel qua core/coordinates.py.
- key(name, action='press'|'down'|'up').
- scripts/test_input.py: demo di chuyển nhân vật + bấm 1 phím để tôi xem game phản hồi.
Done when (tôi tự chạy): game nhận đúng phím/chuột thật theo script, không có cảnh báo lạ từ GameGuard.
```

### Task 1.6 — Emergency Stop / Pause
```
Cài cơ chế hotkey toàn cục dùng lib keyboard:
- F12 = KILL: nhả toàn bộ phím đang giữ + dừng gửi input ngay (<200ms), set cờ engine STOP.
- F9 = PAUSE/RESUME toggle.
- Chạy ở thread riêng, không phụ thuộc main loop có bận hay không.
Done when: pytest xác nhận F12 release <200ms; F9 toggle đúng.
```

### Task 1.7 — FSM skeleton
```
Cài core/state_machine.py: FSM tối thiểu IDLE → FARMING → LOOTING, có main loop.
- Log MỌI transition: from → to + lý do.
- FSM chỉ gọi capture/input QUA interface.
- Test bằng MockCapture/MockInput: mô phỏng chuỗi điều kiện → xác nhận đi đúng thứ tự state.
Done when: pytest xác nhận chuỗi transition đúng; log rõ ràng.
```

### 🧑‍💻 Task 1.8 — Smart Auto Pot
```
Cài features/auto_pot.py:
- Đọc màu pixel tại các mốc % trên thanh HP/MP/STM (tọa độ từ config).
- Đa ngưỡng cấu hình được (vd HP<60% potion thường; <30% potion lớn).
- Cooldown nội bộ mỗi loại thuốc.
- Input qua IInputBackend. Ngưỡng/mốc/phím từ config.
- scripts/test_pot.py để tôi chạy thử 30 phút với game thật.
Done when (tôi tự chạy): máu tụt dưới ngưỡng → bấm đúng phím thuốc, không spam, 30 phút ổn.
```

### 🧑‍💻 Task 1.9 — Combat PHỔ DỤNG (thay hoàn toàn combo theo class)
```
Cài features/combat.py — KHÔNG có combo riêng theo class, dùng chung cho mọi hệ phái:
- Đọc config combat: left_click{enabled, interval_sec}, right_click{enabled, interval_sec}, engage_range_ratio, target_source.
- target_source="tab" (làm trước, không cần AI): định kỳ nhấn phím khóa mục tiêu của game (config được, vd Tab/Space) để game tự chọn quái gần nhất.
- Khi có mục tiêu trong tầm: lặp LMB và/hoặc RMB theo interval riêng từng nút. Mọi input qua IInputBackend + humanizer (humanizer làm ở Task 2.10, tạm dùng delay đơn giản trước).
- Không có mục tiêu → trả tín hiệu cho FSM đi tìm/di chuyển.
- Không hardcode phím/nhịp — tất cả từ config, để trống chỗ cho target_source="yolo" thêm sau (chưa cần cài ở task này).
Done when (tôi tự chạy): với 1 class bất kỳ, tool tự đánh quái bằng LMB/RMB theo config qua tab-target, chuyển mục tiêu khi hết quái.
```

### 🧑‍💻 Task 1.10 — Ghép nối MVP Lite + soak test
```
Nối auto_pot + combat (tab-target) + FSM thành main.py chạy được ở Direct Control.
- Thêm log thống kê: số lần đánh, số lần pot, uptime.
- scripts/soak_run.py để tôi chạy 2–3 giờ.
Done when (tôi tự chạy): chạy 2h không crash, không kẹt state; log thống kê hợp lý.
```

> **🚦 Gate 1:** MVP Lite ổn ở Direct Control (tab-target + LMB/RMB + Auto Pot) + Emergency Stop hoạt động → commit tag `v0.1-mvp-lite`. Đây đã là bản có thể dùng thử nội bộ, KHÔNG cần đợi AI.

---

# GIAI ĐOẠN 2 — THÔNG MINH HÓA (tùy chọn, làm sau khi có MVP Lite chạy ổn)

> Mục tiêu: thêm target_source="yolo" để nhắm mượt hơn tab-target, cộng loot/humanizer/OCR. Có thể làm từng phần, không bắt buộc làm hết trước khi bán bản Lite.

### 🧑‍💻 Task 2.1 — Script hỗ trợ thu thập dataset
```
Cài scripts/collect_dataset.py: chụp frame game định kỳ (dùng DirectCapture), lưu ra data/raw/ với timestamp. Hotkey bật/tắt chụp.
Done when (tôi tự chạy): thu được ảnh in-game đa dạng map/ánh sáng vào data/raw/.
```

### 🧑‍💻 Task 2.2 & 2.3 — Gán nhãn + Train (việc thủ công của tôi trên Roboflow)
```
Tạo scripts/train_yolo.py dùng ultralytics: nhận dataset YOLO đã export từ Roboflow, train YOLO Nano, lưu best.pt, in mAP@0.5.
Done when (tôi tự chạy): train ra best.pt với mAP@0.5 ≥ 0.85.
```

### Task 2.4 — Export ONNX + validate
```
Cài scripts/export_onnx.py (best.pt → models/monster.onnx) và scripts/validate_onnx.py (so mAP .pt vs .onnx, lệch < 1%).
Done when: monster.onnx tạo ra; validate báo lệch < 1%.
```

### Task 2.5 — Detector + nối vào combat làm target_source="yolo"
```
Cài vision/detector.py: load models/monster.onnx bằng onnxruntime, detect(frame) -> list[Detection(class,x_ratio,y_ratio,w,h,conf)]. Fallback CPU nếu không GPU.
Thêm nhánh target_source="yolo" trong features/combat.py: dùng detection gần nhất làm mục tiêu thay vì tab-target. Giữ nguyên logic LMB/RMB, chỉ đổi cách tìm mục tiêu.
Done when (tôi kiểm): box vẽ đúng lên ảnh mẫu; combat chuyển sang yolo-target khi bật config, vẫn dùng chung logic phổ dụng.
```

### Task 2.6 — Delta detection (tối ưu CPU)
```
Thêm cơ chế: so sánh frame liên tiếp, chỉ chạy detector khi frame đổi đáng kể.
Done when: màn hình đứng yên → detector không chạy; quái mới vào vẫn bắt được.
```

### Task 2.7 — Tracker (ByteTrack)
```
Cài vision/tracker.py: bọc ByteTrack để bám mục tiêu ổn định qua nhiều frame khi dùng yolo-target.
Done when (tôi kiểm): bám 1 quái di chuyển 10s không đổi ID.
```

### 🧑‍💻 Task 2.8 — OCR đọc HP/MP
```
Cài vision/ocr.py: đọc "x/y" ở vùng HP/MP. Nối vào auto_pot: ưu tiên OCR, fallback quét màu nếu OCR fail.
Done when (tôi tự chạy): đọc đúng "x/y" ≥ 98% trên 100 mẫu.
```

### 🧑‍💻 Task 2.9 — Smart Loot Filter
```
Cài features/loot.py + vision/color_filter.py: lọc màu chữ item hiếm + template ngọc, whitelist/blacklist từ config.
Done when (tôi tự chạy): 50 lượt rơi thử → nhặt đúng đồ hiếm, bỏ rác.
```

### 🧑‍💻 Task 2.10 — Humanizer
```
Cài core/humanizer.py: Bezier mouse movement, random delay, random hitbox ±px, jitter. Cho input_direct và combat dùng qua nó thay delay cứng.
Done when (tôi kiểm): quỹ đạo/độ trễ ngẫu nhiên, không còn pattern đều.
```

### 🧑‍💻 Task 2.11 — Benchmark CPU-only
```
Cài scripts/benchmark.py: chạy pipeline (capture→[tab hoặc yolo]→combat) trong N giây, in FPS + %CPU. Chạy trên máy KHÔNG GPU.
Done when (tôi tự chạy): đạt ≥ 20 FPS trên CPU-only kể cả khi bật yolo-target.
```

> **🚦 Gate 2:** yolo-target mượt hơn tab-target, nhặt chọn lọc, ≥20 FPS CPU-only → tag `v0.2-ai`.

---

# GIAI ĐOẠN 3 — TỰ ĐỘNG HÓA TOÀN DIỆN (Session KHÔNG nằm ở đây — xem mục Hoãn cuối file)

### 🧑‍💻 Task 3.1 — Auto Buff / Aura
```
Cài features/auto_buff.py: đếm giờ từng buff (config), tái buff trước khi hết ~5s, verify icon buff trên thanh trạng thái.
Done when (tôi tự chạy): test 1h, buff tái đúng chu kỳ, có verify icon.
```

### 🧑‍💻 Task 3.2 — Auto Town & Return Cycle
```
Cài features/navigation.py (v1): Return Scroll → bán rác → mua potion → sửa đồ → Bookmark quay lại map. Điểm click/NPC từ config.
Done when (tôi tự chạy): chạy trọn chu trình và quay lại đúng map ≥ 5 lần liên tiếp.
```

### 🧑‍💻 Task 3.3 — Waypoint/Pathing + Zone Clear
```
Bổ sung navigation: record/replay tuyến farm, kiểm minimap; hết quái trong khoảng thời gian → nhảy cụm/màn mới.
Done when (tôi tự chạy): đi đúng tuyến; hết quái tự chuyển cụm.
```

### Task 3.4 — Inventory Management
```
Cài features/inventory.py: quét lưới ô túi, đếm ô trống (region từ config); đầy → tín hiệu FSM RETURN_TOWN.
Done when (tôi kiểm): đếm đúng ô trống ≥ 98% trên ảnh mẫu.
```

### 🧑‍💻 Task 3.5 — Safety đầy đủ
```
Cài features/safety.py + nối FSM (EMERGENCY/ANTI_STUCK):
- Death Detection, PK/PVP Alert, Captcha/GM-popup Detection (dừng ngay + báo động khẩn), Anti-Stuck.
Done when (tôi tự chạy): giả lập từng ca → tool dừng an toàn + báo động đúng.
```

### 🧑‍💻 Task 3.6 — Soak test 24/7
```
Cài scripts/soak_24h.py: chạy full pipeline liên tục, log định kỳ (uptime, số lần đánh/pot, sự kiện safety), tự chụp ảnh khi có sự kiện lạ.
Done when (tôi tự chạy): 24h × 3 ngày không crash, không kẹt, không bị ban (tài khoản thử nghiệm).
```

> **🚦 Gate 3:** Treo 24/7 ổn định ở Direct Control → tag `v0.3-auto`.

---

# GIAI ĐOẠN 4 — THƯƠNG MẠI HÓA (gọn lại: key ký số offline)

### Task 4.1 — License key ký số offline (thay cho License server/HWID DB/kill switch)
```
Cài security/license.py cơ chế key OFFLINE:
- Định dạng key = payload {customer_id, expire_date, hwid?} + chữ ký Ed25519 (dùng pynacl hoặc cryptography). Tool nhúng public key để verify, không gọi server.
- Lúc khởi động: verify chữ ký + kiểm hết hạn + (nếu có hwid) so với HWID máy hiện tại (đọc từ volume serial + CPU id, hoặc tương đương ổn định).
- Sai/hết hạn/lệch HWID → chặn chạy, báo rõ lý do.
- Viết scripts/gen_key.py (dùng private key của tôi, chạy trên máy tôi, KHÔNG ship cho khách) để cấp key mới.
Done when: key hợp lệ cho chạy; key sai/hết hạn/lệch HWID bị chặn; gen_key.py cấp được key hoạt động.
```

### Task 4.2 — UI cấu hình tối thiểu
```
Cài ui/app.py (PySide6/PyQt hoặc Tkinter):
- Chọn class đang chơi (để set vùng HP/MP mặc định), bật/tắt + đặt nhịp LMB/RMB, ngưỡng pot, chọn target_source (tab/yolo nếu có), nhập key license.
- Nút Start/Stop; hiển thị trạng thái + thống kê cơ bản.
Done when (tôi kiểm): đổi cấu hình qua UI và chạy được, không đụng code.
```

### 🧑‍💻 Task 4.3 — Remote Notify/Control
```
Cài remote/notifier.py + remote/controller.py (Telegram/Discord bot):
- Notify: chết, đầy đồ, nhặt đồ hiếm, gặp captcha/GM — kèm ảnh chụp màn hình.
- Control: lệnh pause/resume/stop từ điện thoại.
Done when (tôi tự chạy): nhận thông báo kèm ảnh; điều khiển từ xa được.
```

### 🧑‍💻 Task 4.4 — Đóng gói Nuitka .exe 1-click
```
Cấu hình build Nuitka → 1 file .exe, không cần khách cài Python. Gộp onnxruntime + model (nếu dùng yolo) + config.
Done when (tôi tự chạy): copy .exe sang máy sạch (không Python) → bật chạy được.
```

### 🧑‍💻 Task 4.5 — Closed Beta
```
Thêm log/telemetry tối thiểu để thu feedback + phát hiện lỗi/ban trong beta (opt-in, ẩn danh). Chuẩn bị checklist onboarding cho vài chục khách beta đầu tiên.
Done when (tôi tự chạy): 2 tuần beta, tỉ lệ ban = 0, sửa hết lỗi P0/P1.
```

### Task 4.6 — Tài liệu + onboarding
```
Viết docs/: cài đặt, cấu hình, chọn target_source, xử lý sự cố (FAQ), cảnh báo an toàn + điều khoản tự chịu rủi ro.
Done when: người mới tự cài & chạy theo tài liệu, không cần hỏi.
```

> **🚦 Gate 4:** `.exe` bán được, có key license, qua closed beta không ban → release `v1.0`.

---

# ⏸️ HOÃN — CHẾ ĐỘ SESSION (chỉ tham khảo, KHÔNG làm bây giờ)

> Không viết các task dưới đây trừ khi có quyết định rõ ràng mở lại. Giữ nguyên vì 2 lý do: (1) GameGuard kernel-level nhiều khả năng từ chối chạy trong Desktop Object lạ; (2) đầu tư nặng cho một tính năng rủi ro cao trong khi MVP Lite còn chưa ra mắt là đúng kiểu Rủi ro #3 (scope creep) đã cảnh báo.

Nếu tương lai muốn mở lại: điều kiện tiên quyết là chạy lại một POC Session riêng (tương tự Cổng 0 nhưng thử tạo Desktop Object + launch game trong đó) và PASS trước khi viết bất kỳ dòng nào của session_manager/capture_session/input_session/preview_window. Vì Task 1.2 đã tách interface sạch, việc cắm 2 backend mới này sau này không đụng tới core/features hiện có.

---

# PHƯƠNG ÁN DỰ PHÒNG (dùng khi Cổng 0 No-Go)

- **Capture bị GameGuard chặn:** thử PrintWindow / GDI BitBlt / chụp full-screen thô thay Desktop Duplication.
- **Input bị gắn cờ là giả lập:** leo thang theo thứ tự pydirectinput → Interception driver → Arduino Leonardo (HID phần cứng, input thật ở tầng USB).
- **Cả hai đều fail:** dự án không khả thi ở dạng phần mềm thuần với anti-cheat hiện tại — dừng đúng lúc thay vì tiếp tục đầu tư.

---

## Lưu ý cuối khi vibe code
- Task 🧑‍💻 là chỗ vibe code hay "tự tin ảo" — agent không thấy được game, bạn phải tự chạy và mắt kiểm.
- Commit sau mỗi task xanh để còn rollback.
- Giữ kỷ luật interface (Luật vàng #2 trong CLAUDE.md). Nếu agent `import pydirectinput` trong `features/`/`core/` → bắt sửa ngay.
- Cổng 0 là cổng thật đầu tiên — làm trước cả Task 1.1 nếu bạn muốn tuyệt đối an toàn, hoặc song song với 1.1 (vì 1.1 chỉ tạo skeleton, không đụng game).
