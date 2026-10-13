# T7.4-SQL — Hugging Face Spaces showcase (optional)

## Mục tiêu

Xuất bản showcase NL2SQL chỉ khi giữ được đúng small model và safety contract của
hệ thống nghiên cứu. Đây không phải scientific execution environment.

## Điều kiện bắt đầu

- Local Gradio demo T7.3 đã pass.
- Model revision, quantization và tokenizer được pin.
- Resource probe chứng minh Space chạy được trong RAM/CPU/GPU quota mục tiêu.
- SQL validator, managed-relation allowlist và dry-run/cost guard không bị bỏ qua.

## Hai kết quả hợp lệ

1. **Interactive:** Space chạy đúng small model đã pin và chỉ thực thi BigQuery
   khi credential/cost policy được cấu hình an toàn.
2. **Static showcase:** nếu resource không đủ, hiển thị các case study đã seal và
   ghi rõ không phải live inference.

Không thay model nghiên cứu bằng dịch vụ inference bên ngoài để làm demo chạy được.

## Acceptance

- [ ] Model identity khớp artifact nghiên cứu hoặc showcase được gắn nhãn static.
- [ ] Không có write access; query chỉ được chạy sau parse, allowlist và dry-run.
- [ ] Secrets không nằm trong image, log hoặc repository.
- [ ] UI ghi rõ limitation, provenance và trạng thái live/static.
- [ ] Local demo vẫn là đường defense chính nếu Space không đủ tài nguyên.

## Trạng thái

Optional; chỉ thực hiện sau T7.3.
