# Nhật ký do text2BPMN xuất

Đặt nhật ký vào thư mục con trùng tên tệp BPMN, mỗi tệp là một kịch bản (tên tệp = tên kịch bản):

```
data/part1_logs/
└── quy-trinh-nghi-phep/
    ├── viec_suon_se.csv
    └── nhieu_truc_trac.xes
```

Khi thư mục này có tệp, pipeline dùng nhật ký đó thay cho bộ mô phỏng. Cột được nhận diện tự động
(`case_id` / `case:concept:name`, `activity` / `concept:name`, `start_ts` / `start_timestamp`,
`end_ts` / `time:timestamp`, `resource`, `role` / `lane`); có thể bổ sung tên cột trong
`src/text2bpmn_mining/eventlog.py` (`COL_ALIASES`). Nhật ký dạng hai dòng `start`/`complete`
(`lifecycle:transition`) cũng được ghép lại.

Nếu nhật ký không có thời điểm hồ sơ sẵn sàng (`enable_ts`), thời gian chờ được xấp xỉ bằng
khoảng cách từ lúc bước liền trước kết thúc; cách xấp xỉ này sai khi có nhánh song song.
