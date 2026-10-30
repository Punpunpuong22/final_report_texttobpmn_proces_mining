# final_report_texttobpmn_proces_mining

[![Open In Colab](https://colab.research.google.com/assets/colab-badge.svg)](https://colab.research.google.com/github/Punpunpuong22/final_report_texttobpmn_proces_mining/blob/main/notebooks/Part2_ProcessMining.ipynb)

Mã nguồn **Phần 2** của đề tài *Từ văn bản hành chính đến BPMN cải tiến* (học phần Business Process Management – Process Mining).
Phần 1 (ứng dụng **text2BPMN**) sinh mô hình BPMN 2.0 từ văn bản, mô phỏng kịch bản và xuất nhật ký sự kiện.
Phần 2 nhận chính các tệp đó và chạy một pipeline khai phá quy trình tám bước bằng Python và [PM4Py](https://pm4py.fit.fraunhofer.de/):

```
BPMN (text2BPMN) ─┬─► 1. Kiểm tra cấu trúc, soundness (Woflan)
                  └─► 2. Nhật ký sự kiện (log text2BPMN hoặc mô phỏng 4 kịch bản)
                        ├─► 3. Thống kê mô tả: KPI, biến thể, thời gian làm việc / lưu trú
                        ├─► 4. Khám phá: DFG, Alpha, Heuristics, Inductive Miner
                        ├─► 5. Tuân thủ: alignment + luật nghiệp vụ
                        ├─► 6. Điểm nghẽn: thời gian chờ, tải từng làn, hàng đợi
                        ├─► 7. Nguyên nhân trễ hạn: cây quyết định
                        └─► 8. BPMN TO-BE + what-if (CRN, 10 lần lặp, Wilcoxon, ablation)
                                └─► log TO-BE quay lại bước 5–6 để kiểm chứng
```

> Nhật ký mặc định là **dữ liệu mô phỏng** với tham số giả định (thời gian từng bước, số người mỗi làn, thời hạn).
> Kết quả minh hoạ phương pháp, không mô tả hiệu năng của một tổ chức cụ thể.

## Chạy nhanh

### Google Colab
1. Bấm nút **Open in Colab** ở trên.
2. **Runtime → Run all.** Ô đầu tiên tự clone kho này và cài thư viện. Toàn bộ notebook chạy khoảng 1–2 phút; ô cuối tải tệp zip kết quả về máy.

Kho để riêng tư nên không clone được? Tải tệp zip của kho lên thanh **Files** của Colab rồi Run all; notebook tự giải nén.

### Kaggle
1. *Create → New Notebook → File → Import Notebook*, tải lên `notebooks/Part2_ProcessMining.ipynb`.
2. Trong **Settings**, bật **Internet** (để cài `pm4py` và clone kho).
3. **Run all.** Ô đầu tiên tự clone kho này; không có Internet thì thêm kho dưới dạng dataset (*Add Data → Upload* tệp zip).

### Máy cá nhân
```bash
git clone https://github.com/Punpunpuong22/final_report_texttobpmn_proces_mining.git
cd final_report_texttobpmn_proces_mining
python -m venv .venv && source .venv/bin/activate      # Windows: .venv\Scripts\activate
pip install -r requirements.txt                          # cần thêm Graphviz (https://graphviz.org/download/) để vẽ DFG/BPMN
jupyter notebook notebooks/Part2_ProcessMining.ipynb     # chạy từng bước
# hoặc chạy cả ba quy trình từ dòng lệnh:
PYTHONPATH=src python -m text2bpmn_mining data/bpmn/*.bpmn --n-rep 10
```
Kiểm tra nhanh mã nguồn: `python tests/test_pipeline.py` (hoặc `pytest -q`).

## Giao diện web: text2BPMN đầy đủ (Phần 1 + Phần 2)

Một trang chạy cả chuỗi: **Phần 1** viết quy trình bằng lời → danh sách bước → sơ đồ BPMN (kéo thả, đổi làn,
sửa tên, kiểm tra lỗi nhanh) → thử 200 hồ sơ với hai kịch bản “Việc suôn sẻ” / “Nhiều trục trặc” → xuất nhật ký
CSV/XES; **Phần 2** nhận thẳng sơ đồ và nhật ký đó, chạy tám bước khai phá quy trình và hiện kết quả từng bước
(chỉ số, nhận xét, hình, bảng, BPMN TO-BE, tải `.zip`). Có thể mở sẵn một tệp `.bpmn` hoặc dùng nhật ký có sẵn.

| Nơi chạy | Phần 1 | Phần 2 |
|---|---|---|
| Colab: ô **Giao diện web** cuối notebook | chạy trong trình duyệt | Python chạy thật với mọi sơ đồ |
| Máy cá nhân: `PYTHONPATH=src python -m text2bpmn_mining.web` → http://127.0.0.1:8050 | như trên | như trên |
| `docs/demo.html` (mở trực tiếp, không cần máy chủ) | như trên | kết quả chạy sẵn cho 3 sơ đồ mẫu |

Ở Bước 2, nhật ký của Phần 1 (chỉ có thời gian làm việc) được dùng để **đối chiếu**: bộ mô phỏng của Phần 2 chạy
trên cùng BPMN phải cho thời gian làm việc và tỷ trọng từng bước khớp với Phần 1, rồi mới thêm hồ sơ đến theo thời
gian và số người mỗi làn để có hàng đợi (`Config(part1_logs_as="doi_chieu")`). Nhật ký thật tải lên thì được dùng
trực tiếp (`part1_logs_as="log"`, mặc định khi chạy notebook).

Văn bản mới được chuyển thành danh sách bước bằng Claude khi trang mở trên claude.ai, bằng bộ quy tắc khi mở từ
Colab hoặc máy cá nhân; ba ví dụ dùng đúng tệp BPMN text2BPMN đã sinh. Tạo lại bản tĩnh:
`PYTHONHASHSEED=2 PYTHONPATH=src python scripts/build_demo.py`.

## Cấu trúc kho

```
text2bpmn-process-mining/
├── notebooks/Part2_ProcessMining.ipynb   # notebook chạy từng bước, dùng cho Colab/Kaggle
├── src/text2bpmn_mining/
│   ├── config.py       # tham số, 4 kịch bản, thiết lập riêng mỗi quy trình (luật, bước tự động hoá, luồng cần sửa)
│   ├── bpmn.py         # đọc BPMN, soundness, dò lỗi cấu trúc, ghi BPMN TO-BE
│   ├── simulation.py   # mô phỏng sự kiện rời rạc dựa trên token, cài sai lệch
│   ├── eventlog.py     # đọc log text2BPMN (CSV/XES), chuẩn hoá cột, kiểm tra chất lượng
│   ├── analysis.py     # khám phá (Alpha, Heuristics, Inductive), alignment, luật, điểm nghẽn, cây quyết định
│   ├── report.py       # chuyển kết quả từng bước thành JSON cho giao diện web
│   ├── web/            # giao diện web: server.py (Flask) + static/index.html
│   ├── whatif.py       # so sánh AS-IS / từng thay đổi / TO-BE, Wilcoxon
│   ├── plots.py        # biểu đồ
│   ├── pipeline.py     # lớp Pipeline: step1 … step8, run()
│   └── __main__.py     # dòng lệnh: python -m text2bpmn_mining
├── data/
│   ├── bpmn/           # 3 tệp BPMN do text2BPMN xuất: nghỉ phép, tuyển dụng, đặt hàng
│   └── part1_logs/     # (tuỳ chọn) đặt log CSV/XES của text2BPMN tại đây
├── scripts/run_all.sh
├── tests/test_pipeline.py
├── requirements.txt
└── pyproject.toml
```

## Dùng trong Python

```python
from text2bpmn_mining import Pipeline, Config

cfg = Config(n_cases=200, n_rep=10,
             task_minutes={"Xem xét đơn": 25},     # ghi đè thời gian một bước (phút)
             capacity={"Quản lý": 1, "Nhân sự": 1},  # số người mỗi làn
             sla_minutes=None)                       # None = 1,5 × P90 thời gian lưu trú của S1
p = Pipeline("data/bpmn/quy-trinh-nghi-phep.bpmn", cfg=cfg)
r1 = p.step1_structure()     # hoặc chạy hết: p.run()
...
r8 = p.step8_tobe()
print(r8["wilcoxon"])
```

Mỗi bước trả về một `dict` các bảng `pandas` và ghi kết quả vào `outputs/<tên tệp BPMN>/`.

### Phân tích một quy trình mới
1. Xuất BPMN từ text2BPMN và chép vào `data/bpmn/`.
2. (Tuỳ chọn) Khai báo luật nghiệp vụ, bước đề xuất tự động hoá và các luồng cần sửa trong `PROCESS_PRESETS`
   (`config.py`), tra theo thuộc tính `name` của `<bpmn:process>`; hoặc truyền trực tiếp qua `Config(rules=..., automate=..., repair_flows=...)`.
3. (Tuỳ chọn) Đặt nhật ký thật vào `data/part1_logs/<tên tệp BPMN>/` – xem `data/part1_logs/README.md`.
4. Chạy notebook hoặc `python -m text2bpmn_mining data/bpmn/<tệp>.bpmn`.

### Bốn kịch bản mặc định

| Kịch bản | Nhánh thuận | Làm lại | Hồ sơ đến (TB) | Sai lệch cài vào | Ghi chú |
|---|---|---|---|---|---|
| S1_suon_se | 90% | 5% | 1 / 40 phút | – | nút “Việc suôn sẻ” của text2BPMN |
| S2_truc_trac | 30% | 33% | 1 / 40 phút | – | nút “Nhiều trục trặc” |
| S3_qua_tai | 90% | 5% | 1 / 25 phút | – | kiểm tra hàng đợi |
| S4_vi_pham | 90% | 5% | 1 / 40 phút | 10% hồ sơ | kiểm tra bước tuân thủ |

## Đầu ra

| Tệp | Nội dung |
|---|---|
| `tab_bpmn_structure.csv` | Lỗi cấu trúc của BPMN |
| `event_log_all.csv`, `event_log_all.xes` | Nhật ký sự kiện mọi kịch bản |
| `tab_kpi.csv` | Số biến thể, thời gian làm việc, thời gian lưu trú, P90, tỷ lệ trễ hạn, làm lại |
| `tab_discovery.csv` | Fitness, % vết khớp, precision, generalization, simplicity |
| `tab_alignment.csv`, `tab_rule_violations.csv` | Kết quả tuân thủ |
| `tab_bottleneck.csv` | Thời gian chờ / xử lý theo bước và kịch bản |
| `tab_asis_vs_tobe_ablation.csv`, `tab_wilcoxon.csv` | So sánh AS-IS và TO-BE (trung bình ± CI 95%) |
| `TO_BE_*.bpmn` | Mô hình cải tiến, mở được bằng bpmn.io / Camunda Modeler |
| `fig_*.png` | BPMN AS-IS/TO-BE, DFG, heatmap thời gian chờ, hàng đợi, boxplot |

## Kết quả tham chiếu (quy trình nghỉ phép, seed 42)

| | S1 Thuận lợi | S2 Trục trặc | S3 Quá tải |
|---|---|---|---|
| Lưu trú TB AS-IS (phút, 10 lần lặp) | 125,6 | 1.518,9 | 614,5 |
| Lưu trú TB TO-BE (C1+C2+C3) | 44,5 (−65%) | 79,3 (−95%) | 128,1 (−79%) |
| Wilcoxon theo cặp | p = 0,002 | p = 0,002 | p = 0,002 |
| Điểm nghẽn | Ghi nhận nghỉ phép (Nhân sự) | Xem xét đơn (Quản lý) | Ghi nhận nghỉ phép (Nhân sự) |

Mô hình đặt hàng **không sound** (8 vấn đề cấu trúc); sửa ba luồng thừa (C0) cùng C2 giảm thời gian lưu trú 25%.

## Lưu ý về tái lập kết quả
- Mô phỏng dùng hạt giống cố định (`seed=42`) và dòng số ngẫu nhiên riêng cho từng hồ sơ, nên log và các bảng KPI,
  tuân thủ, điểm nghẽn, what-if giống nhau giữa các lần chạy.
- Một vài chỉ số của **Heuristics Miner** trong PM4Py phụ thuộc thứ tự duyệt tập hợp của Python (`PYTHONHASHSEED`),
  nên có thể lệch nhẹ giữa các phiên notebook ở quy trình tuyển dụng và đặt hàng. Lệnh `python -m text2bpmn_mining`
  tự cố định `PYTHONHASHSEED=2` (giá trị cho đúng các bảng trong báo cáo). Kết quả của quy trình nghỉ phép không bị ảnh hưởng.
- Chỉ số khám phá được đánh giá in-sample; bước 7 cho liên kết thống kê, không phải quan hệ nhân quả.

## Giấy phép
PM4Py phát hành theo giấy phép **AGPL-3.0**. Nhóm cần chọn giấy phép cho mã của mình (thêm tệp `LICENSE`)
cho tương thích nếu công bố hoặc phân phối lại.

## Tài liệu tham khảo chính
- van der Aalst, W. M. P. (2016). *Process mining: Data science in action* (2nd ed.). Springer.
- Dumas, M., La Rosa, M., Mendling, J., & Reijers, H. A. (2018). *Fundamentals of business process management* (2nd ed.). Springer.
- Berti, A., van Zelst, S. J., & van der Aalst, W. M. P. (2019). Process Mining for Python (PM4Py). ICPM Demo Track, CEUR-WS Vol-2374.
- Leemans, S. J. J., Fahland, D., & van der Aalst, W. M. P. (2014). Discovering block-structured process models from event logs containing infrequent behaviour. BPM Workshops, LNBIP 171.
- Verbeek, H. M. W., Basten, T., & van der Aalst, W. M. P. (2001). Diagnosing workflow processes using Woflan. *The Computer Journal*, 44(4).
