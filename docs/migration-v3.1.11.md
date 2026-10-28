# Chuyển bản mod Takeshi sang WZML-X v3.1.11

Nền mới là commit upstream `91f9702ce278e56e1bf3f60138f77e633573f3d4`.
Tree của commit này khớp hoàn toàn với snapshot `4ff1fa7` trong repo `mirrorz`.
Nhánh triển khai: `wzv3-takeshi`. Nhánh `wzv3` và snapshot gốc vẫn được giữ lại.

Nguồn tính năng riêng là nhánh `wzv3` tại `D:\projectt\wzml`, commit `76a5abd`.
Phần mod được đối chiếu với `44f5675`: 25 commit riêng, thay đổi trên 41 file.
Repo cũ không bị sửa và vẫn có thể tiếp tục dùng để đối chiếu hoặc chạy bản hiện tại.

## Những tính năng đã chuyển

| Nhóm | Kết quả |
| --- | --- |
| Quota | Quota ngày, quota cộng thêm, reset theo múi giờ, thông báo reset, lệnh `/quota` và `/qta` |
| VIP | Giới hạn riêng, thời hạn VIP, bật/tắt VIP, cho phép VIP còn hạn sử dụng trong PM |
| Referral | Link mời, xác minh tham gia nhóm, thưởng người mời, thống kê lượt thành công/chờ |
| Subscribe | Kiểm tra tham gia kênh, yêu cầu tham gia trước khi dùng lệnh, thưởng một lần |
| Menu | Quota/Referral trong bot settings; Quota/Invite trong user settings; quản lý quota/VIP bằng cách reply `/us` vào người dùng |
| Torrent selector | Chuyển giữa giao diện upstream và legacy; giữ cơ chế WebApp trong PM khi URL dùng HTTPS |
| Thông báo | Reaction cho task, status ảnh chuyển sang text khi dài và trở lại ảnh khi ngắn; theo dõi đúng tin nhắn mới để tránh spam |
| Tiện ích | Dùng plugin `/speedtest` của upstream; ưu tiên mirror MIUI OTA khi mirror trả HTTP thành công |
| Vận hành | Giới hạn file descriptor, cảnh báo FD, SDK transmission default 16, restart client theo nhóm và dọn session pool |

Quota được giữ chỗ sau bước kiểm tra đầu vào và trước khi tải/clone, xác nhận khi thành công và trả lại khi lỗi/hủy/thoát sớm.
Torrent giữ và trừ 2 quota; task thông thường giữ và trừ 1 quota.
Luồng task chung cũng bao phủ Telegram clone và Seedr của nền mới.
Phần giữ chỗ của torrent được kiểm tra lại khi Aria2 mới xác định được loại tải.
Các yêu cầu nhận thưởng đồng thời của cùng người dùng được tuần tự hóa để tránh cộng trùng trong một tiến trình bot.

Các khóa dữ liệu cũ được giữ: `USER_QUOTA`, các trường `VIP_*`, `REFERRAL`, `SUBSCRIBE_REWARD`.
Startup giải phóng giữ chỗ cũ; không xóa quota cộng thêm, tổng đã dùng hoặc thời hạn VIP.
Nhánh `feature/shared-user-quota` chưa được chuyển: chức năng chia sẻ quota/VIP giữa nhiều bot không nằm trong nhánh cũ đang dùng.

## Phần dùng cơ chế upstream mới

Giữ HyperDL/HyperUL, `tg_transfer.py`, uploader Telegram, quản lý client/session,
session mã hóa, memory guard, streaming, AllDebrid, Seedr và hệ thống plugin của v3.1.11.
Các commit cũ hạ/thay cơ chế truyền Telegram và sửa Docker theo image v3 không được phát lại.
Speedtest và tạo session dùng plugin tương ứng của upstream; không thêm alias `/sp`.
Script thử deploy cũ không được phát lại vì phụ thuộc cấu trúc bản cũ.

Giao diện legacy gọi chung handler chọn file của upstream, bao gồm xác thực GID/PIN và giới hạn thử PIN.
PIN hiển thị trên nút Telegram dùng cách tính mới; PIN kiểu lấy chữ số từ GID của bản cũ không còn dùng.
URL tunnel tiếp tục được cập nhật trong `BASE_URL`; URL legacy lưu riêng trong `BASE_URL_LEGACY`.
Monitor đồng bộ URL tunnel vào DB, thử lại khi DB lỗi và không ghi lặp khi URL không đổi.
Reaction đi theo hook bắt đầu/lỗi chung của task; không báo nhận task thành công trước khi resolver hoàn tất.
Plugin speedtest dùng worker thread cho ảnh share và giữ kết quả text khi gửi ảnh thất bại.

## Cấu hình riêng tại máy

Đã tạo `mirrorz/config.py` từ các giá trị literal trong config cũ, sao chép `token.pickle` và `.netrc`.
Các file này được Git bỏ qua. Không nhập hay chạy config cũ khi chuyển đổi và không kết nối MongoDB.

- `LEECH_DUMP_CHAT` của owner được ánh xạ sang `LEECH_LOG_CHAT` theo cơ chế upstream.
- `CLEAN_LOG_MSG` được bỏ qua vì không còn là cấu hình được hỗ trợ.
- Các biến `USER_QUOTA_*` và `REFERRAL_*` chỉ chỉnh qua Bot Settings và lưu tại MongoDB `settings.config`.
  Chúng không nằm trong `config.py`/`config_sample.py`; config cũ và biến môi trường không ghi đè giá trị trong DB.
  Giá trị mặc định trong class `Config` chỉ dùng lúc chưa có dữ liệu DB. Thông tin quota/VIP từng người dùng vẫn lưu trong dữ liệu user.
- `UPSTREAM_REPO = ""` để lần khởi động đầu không tải code từ fork cũ.
- `UPSTREAM_BRANCH = "wzv3-takeshi"` được chuẩn bị cho nhánh bản mod.
- Bot token và MongoDB URL được giữ theo nguồn cũ. Vì vậy, file này trỏ đến dữ liệu của bot hiện tại.

Công cụ chuyển cấu hình có thể dùng lại; mặc định chỉ xem kế hoạch và không in giá trị bí mật:

```powershell
python scripts/migrate_legacy_config.py --source D:/projectt/wzml --output D:/config-preview.py --copy-credentials
```

Thêm `--write` để tạo file. Công cụ từ chối ghi đè config hoặc credential khác nội dung đã có.

## Chạy thử và chuyển bot

Chưa chạy bot hoặc container từ bản mới. Máy thực hiện chuyển đổi không có Docker;
kiểm tra hiện tại chưa chứng minh được hoạt động tải/upload thật hoặc tính tương thích của image.

Trước khi chạy bản mới bằng cấu hình hiện có, sao lưu MongoDB và các file cấu hình/credential.
Để thử độc lập, dùng bản sao dữ liệu và bot thử riêng. Dữ liệu được phân vùng theo bot ID;
đổi bot token không tự đưa dữ liệu từ phân vùng của bot cũ sang bot thử.
Không chạy đồng thời hai bản với cùng bot token và dữ liệu đang dùng.
Startup upstream có thể chuyển đổi và ghi lại các thiết lập người dùng đã đổi tên.

Giao diện tunnel mặc định:

```bash
docker compose build
docker compose up -d
docker compose logs -f app
```

Giao diện legacy qua IP:port cần `BASE_URL_MODE = "legacy"`, đặt `BASE_URL_LEGACY`,
và dùng Compose override đã chuẩn bị:

```bash
docker compose -f docker-compose.yml -f docker-compose.legacy.yml up -d --build
```

Sau khi lưu cấu hình qua Telegram, tiếp tục dùng cùng bộ file Compose khi dừng/khởi động.
Kiểm tra trên môi trường thật: mirror/leech trực tiếp, torrent hai engine, chọn file hai giao diện,
upload bằng bot/user/helper, file lớn, hàng đợi, hủy task và restart/resume.
Đối chiếu thêm quota free/VIP, hết quota, VIP hết hạn và nhận thưởng referral/subscribe.

Để quay lại, dừng bản mới và chạy bản cũ. Nếu cần khôi phục chính xác dữ liệu trước chuyển đổi,
dùng bản sao MongoDB và cấu hình đã sao lưu trước lần chạy đầu.

## Kiểm tra tự động

Kết quả tại máy chuyển đổi: 81/81 bài kiểm tra offline đạt; lint `F,E9`, kiểm tra cú pháp Python,
YAML Compose/plugin và kiểm tra whitespace đều đạt. Đây chưa phải kiểm chứng chạy container hoặc truyền file thật.

```bash
python -m pip install -r tests/requirements.txt
python -m unittest discover -s tests -v
```

Các bài kiểm tra dùng code quota/referral thật với DB/Telegram giả lập; kiểm tra menu và status
chạy thân hàm thật, không khởi tạo bot. Các bài kiểm tra web dùng FastAPI/HTTPX trong bộ nhớ
với engine tải giả lập. Không bài nào kết nối bot hoặc MongoDB thật.

Phạm vi gồm cạnh tranh quota, giữ chỗ torrent, hoàn quota khi lỗi/hủy/thoát sớm,
reset/VIP, giữ dữ liệu cũ, chống thưởng trùng, callback/phân quyền,
chọn file và giới hạn PIN, status ảnh/text, chuyển cấu hình và không ghi đè file riêng.

## Các lần cập nhật sau

Các thay đổi chuyển tính năng hiện nằm trong working tree để kiểm tra trước khi commit.
Sau khi review, commit và đẩy nhánh bản mod lên fork của bạn. Không cần force-push nhánh snapshot cũ.
Chỉ bật lại tự cập nhật khi `UPSTREAM_REPO` trỏ tới fork chứa bản mod và `UPSTREAM_BRANCH`
trỏ tới nhánh đã đẩy thành công.

Đồng bộ thay đổi tác giả trên nhánh bản mod đã commit:

```bash
git fetch upstream wzv3
git merge upstream/wzv3
```

Nhánh mới có lịch sử thật của upstream nên các lần merge sau có tổ tiên chung để đối chiếu.
