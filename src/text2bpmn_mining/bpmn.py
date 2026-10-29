"""Đọc, kiểm tra và chỉnh sửa tệp BPMN 2.0 XML do text2BPMN xuất."""
from __future__ import annotations

import copy
import os
from collections import Counter, defaultdict

import pandas as pd
import pm4py
from lxml import etree
from pm4py.algo.analysis.woflan import algorithm as woflan

from .config import SYSTEM_TYPES, TASK_TAGS

NS = {"bpmn": "http://www.omg.org/spec/BPMN/20100524/MODEL"}
DI_EDGE = "{http://www.omg.org/spec/BPMN/20100524/DI}BPMNEdge"


def parse_bpmn(path: str) -> dict:
    """Đọc BPMN thành đồ thị, giữ những thông tin pm4py bỏ qua: làn, loại công việc, nhãn nhánh."""
    tree = etree.parse(path)
    proc = tree.find(".//bpmn:process", NS)
    lane_of = {}
    for lane in proc.findall(".//bpmn:lane", NS):
        for ref in lane.findall("bpmn:flowNodeRef", NS):
            lane_of[ref.text] = lane.get("name")
    nodes, flows = {}, {}
    for el in proc:
        tag = etree.QName(el).localname
        if tag in ("laneSet", "sequenceFlow") or not el.get("id"):
            continue
        nodes[el.get("id")] = dict(id=el.get("id"), type=tag, name=(el.get("name") or "").strip(),
                                   lane=lane_of.get(el.get("id"), "Không có lane"))
    for f in proc.findall("bpmn:sequenceFlow", NS):
        flows[f.get("id")] = dict(id=f.get("id"), src=f.get("sourceRef"), tgt=f.get("targetRef"),
                                  name=(f.get("name") or "").strip())
    out_, in_ = defaultdict(list), defaultdict(list)
    for f in flows.values():
        out_[f["src"]].append(f["id"])
        in_[f["tgt"]].append(f["id"])
    tasks = [n["name"] for n in nodes.values() if n["type"] in TASK_TAGS]
    lanes = sorted({n["lane"] for n in nodes.values() if n["type"] in TASK_TAGS})
    return dict(name=proc.get("name"), nodes=nodes, flows=flows, out=out_, inn=in_,
                tree=tree, path=path, tasks=tasks, lanes=lanes)


def element_table(M: dict) -> pd.DataFrame:
    df = pd.DataFrame(M["nodes"].values())
    df["vào"] = df["id"].map(lambda i: len(M["inn"][i]))
    df["ra"] = df["id"].map(lambda i: len(M["out"][i]))
    return df[["id", "type", "name", "lane", "vào", "ra"]]


def flow_table(M: dict) -> pd.DataFrame:
    return pd.DataFrame([dict(id=f["id"], tu=M["nodes"][f["src"]]["name"], den=M["nodes"][f["tgt"]]["name"],
                              nhan=f["name"]) for f in M["flows"].values()])


def structural_issues(M: dict) -> pd.DataFrame:
    """Dò các mẫu lỗi thường gặp khi mô tả quy trình bằng lời."""
    iss = []
    N = M["nodes"]
    for n in N.values():
        o, i = len(M["out"][n["id"]]), len(M["inn"][n["id"]])
        if n["type"] in TASK_TAGS and o > 1:
            iss.append(("Rẽ nhánh ngầm (task >1 luồng ra)", n["name"], f"{o} luồng ra → chạy song song ngầm"))
        if n["type"] in TASK_TAGS and i > 1:
            iss.append(("Hội tụ ngầm (task >1 luồng vào)", n["name"], f"{i} luồng vào, không có cổng hợp nhất"))
        if n["type"] == "exclusiveGateway" and o > 1:
            labels = [M["flows"][f]["name"] for f in M["out"][n["id"]]]
            if any(not lb for lb in labels):
                iss.append(("Nhánh XOR thiếu nhãn", n["name"], str(labels)))
            dup = [lb for lb, c in Counter(labels).items() if lb and c > 1]
            if dup:
                iss.append(("Nhánh XOR trùng nhãn", n["name"], f"{dup} xuất hiện >1 lần"))
        if n["type"] == "parallelGateway" and o > 1 and i > 1:
            iss.append(("Cổng song song vừa tách vừa hợp", n["name"], ""))
        if n["type"] in SYSTEM_TYPES and not any(k in n["lane"].lower()
                                                 for k in ["hệ thống", "he_thong", "he thong", "system"]):
            iss.append(("Task hệ thống nằm ở lane người", n["name"],
                        f"lane '{n['lane']}' – nếu thực tế do người làm thì nên là task/userTask, nếu không sẽ không có hàng đợi"))
        if n["lane"] == "Không có lane":
            iss.append(("Phần tử không thuộc lane", n["name"] or n["id"], ""))
    for f in M["flows"].values():
        if f["name"].lower() in ("nhãn nhánh", "label", "nhan nhanh"):
            iss.append(("Nhãn giữ chỗ chưa sửa", f["name"], f"{N[f['src']]['name']} → {N[f['tgt']]['name']}"))
    return pd.DataFrame(iss, columns=["van_de", "phan_tu", "chi_tiet"])


def to_petri(path: str):
    """Đọc BPMN bằng pm4py và chuyển sang mạng Petri (workflow net)."""
    bpmn_obj = pm4py.read_bpmn(path)
    net, im, fm = pm4py.convert_to_petri_net(bpmn_obj)
    return bpmn_obj, net, im, fm


def is_sound(net, im, fm) -> bool:
    return bool(woflan.apply(net, im, fm, parameters={"print_diagnostics": False,
                                                      "return_asap_when_not_sound": True}))


def sample_traces(net, im, fm, n: int = 30, top: int = 6) -> pd.DataFrame:
    """Phát ngẫu nhiên vài vết từ mạng Petri để xem mô hình cho phép hành vi nào."""
    pl = pm4py.play_out(net, im, fm, parameters={"noTraces": n})
    cnt = Counter(" → ".join(e["concept:name"] for e in t) for t in pl)
    return pd.DataFrame(cnt.most_common(top), columns=["vet", "so_lan"])


def reachable_tasks(M: dict, from_ids, direction: str = "out") -> set:
    """Công việc đầu tiên gặp khi đi từ các nút cho trước (bỏ qua cổng và sự kiện)."""
    found, stack, seen = set(), list(from_ids), set()
    while stack:
        nid = stack.pop()
        for f in M[direction][nid]:
            x = M["flows"][f]["tgt" if direction == "out" else "src"]
            if x in seen:
                continue
            seen.add(x)
            if M["nodes"][x]["type"] in TASK_TAGS:
                found.add(M["nodes"][x]["name"])
            else:
                stack.append(x)
    return found


def start_end_tasks(M: dict):
    starts = reachable_tasks(M, [n for n, v in M["nodes"].items() if v["type"] == "startEvent"], "out")
    ends = reachable_tasks(M, [n for n, v in M["nodes"].items() if v["type"] == "endEvent"], "inn")
    return starts, ends


def build_tobe_bpmn(M: dict, changes, out_dir: str, automate: str = "", repair_flows=()) -> tuple[dict, str]:
    """Ghi tệp BPMN TO-BE.

    C0: xoá các sequenceFlow trong `repair_flows` (kèm tham chiếu incoming/outgoing và cạnh vẽ).
    C3: đổi bước `automate` thành serviceTask.
    C1, C2 chỉ thay tham số mô phỏng nên không đổi tệp BPMN.
    """
    tree = copy.deepcopy(M["tree"])
    proc = tree.find(".//bpmn:process", NS)
    if "C0" in changes:
        for fid in repair_flows:
            for el in list(proc.iter()):
                if el.text == fid and etree.QName(el).localname in ("incoming", "outgoing"):
                    el.getparent().remove(el)
            f = proc.find(f"bpmn:sequenceFlow[@id='{fid}']", NS)
            if f is not None:
                f.getparent().remove(f)
            for e in list(tree.iter(DI_EDGE)):
                if e.get("bpmnElement") == fid:
                    e.getparent().remove(e)
    if "C3" in changes and automate:
        for el in proc:
            if el.get("name") == automate and etree.QName(el).localname in TASK_TAGS:
                el.tag = f"{{{NS['bpmn']}}}serviceTask"
    os.makedirs(out_dir, exist_ok=True)
    path = os.path.join(out_dir, f"TO_BE_{'_'.join(sorted(changes)) or 'none'}.bpmn")
    tree.write(path, xml_declaration=True, encoding="UTF-8", pretty_print=True)
    return parse_bpmn(path), path
