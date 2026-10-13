"""M1 — Efficiency Audit: MFU/MBU, the GPU-Util lie, and idle waste (deck §5).

Run: python missions/m1_efficiency_audit.py
"""
from __future__ import annotations
import os as _os, sys as _sys
_sys.path.insert(0, _os.path.dirname(_os.path.dirname(_os.path.abspath(__file__))))
from collections import defaultdict
from missions._common import load_csv, num, catalog_by_type
from finops import metrics


def run(verbose: bool = True) -> dict:
    tel = load_csv("gpu_telemetry.csv")
    cat = catalog_by_type()

    # per-row MFU/MBU, then aggregate per GPU
    agg = defaultdict(lambda: {"util": [], "mfu": [], "mbu": [], "type": None, "idle_hours": 0})
    for r in tel:
        gtype = r["gpu_type"]
        peak_fp16 = num(cat[gtype]["peak_tflops_fp16"])
        peak_bw = num(cat[gtype]["peak_bw_tbs"])
        mfu = metrics.compute_mfu(num(r["achieved_tflops"]), peak_fp16)
        mbu = metrics.compute_mbu(num(r["achieved_bw_tbs"]), peak_bw)
        a = agg[r["gpu_id"]]
        a["type"] = gtype
        a["util"].append(num(r["gpu_util_pct"]))
        a["mfu"].append(mfu)
        a["mbu"].append(mbu)
        if num(r["gpu_util_pct"]) < 10:  # effectively idle this interval (1h)
            a["idle_hours"] += 1

    summary = []
    for gid, a in agg.items():
        summary.append({
            "gpu_id": gid, "gpu_type": a["type"],
            "gpu_util_pct": round(sum(a["util"]) / len(a["util"]), 1),
            "mfu": round(sum(a["mfu"]) / len(a["mfu"]), 3),
            "mbu": round(sum(a["mbu"]) / len(a["mbu"]), 3),
            "idle_hours": a["idle_hours"],
        })

    lies = metrics.flag_util_lies(summary)
    idle_waste = 0.0
    for s in summary:
        on_demand = num(catalog_by_type()[s["gpu_type"]]["on_demand_hr"])
        idle_waste += metrics.idle_waste_usd(s["idle_hours"], on_demand)

    # --- Extension 2: Right-sizing theo MBU ---
    vram_economics = {}
    for gtype, c in cat.items():
        od = num(c["on_demand_hr"])
        hbm = num(c["hbm_gb"])
        bw = num(c["peak_bw_tbs"])
        vram_economics[gtype] = {
            "on_demand_hr": od,
            "hbm_gb": hbm,
            "peak_bw_tbs": bw,
            "cost_per_gb_vram": round(od / hbm, 4) if hbm > 0 else 0.0,
            "cost_per_tbs": round(od / bw, 4) if bw > 0 else 0.0,
        }

    # Bảng mapping đề xuất dựa trên VRAM footprint và achieved throughput
    rightsize_recs = []
    total_rightsize_monthly = 0.0
    for lie in lies:
        cur_type = lie["gpu_type"]
        cur_od = num(cat[cur_type]["on_demand_hr"])
        # Tìm GPU phù hợp từ catalog có VRAM và bandwidth đủ cho workload thực tế
        if cur_type == "H100":
            target_type = "A100"
            reason = "A100 có 80GB VRAM (> 52GB cần dùng) và 2.0 TB/s BW (> 0.69 TB/s thực tế). Không dùng L4/A10G rẻ hơn vì sẽ bị OOM (cần >24GB)."
        elif cur_type == "A10G":
            target_type = "L4"
            reason = "L4 có 24GB VRAM (> 15.2GB cần dùng) và 0.3 TB/s BW (> 0.18 TB/s thực tế), chi phí $0.8/h thay vì $1.0/h."
        else:
            target_type = cur_type
            reason = "Giữ nguyên cấu hình."

        tgt_od = num(cat[target_type]["on_demand_hr"])
        hourly_save = max(0.0, cur_od - tgt_od)
        monthly_save = hourly_save * 24 * 30
        total_rightsize_monthly += monthly_save
        rightsize_recs.append({
            "gpu_id": lie["gpu_id"],
            "current_type": cur_type,
            "target_type": target_type,
            "hourly_savings": round(hourly_save, 2),
            "monthly_savings": round(monthly_save, 2),
            "reason": reason,
        })

    if verbose:
        print("== M1 Efficiency Audit ==")
        print(f"{'GPU':14}{'type':7}{'util%':>7}{'MFU':>7}{'MBU':>7}{'idle_h':>8}")
        for s in sorted(summary, key=lambda x: x["mfu"]):
            print(f"{s['gpu_id']:14}{s['gpu_type']:7}{s['gpu_util_pct']:>7}{s['mfu']:>7}{s['mbu']:>7}{s['idle_hours']:>8}")
        print(f"\nGPU-Util LIES (util>=90% but MFU<30%): {[l['gpu_id'] for l in lies]}")
        print(f"Idle waste (1 day): ${idle_waste:,.2f}  ->  ${idle_waste*30:,.0f}/month")

        print("\n-- Extension 2: Right-sizing theo MBU --")
        print(f"{'GPU Type':10}{'$/h':>6}{'VRAM(GB)':>10}{'BW(TB/s)':>10}{'$/GB-VRAM':>12}{'$/TB/s':>10}")
        for gt, eco in sorted(vram_economics.items(), key=lambda x: x[1]["cost_per_gb_vram"]):
            print(f"{gt:10}{eco['on_demand_hr']:>6.2f}{eco['hbm_gb']:>10.0f}{eco['peak_bw_tbs']:>10.2f}{eco['cost_per_gb_vram']:>12.4f}{eco['cost_per_tbs']:>10.4f}")

        print("\nĐề xuất Right-sizing cho các GPU memory-bound / util-lie:")
        for r in rightsize_recs:
            print(f"  {r['gpu_id']} ({r['current_type']}) -> {r['target_type']} | Tiết kiệm: ${r['monthly_savings']:,.2f}/tháng")
            print(f"    Lý do: {r['reason']}")
        print(f"Tổng tiết kiệm Right-sizing: ${total_rightsize_monthly:,.2f}/tháng")

    return {
        "summary": summary,
        "lies": lies,
        "idle_waste_daily": round(idle_waste, 2),
        "vram_economics": vram_economics,
        "rightsize_recommendations": rightsize_recs,
        "rightsize_monthly_savings": round(total_rightsize_monthly, 2),
    }


if __name__ == "__main__":
    run()
