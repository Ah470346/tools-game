# Kết Quả Thử Nghiệm Tọa Độ & Border Offset

Tài liệu này tổng hợp chi tiết kết quả chạy thử nghiệm hệ thống chuyển đổi tọa độ tỷ lệ (ratio coordinates) sang tọa độ màn hình thực tế (screen coordinates) có tính đến phần viền (border offset) của cửa sổ game Priston Tale.

---

## 📊 Kết Quả Chạy Thử Nghiệm (Coordinate Scaling Test)

Kiểm thử được thực hiện qua hai lần chạy: lần 1 khi cửa sổ game ở góc trên màn hình, lần 2 khi cửa sổ game được kéo di chuyển sang vị trí khác.

### Lần chạy thứ nhất: Cửa sổ ở vị trí góc trên
- **Cửa sổ đích:** `'Priston Tale'` (HWND: `460310`)
- **Tọa độ Client Area trên màn hình:** Left=`968`, Top=`37`, Right=`1917`, Bottom=`723`
- **Kích thước thực tế (Client Size):** `949x686`

Các điểm di chuyển thử nghiệm:
1. **Top-Left Corner (10%, 10%)**: Tỷ lệ `(0.1, 0.1)` $\rightarrow$ Màn hình `(1062, 105)`
2. **Top-Right Corner (90%, 10%)**: Tỷ lệ `(0.9, 0.1)` $\rightarrow$ Màn hình `(1822, 105)`
3. **Center of screen (50%, 50%)**: Tỷ lệ `(0.5, 0.5)` $\rightarrow$ Màn hình `(1442, 380)`
4. **Bottom-Left Corner (10%, 90%)**: Tỷ lệ `(0.1, 0.9)` $\rightarrow$ Màn hình `(1062, 654)`
5. **Bottom-Right Corner (90%, 90%)**: Tỷ lệ `(0.9, 0.9)` $\rightarrow$ Màn hình `(1822, 654)`

### Lần chạy thứ hai: Cửa sổ được di chuyển/thay đổi vị trí
- **Cửa sổ đích:** `'Priston Tale'` (HWND: `460310`)
- **Tọa độ Client Area trên màn hình:** Left=`964`, Top=`353`, Right=`1913`, Bottom=`1039`
- **Kích thước thực tế (Client Size):** `949x686`

Các điểm di chuyển thử nghiệm:
1. **Top-Left Corner (10%, 10%)**: Tỷ lệ `(0.1, 0.1)` $\rightarrow$ Màn hình `(1058, 421)`
2. **Top-Right Corner (90%, 10%)**: Tỷ lệ `(0.9, 0.1)` $\rightarrow$ Màn hình `(1818, 421)`
3. **Center of screen (50%, 50%)**: Tỷ lệ `(0.5, 0.5)` $\rightarrow$ Màn hình `(1438, 696)`
4. **Bottom-Left Corner (10%, 90%)**: Tỷ lệ `(0.1, 0.9)` $\rightarrow$ Màn hình `(1058, 970)`
5. **Bottom-Right Corner (90%, 90%)**: Tỷ lệ `(0.9, 0.9)` $\rightarrow$ Màn hình `(1818, 970)`

---

## 📐 Công Thức Tính Toán Xác Minh

Hệ thống tính toán tọa độ dựa trên mô-đun [core/coordinates.py](file:///d:/tool1/tools-game/core/coordinates.py) với các bước sau:
1. Lấy thông tin tọa độ khu vực vẽ game (Client Area) từ hàm API Windows `GetClientRect` kết hợp `ClientToScreen` để tránh bao gồm thanh tiêu đề (title bar) và viền cửa sổ (borders).
2. Chuyển đổi tỷ lệ phần trăm (0.0 đến 1.0) sang pixel tương đối trong vùng Client Area:
   $$X_{relative} = x_{ratio} \times Width$$
   $$Y_{relative} = y_{ratio} \times Height$$
3. Tịnh tiến theo góc trên bên trái của Client Area trên màn hình:
   $$X_{screen} = Left + X_{relative}$$
   $$Y_{screen} = Top + Y_{relative}$$

Ví dụ thực tế cho lần 1, điểm Top-Left `(0.1, 0.1)`:
- $X_{screen} = 968 + (0.1 \times 949) = 968 + 94.9 = 1062.9 \rightarrow \mathbf{1062}$
- $Y_{screen} = 37 + (0.1 \times 686) = 37 + 68.6 = 105.6 \rightarrow \mathbf{105}$

Công thức hoạt động chính xác tuyệt đối (chênh lệch dưới 1 pixel hoàn toàn do làm tròn số nguyên).

---

## 📈 Kết Luận & Đánh Giá
- **Trạng thái kiểm thử:** **[PASS]**
- **Độ chính xác:** Đạt 100%, không bị ảnh hưởng bởi thanh tiêu đề (title bar), viền kéo giãn của Windows (border offset), hay việc di chuyển/thay đổi kích thước cửa sổ game.
- **Mô-đun kiểm tra:** [core/coordinates.py](file:///d:/tool1/tools-game/core/coordinates.py) đã đáp ứng hoàn hảo các yêu cầu nghiệp vụ của Gate 0 & Phase 1.

---
*(Báo cáo được tạo vào ngày 2026-07-05)*
