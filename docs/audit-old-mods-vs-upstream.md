# Rà soát phần mod cũ so với upstream v3.1.11

So sánh nhánh cũ `wzv3` tại `76a5abd` với nền trước mod `44f5675`, rồi đối chiếu
với upstream nguyên bản `91f9702`. Phạm vi gồm đủ 25 commit riêng và 41 file có delta cuối cùng.
Các nhận định về upstream dùng code nguyên bản trong Git, tránh nhầm phần vừa chuyển là tính năng tác giả đã có.
Nhánh đang sửa hiện tại là `wzv3-takeshi`.

Đây là đối chiếu code và luồng xử lý. Chưa benchmark hoặc chạy truyền file thật trong container;
không kết luận bản mới nhanh hơn hay hết lỗi vận hành chỉ dựa trên số phiên bản.

## Các chỉnh sửa đã làm theo yêu cầu mới

- Bỏ alias `/sp`; manifest speedtest trở lại cấu hình của upstream: `/speedtest`, alias `/spt`.
- Bỏ các biến `USER_QUOTA_*`, `REFERRAL_*` khỏi `config_sample.py` và không sinh chúng vào `config.py`.
  Bộ đọc config và env bỏ qua các biến này; snapshot deploy cũng loại chúng để không ghi đè thiết lập trong DB.
- Các giá trị vẫn có mặc định trong class runtime `Config`, được tải từ MongoDB `settings.config`
  và chỉnh/lưu qua menu Bot Settings. Dữ liệu quota/VIP/referral từng người dùng tiếp tục ở dữ liệu user.
- Đổi tên nhánh và các tham chiếu cấu hình/tài liệu sang `wzv3-takeshi`.
  Không có thao tác ghi vào DB thật trong lần sửa này.
- Đã xử lý các phần còn thiếu về client, tunnel và reaction theo cấu trúc upstream mới;
  bổ sung sửa gửi status theo topic và tránh chặn event loop trong plugin speedtest.

Kiểm tra sau thay đổi: **81/81 bài kiểm tra offline đạt**, lint `F,E9` và kiểm tra cú pháp đạt.
Đã xác nhận config mẫu/config riêng không có biến quota/referral, manifest speedtest khớp upstream,
và giá trị DB không bị file config hoặc env ghi đè. Chưa chạy bot/container thật.

## Kết quả theo từng nhóm chức năng

| Nhóm | Phần mod cũ | Upstream mới và quyết định |
| --- | --- | --- |
| A1 | Quota ngày, quota cộng thêm, VIP, referral, subscribe reward, reset notice | Upstream nguyên bản chưa có hệ thống tương đương. Giữ phần mod; cấu hình chỉ lưu DB. Giới hạn số task đồng thời của upstream không thay thế được quota ngày/VIP. |
| A2 | Giữ/trừ/hoàn quota theo vòng đời task; dọn pending sau restart; cảnh báo FD | Vòng đời task có thêm luồng mới nhưng chưa có quota. Giữ các hook theo API mới. Memory guard của tác giả quản lý RAM/cache, không thay thế giám sát số FD. |
| A3 | Giảm `max_concurrent_transmissions` từ 100 xuống 16; restart client theo nhóm 3 | Upstream nguyên bản vẫn đặt 100 và restart helper song song. Bản Takeshi hiện giữ default SDK 16, tôn trọng override của caller, restart theo nhóm 3 cho cả stream client, tránh restart trùng và vẫn dọn UserSessionPool. HyperDL/HyperUL mới được giữ. |
| A4 | Thêm biến quota/selector; fallback `wz_bin` sang binary hệ thống | Giữ biến runtime cho quota/selector. Không mang fallback binary cũ sang: nền mới dùng image `wzadv`, `BinConfig` và bộ cài binary tương ứng. Chưa build image tại máy này nên chưa xác nhận môi trường thực tế. |
| A5 | Đăng ký `/quota`, `/us`, blacklist và `/sp` | Giữ quota, cách mở user settings và blacklist của bản mod. Bỏ phần `/sp`; dùng plugin speedtest upstream. Hệ thống lệnh/plugin mới vẫn được giữ. |
| A6 | Menu quota/VIP/referral; sửa Reset User Session String | Upstream có nhiều menu/giới hạn và user session mới, nhưng không có menu quota của bạn. Giữ phần menu riêng. Điều kiện Reset của upstream vẫn chặn biến protected `USER_SESSION_STRING`, nên bản sửa nút Reset này còn cần. |
| A7 | Cho VIP dùng PM; yêu cầu tham gia kênh, thưởng subscribe | Upstream có auth và force-sub thông thường, chưa có chính sách VIP/thưởng của bạn. Giữ phần mở rộng, đồng thời giữ cách lấy người bấm callback và chat context của upstream mới. |
| A8 | Nội dung `/start`, nút Channel/Groups, thông báo reward | Đây là tùy biến sản phẩm của bạn, không phải bản sửa kỹ thuật được upstream thay thế. Giữ nội dung và xử lý referral. |
| A9 | Reaction nhận task/lỗi trong mirror, clone, yt-dlp; giữ thông báo kiểm tra task | Upstream chưa có reaction task tương đương. Bản Takeshi dùng hook bắt đầu/lỗi chung của TaskListener, bổ sung lỗi chuẩn bị nguồn và chỉ dùng API `Message.react()` của wzgram. Không gửi dấu nhận task thành công trước bước resolver. |
| A10 | Status ảnh dài chuyển text, ngắn trở lại ảnh; sửa theo dõi message tránh spam | Upstream đã đổi API gửi/sửa tin sang `ReplyParameters` và `LinkPreviewOptions`, nhưng status vẫn gọi edit với ảnh và cập nhật tham chiếu message cũ. Phần chuyển ảnh/text và theo dõi message mới của bạn vẫn cần, phải dùng API gửi tin hiện tại. |
| A11 | Thay HyperDL, bỏ HyperUP/transfer chung, đổi uploader và fallback Telegram | Upstream đã phát triển lại transfer chung, HyperDL/HyperUL, client bot/user/helper, pool session, cancel và quản lý buffer/RAM. Giữ toàn bộ cụm mới; không phát lại những commit xóa `tg_transfer.py` hoặc ép engine cũ. Chưa có benchmark để khẳng định hiệu năng tốt hơn trên máy của bạn. |
| A12 | Hai chế độ chọn torrent; giao diện legacy và route API riêng | Upstream có UI mới và nút WebApp trong PM, nhưng không có toggle hai giao diện. Giữ toggle/legacy nếu bạn vẫn muốn dùng UI cũ. Cho cả hai dùng handler/PIN/giới hạn thử PIN của upstream; không cần duy trì bản sao backend cũ. |
| A13 | Đổi link MIUI `bigota.d.miui.com` sang `bn.d.miui.com` khi mirror truy cập được | Không có bản sửa tương đương trong upstream đã kiểm tra. Giữ helper, kiểm tra HTTP và fallback về link gốc. Chưa xác minh host bên ngoài hiện hoạt động ở môi trường chạy bot. |
| A14 | Luôn theo dõi URL tunnel và lưu URL mới vào DB | Upstream cập nhật runtime; bản Takeshi bổ sung ghi URL vào DB, chỉ ghi khi cần, thử lại sau lỗi/DB reconnect và bảo đảm monitor không khởi chạy trùng. URL legacy không bị sửa. |
| A15 | Module speedtest riêng: format ngắn, bắt lỗi, ảnh kết quả và `/sp` | Dùng plugin `/speedtest`, không thêm `/sp`. Bổ sung `sync_to_async()` cho `results.share()` và fallback sửa tin kết quả dạng text nếu helper gửi ảnh trả lỗi/None; không xóa tin trạng thái khi chưa gửi được kết quả. |
| A16 | Cài lại apt packages/venv/PATH trong Docker; nofile; mở cổng trực tiếp | Bỏ workaround Docker dành cho image v3 cũ. Giữ nofile; cổng legacy dùng Compose override. Giữ restart policy upstream cho các ví dụ thay vì mang các chỉnh sửa test `restart: no` sang. |
| A17 | Nhãn phiên bản riêng v3.1.7-* | Giữ phiên bản nền v3.1.11-x để phù hợp plugin/API hiện tại; nhánh Git phân biệt bản Takeshi. Không mang số phiên bản nền cũ sang. |
| A18 | Script tạo user session riêng | Upstream có plugin `/exportsession`, thêm session mã hóa, passphrase, TTL và dọn pool. Với luồng tạo session qua bot, dùng cơ chế mới. CLI riêng chỉ còn cần nếu bạn muốn tạo session ngoài bot. |
| A19 | Script áp dụng chế độ deploy-test | Script cũ ghi lại Dockerfile/fallback theo image v3. Không dùng trên nền mới. Hướng dẫn chuyển đổi và bộ kiểm tra hiện tại phục vụ việc thử bản mới; chúng không thay thế được kiểm tra container thật. |

## Cách đã xử lý các điểm còn thiếu

**1. Giới hạn truyền và restart client.**
Giữ giới hạn mặc định 16 cho truyền qua SDK, cho phép caller truyền giới hạn riêng.
Restart tối đa 3 client cùng lúc, bao gồm bot, user, helper và stream; cùng một client có trong nhiều danh sách chỉ restart một lần.
Một client lỗi không ngăn các client còn lại được xử lý; kết quả lỗi được báo sau cùng.
UserSessionPool luôn được dọn trong `finally`, kể cả khi restart lỗi/hủy.
Giao diện restart báo thất bại thay vì để người dùng hiểu rằng đã hoàn tất.
Cơ chế transfer/pipeline/session mới của tác giả không bị thay bằng engine cũ.

**2. Đồng bộ URL tunnel.**
Một hàm chung cập nhật runtime và ghi `BASE_URL` vào DB khi kết nối đã sẵn sàng.
Lỗi DB không ngăn runtime nhận URL mới; vòng monitor sẽ thử lại, kể cả khi URL runtime không còn thay đổi.
Sau khi ghi thành công, các lần poll cùng URL không ghi lặp. Lock tuần tự hóa cập nhật; monitor có kiểm tra để không khởi chạy trùng.
Không sửa `BASE_URL_LEGACY` và không dùng URL rỗng để xóa URL đang hoạt động.

**3. Reaction theo vòng đời task.**
Dấu nhận task thành công gửi một lần khi engine đăng ký bắt đầu task/hàng đợi thông qua `on_download_start()`.
Lỗi download/upload đổi sang reaction lỗi; callback bắt đầu đến muộn không ghi đè trạng thái lỗi.
Lỗi chuẩn bị link/file, AllDebrid, direct link, clone và yt-dlp cũng có phản hồi lỗi.
Nếu người dùng hủy trong bước chuẩn bị, không tiếp tục dispatch task.
Chỉ dùng `Message.react(emoji=...)` của wzgram; bỏ nhánh API typed/private cũ.
Lỗi mạng không blacklist emoji, FloodWait không khiến việc chuyển file phải chờ;
cache emoji không hợp lệ có thời hạn và giới hạn kích thước.

**4. Plugin speedtest.**
Giữ plugin, lệnh và renderer của tác giả. Bước tạo ảnh share chạy qua worker thread đang dùng chung trong bot.
Nếu gửi kết quả trả lỗi hoặc không có message, sửa tin trạng thái bằng kết quả dạng text.

**5. Helper gửi tin/status.**
Giữ `ReplyParameters`/`LinkPreviewOptions` của upstream, truyền tiếp tham số topic qua các nhánh gửi/fallback/retry.
Caption vượt giới hạn chuyển sang text đầy đủ thay vì cắt nội dung. Fallback parse/peer lỗi được chặn để không đệ quy vô hạn.

## Khuyến nghị giữ/bỏ

- Dùng upstream cho speedtest, tạo/quản lý session, HyperDL/HyperUL/transfer, plugin manager,
  API tin nhắn mới và nền Docker mới.
- Giữ mod riêng cho quota/VIP/referral/subscribe, menu và thương hiệu, status ảnh/text,
  MIUI fallback, selector legacy và giám sát FD.
- Các phần client/tunnel/reaction đã được tích hợp theo API và vòng đời mới; chưa có kiểm chứng hiệu năng hay truyền file thật trong Docker.
- Chưa tính `feature/shared-user-quota`: commit của nhánh chia sẻ quota/VIP giữa nhiều bot không nằm trong `wzv3` đang dùng.

## Phụ lục: đủ 41 file trong delta cũ

Nhóm A1–A19 tham chiếu bảng trên; các file đã xóa trong mod cũ vẫn được tính trong phạm vi đối chiếu.

| # | File | Nhóm |
| --- | --- | --- |
| 1 | `Dockerfile` | A16 |
| 2 | `bot/__main__.py` | A2 |
| 3 | `bot/core/config_manager.py` | A4 |
| 4 | `bot/core/handlers.py` | A5 |
| 5 | `bot/core/startup.py` | A2 |
| 6 | `bot/core/tg_client.py` | A3 |
| 7 | `bot/helper/ext_utils/bot_utils.py` | A12 |
| 8 | `bot/helper/ext_utils/hyperdl_utils.py` | A11 |
| 9 | `bot/helper/ext_utils/hyperup_utils.py` | A11 |
| 10 | `bot/helper/ext_utils/quota_reset_notifier.py` | A1 |
| 11 | `bot/helper/ext_utils/referral_manager.py` | A1 |
| 12 | `bot/helper/ext_utils/task_manager.py` | A2 |
| 13 | `bot/helper/ext_utils/tunnel_monitor.py` | A14 |
| 14 | `bot/helper/ext_utils/user_quota_manager.py` | A1 |
| 15 | `bot/helper/languages/en.py` | A8 |
| 16 | `bot/helper/listeners/aria2_listener.py` | A12 |
| 17 | `bot/helper/listeners/task_listener.py` | A2 |
| 18 | `bot/helper/mirror_leech_utils/download_utils/aria2_download.py` | A13 |
| 19 | `bot/helper/mirror_leech_utils/download_utils/nzb_downloader.py` | A12 |
| 20 | `bot/helper/mirror_leech_utils/download_utils/qbit_download.py` | A12 |
| 21 | `bot/helper/mirror_leech_utils/download_utils/telegram_download.py` | A11 |
| 22 | `bot/helper/mirror_leech_utils/upload_utils/telegram_uploader.py` | A11 |
| 23 | `bot/helper/telegram_helper/bot_commands.py` | A5 |
| 24 | `bot/helper/telegram_helper/filters.py` | A7 |
| 25 | `bot/helper/telegram_helper/message_utils.py` | A10 |
| 26 | `bot/helper/telegram_helper/tg_transfer.py` | A11 |
| 27 | `bot/modules/__init__.py` | A5 |
| 28 | `bot/modules/bot_settings.py` | A6 |
| 29 | `bot/modules/clone.py` | A9 |
| 30 | `bot/modules/file_selector.py` | A12 |
| 31 | `bot/modules/mirror_leech.py` | A9 |
| 32 | `bot/modules/services.py` | A8 |
| 33 | `bot/modules/speedtest.py` | A15 |
| 34 | `bot/modules/users_settings.py` | A6 |
| 35 | `bot/modules/ytdlp.py` | A9 |
| 36 | `bot/version.py` | A17 |
| 37 | `docker-compose.yml` | A16 |
| 38 | `gen_user_session.py` | A18 |
| 39 | `scripts/apply-deploy-test-mode.ps1` | A19 |
| 40 | `web/templates/legacy_page.html` | A12 |
| 41 | `web/wserver.py` | A12 |
