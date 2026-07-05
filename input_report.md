# Kết Quả Thử Nghiệm Hệ Thống Direct Input (Direct Control Mode)

Tài liệu này tổng hợp chi tiết kết quả thử nghiệm và kiểm thử hệ thống giả lập chuột/bàn phím tương thích với cơ chế bảo mật của GameGuard trên Priston Tale VTC.

---

## 📊 Kết Quả Chạy Thử Nghiệm Thực Tế (Direct Input Test)

Kiểm thử giả lập đầu vào được chạy thành công trên máy khách (client) thực tế chạy hệ điều hành Windows với quyền Administrator và game client Priston Tale đang mở ở chế độ cửa sổ (Windowed Mode).

### Các bước kiểm thử và Trạng thái ghi nhận:
1. **Bước 1: Di chuyển chuột tới trung tâm cửa sổ game (0.5, 0.5)**
   - *Kết quả:* **[PASS]** Con trỏ chuột di chuyển mượt mà và dừng lại chính xác tại tâm của khu vực vẽ game (Client Area), ngay trên nhân vật đứng ở trung tâm màn hình.
2. **Bước 2: Click chuột trái tại tâm (0.5, 0.5)**
   - *Kết quả:* **[PASS]** Tín hiệu click chuột trái được gửi thành công, game nhận tiêu điểm (focus) và kích hoạt tương tác thành công.
3. **Bước 3: Nhấn phím nóng 'v' (Mở/Tắt hành trang)**
   - *Kết quả:* **[PASS]** Cửa sổ Hành trang (Inventory) của nhân vật được bật lên và tắt đi ngay lập tức, xác nhận truyền tín hiệu bàn phím thành công qua GameGuard.
4. **Bước 4: Nhấn phím nóng '1' (Sử dụng kỹ năng/bình dược nhanh)**
   - *Kết quả:* **[PASS]** Tín hiệu phím được gửi thành công (nhân vật sẽ dùng bình dược hoặc xuất kỹ năng nếu có gán vào ô số 1).
5. **Bước 5: Nhấp chuột phải ở khu vực góc dưới (0.5, 0.7)**
   - *Kết quả:* **[PASS]** Chuột di chuyển chuẩn xác từ trung tâm thẳng xuống vùng bên dưới và thực hiện nhấp chuột phải thành công.

---

## 🛠️ Các Lỗi Hệ Thống Đã Được Khắc Phục

Trong quá trình chạy kiểm thử, hệ thống đã gặp và giải quyết triệt để 2 vấn đề lớn:

### 1. Khắc Phục Lệch Tọa Độ Di Chuyển Chuột (Mouse Drift/Offset)
* **Nguyên nhân:** Thư viện `pydirectinput.moveTo` sử dụng API `SendInput` với tham số tọa độ tuyệt đối `MOUSEEVENTF_ABSOLUTE`. API này yêu cầu chuẩn hóa tọa độ (0-65535) dựa trên độ phân giải màn hình. Khi chạy dưới môi trường có DPI scaling (Windows Display Scale) hoặc trong các cấu hình ảo hóa của GameGuard, tọa độ chuẩn hóa bị tính toán sai lệch khiến chuột nhảy sang bên trái và đi lệch hướng.
* **Giải pháp:** 
  - Chuyển sang sử dụng trực tiếp hàm API Windows `ctypes.windll.user32.SetCursorPos(screen_x, screen_y)` để di chuyển chuột tuyệt đối theo tọa độ pixel thực tế đã được hiệu chỉnh góc viền (đã được chứng minh chạy chính xác 100% ở Task 1.4).
  - Tách biệt hành động nhấp chuột (`click`): Sử dụng `SetCursorPos` để dịch chuyển trước, sau đó gọi `pydirectinput.mouseDown/mouseUp` không truyền tham số tọa độ (để nhấn nút chuột ngay tại vị trí con trỏ hiện thời).
  - Kết quả là chuột di chuyển và click cực kỳ chính xác, không còn bị lệch tọa độ.

### 2. Thay Thế Phím Kiểm Thử Bàn Phím Phù Hợp Với Game
* **Nguyên nhân:** Kịch bản ban đầu kiểm tra phím `Spacebar` (Space) với kỳ vọng nhân vật sẽ thực hiện hành động nhảy. Tuy nhiên, game Priston Tale không hỗ trợ tính năng nhảy của nhân vật, gây nhầm lẫn trong quá trình đánh giá.
* **Giải pháp:** Thay thế phím kiểm tra sang phím `v` (Phím tắt mở/tắt bảng Hành trang mặc định của Priston Tale). Đây là hành động có hiệu ứng hiển thị trực quan và dễ xác thực nhất.

---

## 📐 Thông Tin Các Mô-đun Hệ Thống

Các tệp mã nguồn tham gia cấu thành tính năng:
- **Lớp xử lý Input:** [backends/input_direct.py](file:///d:/tool1/tools-game/backends/input_direct.py)
- **Tập lệnh kiểm thử:** [scripts/test_input.py](file:///d:/tool1/tools-game/scripts/test_input.py)
- **Bộ Unit Tests:** [tests/test_input_direct.py](file:///d:/tool1/tools-game/tests/test_input_direct.py)

Tất cả các ca kiểm thử tự động (Unit Tests) đều đã vượt qua thành công:
```powershell
============================== 8 passed in 0.32s ==============================
```

---

## 📈 Kết Luận & Đánh Giá
- **Trạng thái kiểm thử:** **[PASS]**
- **Hiệu năng & Độ ổn định:** Giả lập chuột và bàn phím hoạt động ổn định, chính xác dưới lớp bảo vệ của GameGuard, không bị khóa hay văng ứng dụng.
- **Tiến trình dự án:** Đạt chuẩn đầu ra cho Gate 0 & Phase 1. Sẵn sàng tích hợp sang phát triển các tính năng tự động nâng cao (Auto Pot, Combat).

---
*(Báo cáo được cập nhật vào ngày 2026-07-05)*
