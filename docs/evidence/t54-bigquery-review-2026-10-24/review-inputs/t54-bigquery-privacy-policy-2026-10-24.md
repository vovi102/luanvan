# T5.4-B — phạm vi dữ liệu để duyệt

Ngày chuẩn bị: 2026-10-24 (Asia/Saigon). Đây là chính sách dự án được đề xuất để
reviewer duyệt, không phải tuyên bố pháp lý của nhà cung cấp hoặc review đã ký.
Bốn worksheet tại [privacy-review-drafts.json](../../configs/t54/privacy-review-drafts.json)
bind SHA-256 của chính file này; chưa được nạp như canonical PrivacyReview.

## Phạm vi và luồng dữ liệu

- B1/B2 × EN/VI, hai finalized test snapshots được pin trong worksheets.
  Mỗi run N=100; EN/VI và ba replicates giữ riêng. Không sửa prompt/model/SQL,
  không tune theo benchmark và không mở inference mới.
- Inference lịch sử đã dùng Kaggle private: câu hỏi, schema/prompt, năm training
  examples khi là B2 và model outputs đã được gửi/lưu ở Kaggle. Private notebook
  không đồng nghĩa dữ liệu chưa rời máy. Không gửi credential BigQuery tới Kaggle.
- Bước BigQuery chỉ gửi exact GoogleSQL gold/predicted đã pin, gồm literals,
  địa chỉ Ethereum và labels xuất hiện trong SQL. Không cần gửi câu hỏi NL,
  prompts, training corpus hoặc model weights cho BigQuery.
- Project job: `nl2sparql-thesis`; dataset `nl2sparql_analytics`, location `US`.
  Dataset location không phải cam kết mọi metadata/logs đều cư trú duy nhất ở US.
  Provider scope đề xuất: `Kaggle; Google Cloud BigQuery`, `data_egress=provider`.

## Dữ liệu đầu vào và kết quả

- Chỉ analytics catalog hiện có và dependencies đã ghi trong metadata inventory;
  không tự mở nguồn private mới. Public Ethereum addresses/labels vẫn cần quản
  lý quyền truy cập, không mặc định là dữ liệu vô hại hoặc được phép công bố.
- Dry-run chỉ validate/estimate, không đọc result rows cho evaluation, không tạo
  execution accuracy. Khi được duyệt live riêng, row data có thể được tải về bộ
  nhớ để canonicalize; artifact evaluation chỉ giữ schema/count/row digests.
- Journal có thể lưu nguyên SQL/literals, case/run IDs, job IDs, thời gian,
  bytes và kết quả lỗi. Row digests không phải bảo đảm ẩn danh.
- Không xuất full result rows, weights hoặc secrets vào repository để hoàn tất
  privacy review. Không log access/refresh tokens, credential JSON hoặc headers.

## Quyền đọc, lưu giữ và công bố

- Quyền đọc được đề xuất cho chủ dự án và collaborators đã được chủ dự án cho
  phép tại workspace/repository, Google Cloud và Kaggle. Chưa audit toàn bộ IAM
  hoặc collaborators; reviewer xác nhận phạm vi này trước khi ký.
- Gói duyệt và execution journals ở workspace/repository hiện tại; không push,
  upload, public hóa hay cấp thêm quyền như một phần task này.
- Giữ bằng chứng nguồn/hash immutable để tái lập luận văn; không tự xóa artifacts
  hoặc sửa access policy. Việc công bố luận văn/dataset cần review/redact riêng.
  Vòng đời logs/results phía provider theo cấu hình/dịch vụ tương ứng, chưa có
  cam kết custom retention hoặc xóa từ phía provider.

## Điều kiện ký

Reviewer xác nhận scope egress, người được đọc và retention ở trên. Agent không
điền reviewer ID/thời gian thay người dùng. Sau khi có quyết định thật, tạo bốn
canonical PrivacyReview, re-adapt vào thư mục mới và pin hashes mới; không ghi đè
12 canonical artifacts offline. Duyệt policy không tự cấp quyền dry-run/live,
không bật billing và không xác nhận scientific readiness.

Nguồn cấu hình thực tế: [metadata inventory](../evidence/t54-bigquery-review-2026-10-24/metadata.json).
Phân biệt notebook và dataset sharing theo
[Kaggle notebooks documentation](https://www.kaggle.com/docs/notebooks).
Trang Kaggle đọc được qua web search nhưng tải snapshot HTTP trực tiếp bị lỗi;
không có hash snapshot provider-policy Kaggle và không suy diễn điều khoản của họ.
`policy_sha256` ở worksheet là hash chính sách dự án này.
