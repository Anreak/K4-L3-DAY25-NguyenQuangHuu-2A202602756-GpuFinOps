# NimbusAI — GPU Cost Optimization Report

**Period:** monthly  
**Baseline spend:** $27,133  
**Optimized spend:** $14,626  
**Projected savings:** $12,507  (**46%**)

## Savings by lever

| Lever | Savings (USD) |
|---|---|
| Inference (cascade/cache/batch) | $1,212 |
| Purchasing (spot/reserved) | $10,040 |
| Right-size util-lies | $655 |
| Kill idle GPUs | $600 |

## Sustainability

- Energy per query: 0.24 Wh
- Carbon per query: 0.091 gCO2e
- Cheapest+cleanest region: europe-north1

## Phân tích bản chất GPU-Util Lie và tác động tài chính

- gpu-h100-4 ghi nhận mức GPU-Util lên tới 98.2%, tuy nhiên hiệu suất tính toán thực sự (MFU) chỉ đạt 19.4% (0.194) và MBU đạt 20.7%.
- Nguyên nhân gốc rễ: nvidia-smi chỉ ghi nhận tỷ lệ thời gian các bộ xử lý SM có xung nhịp hoạt động (có ít nhất 1 warp đang active), hoàn toàn không đo lường khối lượng tính toán hữu ích trên Tensor Cores. Do hiện tượng nghẽn truyền tải bộ nhớ (memory stalls) trong giai đoạn decode (arithmetic intensity chỉ đạt 1-2 FLOP/byte so với ridge point 295 FLOP/byte của H100) và overhead khởi chạy kernel, GPU tiêu tốn phần lớn chu kỳ để chờ nạp dữ liệu từ HBM.
- Tác động tài chính: NimbusAI đang chi trả 100% chi phí thuê H100 ($2.50/giờ) nhưng chỉ thu lại khoảng 1/5 thông lượng tính toán định mức, gây lãng phí nghiêm trọng ngân sách.

## Kế hoạch hành động theo thứ tự ưu tiên ROI

1. Ưu tiên 1 - Tối ưu chiến lược mua sắm GPU (Purchasing Strategy - Tiết kiệm $10,040/tháng): Đây là đòn bẩy đóng góp lớn nhất (chiếm hơn 80% tổng savings). Chuyển dịch ngay các job training/fine-tuning/eval có thể gián đoạn (interruptible=1) sang Spot instance kết hợp lưu checkpoint tự động; cam kết Reserved 3 năm cho các workload suy luận hoạt động 24/7.
2. Ưu tiên 2 - Áp dụng các đòn bẩy suy luận (Inference Levers - Tiết kiệm $1,212/tháng): Giảm đơn giá phục vụ từ $6.488 xuống $1.126 trên mỗi triệu token (giảm 82.6%). Thực hiện cascade routing sang model nhỏ cho các tác vụ phổ thông, kích hoạt prompt caching để hưởng chiết khấu 90% cho input lặp lại, và chuyển các tác vụ bất đồng bộ sang Batch API.
3. Ưu tiên 3 - Right-sizing GPU memory-bound (Tiết kiệm $655/tháng): Thay thế gpu-h100-4 bằng A100 (tiết kiệm $511.20/tháng) và gpu-a10g-1 bằng L4 (tiết kiệm $144.00/tháng). Cả hai GPU thay thế đều đáp ứng đủ dung lượng VRAM và băng thông thực tế, ngăn ngừa lỗi tràn bộ nhớ (OOM).
4. Ưu tiên 4 - Dọn dẹp GPU nhàn rỗi (Kill Idle GPUs - Tiết kiệm $600/tháng): Thiết lập quy tắc tự động tắt các GPU không có tải (util < 10%) sau 15 phút, loại bỏ hoàn toàn 8 giờ idle mỗi ngày trên gpu-h100-5.

## Đánh giá Tính bền vững và Vùng triển khai (Sustainability)

- Đánh giá điện năng và carbon: Mỗi truy vấn thông thường tiêu thụ trung bình 0.24 Wh và phát thải 0.091 gCO2e tại us-east-1. Vùng sạch nhất và rẻ nhất là europe-north1 với hệ số phát thải chỉ 30 gCO2/kWh (sạch hơn 12.6 lần so với us-east-1).
- Đánh đổi độ trễ mạng (Latency Trade-off): Việc dịch chuyển toàn bộ sang europe-north1 có thể làm tăng độ trễ mạng (RTT tăng thêm 80-120ms đối với người dùng tại Bắc Mỹ). Giải pháp tối ưu: Triển khai các tác vụ batch training, embedding và offline evaluation tại europe-north1, trong khi hạ tầng suy luận tương tác thời gian thực được đặt tại us-west-2 hoặc us-east-wa để cân bằng giữa chi phí, carbon và độ trễ.

## Báo cáo kết quả mở rộng (Extensions)

- Extension 2 (Right-sizing theo MBU): Phân tích chi phí trên mỗi GB VRAM ($/GB-VRAM) cho thấy MI300X ($0.0102) và A100 ($0.0224) có hiệu quả chi phí bộ nhớ vượt trội so với H100 ($0.0312). Đề xuất right-size 2 GPU bị util-lie giúp tiết kiệm $655.20/tháng mà không làm giảm thông lượng.
- Extension 3 (Kinh tế học Caching): Phân tích điểm hòa vốn cho thấy prompt caching có lãi ngay khi hệ số đọc lại đạt từ 1.11 lần trở lên. Với các prefix được đọc từ 2 lần trở lên, chi phí giảm tới 90% trên phần input cache.
- Extension 4 (Ngân sách Reasoning): Các truy vấn suy luận (is_reasoning=1) chỉ chiếm 8.38% lượng request và 16.48% lượng token nhưng tiêu thụ tới 94.04% tổng điện năng suy luận (29,787.7 Wh/ngày so với 1,887.6 Wh của nhóm non-reasoning, do hệ số nhân 80x). Đề xuất chính sách định tuyến chặt chẽ: chỉ kích hoạt reasoning khi độ phức tạp vượt ngưỡng xác định.

_Figures are June-2026 as-of snapshots; re-baseline before acting._