# Báo cáo Kỹ thuật và Phân tích Tối ưu hóa GPU FinOps (NimbusAI)

Họ và tên học viên: Nguyễn Quang Hữu
Mã học viên: 2A202602756
Khóa học: AICB Phase 2 - Track 2 (Infrastructure) - Day 25
Dự án: NimbusAI GPU Cost Optimization Report


1. So sánh Baseline và Optimized

Trong bài toán kiểm toán tài chính hạ tầng tính toán tại NimbusAI, việc tối ưu hóa được đánh giá đa chiều trên cả góc độ chi phí vận hành hàng tháng (OpEx theo đơn vị USD) và chỉ số hiệu quả kinh tế đơn vị trên sản lượng phục vụ (Unit Economics theo đơn vị $/1M-token).

Bảng so sánh tổng quan:
- Tổng chi phí hàng tháng (Monthly Spend):
  + Baseline: $27,133/tháng
  + Optimized: $14,626/tháng
  + Tiết kiệm tuyệt đối: $12,507/tháng
  + Tỷ lệ cắt giảm: 46.1%
- Chi phí phục vụ suy luận trên một triệu token ($/1M-token):
  + Baseline: $6.488/1M-token
  + Optimized: $1.126/1M-token
  + Tỷ lệ cắt giảm: 82.6%
- Tổng số lượng request và token xử lý:
  + 2,400 lượt truy vấn
  + 7,533,027 token (input và output)
- Tỷ lệ gán nhãn tài nguyên (Tag Coverage): 92% (đủ điều kiện kích hoạt Chargeback gate >= 80%).


2. Phân tích đóng góp của từng đòn bẩy (Cost Levers)

Khoản ngân sách cắt giảm $12,507/tháng được cấu thành từ 4 đòn bẩy chính:

a. Đòn bẩy mua sắm GPU (Purchasing Strategy - Tiết kiệm $10,040/tháng):
Đóng góp lớn nhất vào tổng ngân sách tiết kiệm (chiếm 80.3% tổng số tiền giảm được).
- Cơ chế: Chuyển đổi từ mô hình thuê on-demand thuần túy sang mô hình kết hợp Spot instance và Reserved instance dựa trên chu kỳ hoạt động (duty cycle) và khả năng chấp nhận gián đoạn (interruptibility).
- Chi tiết:
  + Các tác vụ huấn luyện (job-train-llm, job-train-embed, job-finetune, job-batch-eval) có đặc tính interruptible=1 được chuyển sang Spot instance kết hợp lưu checkpoint định kỳ. Dù phát sinh chi phí phụ trội checkpoint và chạy lại khi bị thu hồi (effective hours tăng từ 720h lên 759.6h), mức chiết khấu spot từ 40% đến 60% giúp cắt giảm $4,404/tháng cho riêng job-train-llm.
  + Các tác vụ suy luận vận hành liên tục 24/7 (job-infer-chat, job-infer-rag, job-infer-search) có duty cycle 100% vượt xa điểm hòa vốn 55% (break-even utilization ứng với chiết khấu 45%), mang lại hiệu quả kinh tế vượt trội khi ký cam kết Reserved 3 năm.

b. Đòn bẩy tối ưu hóa suy luận (Inference Levers - Tiết kiệm $1,212/tháng):
Đóng góp mức giảm đơn giá token sâu nhất (giảm 82.6% đơn giá $/1M-token).
- Cascade routing: Thay vì chuyển 100% truy vấn vào mô hình lớn (Large tier: $3.00 in / $15.00 out), hệ thống định tuyến các truy vấn đơn giản sang mô hình nhỏ (Small tier: $0.20 in / $0.40 out), rẻ hơn từ 15 đến 37 lần.
- Prompt caching: Đối với các tiền tố prompt lặp lại, chi phí input được hưởng chiết khấu 90% (chỉ tính 10% giá gốc).
- Batch API: Các truy vấn phân tích hoặc đánh giá không yêu cầu phản hồi thời gian thực được xử lý theo lô với mức chiết khấu 50%.
- Hiệu ứng nhân dồn (Discount Stack): Khi kết hợp Batch API và 100% Prompt Cache Hit, chi phí thực tế chỉ còn bằng 0.50 * 0.10 = 0.05 (giảm 95% so với giá naive).

c. Đòn bẩy hạ cấp GPU nghẽn bộ nhớ (Right-sizing Util-Lies - Tiết kiệm $655/tháng):
- Hạ cấp gpu-h100-4 sang A100: Tiết kiệm $511.20/tháng.
- Hạ cấp gpu-a10g-1 sang L4: Tiết kiệm $144.00/tháng.

d. Đòn bẩy tắt GPU nhàn rỗi (Kill Idle GPUs - Tiết kiệm $600/tháng):
- Telemetry ghi nhận gpu-h100-5 có 8 giờ nhàn rỗi hoàn toàn mỗi ngày (util < 10%). Tắt tài nguyên trong các khung giờ trống giúp thu hồi $20.00/ngày, tương đương $600/tháng.


3. Phân tích hiện tượng GPU-Util Lie và tác động tài chính

Trong telemetry ghi nhận của NimbusAI:
- gpu-h100-4 ghi nhận mức GPU-Util lên tới 98.2%, tuy nhiên chỉ số MFU (Model FLOPs Utilization) chỉ đạt 0.194 (19.4%) và MBU (Model Bandwidth Utilization) chỉ đạt 0.207 (20.7%).
- gpu-a10g-1 ghi nhận GPU-Util là 96.9%, trong khi MFU chỉ đạt 0.268 và MBU đạt 0.302.

Bản chất kỹ thuật:
Công cụ giám sát phần cứng truyền thống nvidia-smi chỉ đo lường tỷ lệ thời gian mà các bộ xử lý Streaming Multiprocessor (SM) có ít nhất một warp đang active (clock đang bận). Chỉ số này hoàn toàn không đo lường mật độ tính toán thực tế của Tensor Cores (số phép tính FLOPs thực sự được thực thi trên mỗi giây so với peak FLOPs của phần cứng).
Nguyên nhân gốc rễ gây ra hiện tượng nói dối (GPU-Util lie):
1. Nghẽn truyền tải bộ nhớ (Memory-bound stall): Đối với các tác vụ decode sinh token từng bước trong mô hình ngôn ngữ lớn, arithmetic intensity rất thấp (chỉ khoảng 1 đến 2 FLOP/byte), trong khi điểm chuyển tiếp (ridge point) trên biểu đồ Roofline của H100 là 295 FLOP/byte. Tensor Cores liên tục rơi vào trạng thái nhàn rỗi để chờ nạp trọng số từ HBM vào bộ nhớ đệm SRAM.
2. Overhead khởi chạy kernel và đồng bộ hóa: Tải xử lý gồm nhiều kernel nhỏ với kích thước batch không tối ưu khiến bộ điều phối lệnh (instruction scheduler) phải bận rộn duy trì ngữ cảnh nhưng không phát sinh thông lượng tính toán lớn.

Tác động tài chính:
Doanh nghiệp đang chi trả 100% đơn giá thuê GPU đỉnh cao ($2.50/giờ cho H100), nhưng thực tế chỉ nhận lại chưa đầy 1/5 năng lực tính toán định mức. Đây là nguồn lãng phí ẩn cực kỳ nguy hiểm nếu đội ngũ kỹ thuật chỉ nhìn vào biểu đồ GPU-Util của hệ thống giám sát.


4. Báo cáo triển khai các phần mở rộng (Your Turn Extensions)

Chúng tôi đã triển khai thành công 3 phần mở rộng nâng cao với các kết quả đo lường định lượng:

a. Extension 2 - Right-sizing theo MBU (Triển khai trong missions/m1_efficiency_audit.py):
- Phương pháp: Đo lường chi phí trên mỗi GB VRAM ($/GB-VRAM) và chi phí trên mỗi TB/s băng thông ($/TB/s) từ bảng giá.
  Kết quả kinh tế học VRAM:
  + MI300X: $0.0102 / GB-VRAM (192GB, 5.3 TB/s)
  + A100: $0.0224 / GB-VRAM (80GB, 2.0 TB/s)
  + H100: $0.0312 / GB-VRAM (80GB, 3.35 TB/s)
  + L4: $0.0333 / GB-VRAM (24GB, 0.3 TB/s)
  + A10G: $0.0417 / GB-VRAM (24GB, 0.6 TB/s)
- Đề xuất thay thế:
  + gpu-h100-4 đang dùng trung bình 51.9 GB VRAM và 0.693 TB/s băng thông. Nếu hạ cấp xuống GPU rẻ nhất theo $/h là L4 ($0.80/h) hoặc A10G ($1.00/h), hệ thống sẽ gặp lỗi tràn bộ nhớ (Out-Of-Memory) vì hai loại GPU này chỉ có 24GB VRAM. Do đó, GPU tối ưu chính xác là A100 (80GB VRAM, 2.0 TB/s băng thông, giá $1.79/h). Mức tiết kiệm đạt ($2.50 - $1.79) * 24 * 30 = $511.20/tháng.
  + gpu-a10g-1 dùng 15.2 GB VRAM và 0.181 TB/s băng thông, hoàn toàn phù hợp để hạ cấp sang L4 (24GB VRAM, 0.3 TB/s, giá $0.80/h). Mức tiết kiệm đạt ($1.00 - $0.80) * 24 * 30 = $144.00/tháng.
- Tổng tiết kiệm: $655.20/tháng mà vẫn đảm bảo 100% throughput và không rủi ro OOM.

b. Extension 3 - Kinh tế học Prompt Caching cache_is_worth_it() (Triển khai trong finops/pricing.py và missions/m2_inference_levers.py):
- Phương pháp: Xây dựng hàm kiểm tra điểm hòa vốn giữa chi phí ghi cache (write cost) và chi phí đọc cache được chiết khấu (read discount = 90%).
- Công thức điểm hòa vốn: break_even_reads = write_cost / (input_price * (1 - cache_discount)).
- Đo lường thực tế:
  + Với mô hình Small ($0.20/1M input) và Large ($3.00/1M input), giả định chi phí ghi cache bằng giá input gốc, điểm hòa vốn là 1.11 lần đọc.
  + Nếu số lần đọc là 1 lần: cache_is_worth_it() trả về False (thua lỗ do chịu thêm chi phí ghi).
  + Nếu số lần đọc từ 2 lần trở lên: cache_is_worth_it() trả về True (bắt đầu phát sinh lợi nhuận ròng).
- Kết quả kiểm thử: Đã bổ sung 2 unit tests chuyên biệt trong tests/test_extensions.py kiểm tra điểm hòa vốn và trường hợp biên (input price = 0 hoặc discount = 100%).

c. Extension 4 - Quản lý Ngân sách Reasoning (Triển khai trong missions/m2_inference_levers.py):
- Phân tích hiện trạng dữ liệu (token_usage.csv):
  + Nhóm Non-Reasoning (is_reasoning=0): 2,199 request (91.62%), 6,291,871 token (83.52%), chi phí tối ưu $7.09/ngày (83.54%), tiêu thụ 1,887.6 Wh/ngày (chỉ chiếm 5.96% tổng năng lượng).
  + Nhóm Reasoning (is_reasoning=1): 201 request (8.38%), 1,241,156 token (16.48%), chi phí tối ưu $1.40/ngày (16.46%), nhưng tiêu thụ tới 29,787.7 Wh/ngày (chiếm tới 94.04% tổng năng lượng suy luận).
- Lý giải nguyên nhân: Mô hình reasoning áp dụng cơ chế chuỗi suy nghĩ dài (chain-of-thought) và kiểm chứng bước trung gian, khiến mức tiêu thụ năng lượng tăng vọt khoảng 80 lần (REASONING_ENERGY_MULTIPLIER = 80.0) so với truy vấn tiêu chuẩn.
- Đánh giá chính sách Cap 10%: Vì tỷ trọng hiện tại của reasoning chỉ là 8.38% (< 10%), nên áp dụng cap 10% mang lại mức tiết kiệm bằng 0 USD và 0 Wh.
- Đề xuất chính sách nâng cao (Selective Reasoning Cap 5%): Nếu thiết lập bộ phân loại ý định (classifier) chỉ cho phép tối đa 5% tác vụ phức tạp cao kích hoạt reasoning, hệ thống sẽ tiết kiệm được $0.45/ngày và 11,854 Wh/ngày (giảm gần 40% lượng điện năng tiêu thụ toàn hệ thống).


5. Khuyến nghị chiến lược cho NimbusAI (Góc nhìn FinOps Lead)

Nếu đảm nhận vai trò Trưởng bộ phận FinOps (FinOps Lead) tại NimbusAI, 3 hành động ưu tiên cao nhất cần triển khai ngay lập tức gồm:

Hành động 1: Cấu trúc lại danh mục mua sắm GPU hạ tầng (Áp dụng Purchasing Levers)
- Ban hành chính sách phân loại workload bắt buộc: Mọi job huấn luyện và tinh chỉnh mô hình mới đăng ký vào cụm tính toán phải được gắn nhãn khả năng gián đoạn. Thiết lập checkpointing tự động lưu vào S3/GCS mỗi 30 phút để chuyển 100% các job này sang Spot instances.
- Thực hiện hợp đồng cam kết Reserved 3 năm cho 100% dung lượng GPU phục vụ các endpoint suy luận cốt lõi đã chạy ổn định 24/7.
- Kỳ vọng: Thu hồi ngay lập tức $10,040/tháng (cắt giảm hơn 37% tổng hóa đơn hạ tầng công ty).

Hành động 2: Tái cấu trúc pipeline suy luận với Gateway định tuyến thông minh (Inference Gateway)
- Triển khai LiteLLM Proxy / AI Gateway ở tầng trước mô hình: Tự động phân tích ngữ nghĩa câu hỏi để kích hoạt Cascade routing (chuyển 70-80% request đơn giản sang model nhỏ), đồng thời chỉ cho phép bật is_reasoning khi điểm đánh giá độ phức tạp vượt ngưỡng 0.85.
- Kích hoạt cơ chế Prompt Caching trên toàn bộ context tài liệu doanh nghiệp và hệ thống trợ lý RAG để tận dụng mức giảm giá 90% cho input token.
- Kỳ vọng: Giảm chi phí phục vụ trực tiếp từ $6.488 xuống $1.126/1M-token, đồng thời giảm 94% nguy cơ bùng nổ tiêu thụ điện năng từ reasoning.

Hành động 3: Thiết lập rào cản kỹ thuật quản trị chi phí (Cost Governance & Right-Sizing)
- Cấu hình daemon giám sát tự động: Phát hiện và tự động tắt (auto-terminate) các máy ảo GPU rơi vào trạng thái nhàn rỗi quá 15 phút.
- Thay thế chỉ số theo dõi GPU-Util trên dashboard Datadog/Grafana bằng MFU và MBU. Thực hiện hạ cấp ngay lập tức các GPU bị util-lie (gpu-h100-4 sang A100, gpu-a10g-1 sang L4).
- Tận dụng mức Tag Coverage 92% hiện tại để chính thức áp dụng cơ chế Chargeback: Xuất dữ liệu định dạng FOCUS hàng tháng và phân bổ chi phí trực tiếp về ngân sách của 4 team (assistant, search, eval, rag) để nâng cao trách nhiệm tài chính của từng đội ngũ sản phẩm.
