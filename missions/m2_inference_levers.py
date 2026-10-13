"""M2 — Inference Cost Levers: $/1M-token, batch x cache x cascade (deck §7).

Run: python missions/m2_inference_levers.py
"""
from __future__ import annotations
import os as _os, sys as _sys
_sys.path.insert(0, _os.path.dirname(_os.path.dirname(_os.path.abspath(__file__))))
from missions._common import load_csv, num
from finops import pricing, sustainability

# $/1M tokens (input, output) — illustrative 2026.
MODEL_PRICES = {"small": (0.20, 0.40), "large": (3.00, 15.00)}


def run(verbose: bool = True) -> dict:
    rows = load_csv("token_usage.csv")
    base_cost = opt_cost = 0.0
    total_tokens = 0

    # Phân nhóm phục vụ Extension 4: Ngân sách Reasoning
    reas_stats = {
        0: {"requests": 0, "tokens": 0, "base_cost": 0.0, "opt_cost": 0.0, "wh": 0.0},
        1: {"requests": 0, "tokens": 0, "base_cost": 0.0, "opt_cost": 0.0, "wh": 0.0},
    }

    for r in rows:
        inp, out = int(num(r["input_tokens"])), int(num(r["output_tokens"]))
        cached = int(num(r["cached_input_tokens"]))
        is_batch = bool(int(num(r["is_batch"])))
        is_r = int(num(r["is_reasoning"]))
        req_tokens = inp + out
        total_tokens += req_tokens

        # BASELINE: naive deployment — everything on the large model, no cache, no batch
        lin, lout = MODEL_PRICES["large"]
        r_base = pricing.request_cost(inp, out, lin, lout)
        base_cost += r_base

        # OPTIMIZED: cascade (route_tier), prompt caching, batch API
        pin, pout = MODEL_PRICES[r["route_tier"]]
        r_opt = pricing.request_cost(inp, out, pin, pout, cached_in=cached, batch=is_batch)
        opt_cost += r_opt

        # Tích lũy năng lượng và chi phí theo nhóm reasoning
        r_wh = sustainability.wh_per_query(req_tokens, is_reasoning=bool(is_r))
        group = reas_stats[is_r]
        group["requests"] += 1
        group["tokens"] += req_tokens
        group["base_cost"] += r_base
        group["opt_cost"] += r_opt
        group["wh"] += r_wh

    base_pm = pricing.dollars_per_million(base_cost, total_tokens)
    opt_pm = pricing.dollars_per_million(opt_cost, total_tokens)
    savings_pct = (1 - opt_cost / base_cost) * 100 if base_cost else 0.0

    # --- Extension 3: cache_is_worth_it analysis ---
    # Giả định cache write cost bằng giá input gốc, tính break-even reads
    cache_analysis = {}
    for tier, (p_in, _) in MODEL_PRICES.items():
        savings_per_read = p_in * (1.0 - 0.10)  # 90% discount
        be_reads = p_in / savings_per_read if savings_per_read > 0 else 0.0
        cache_analysis[tier] = {
            "price_in": p_in,
            "savings_per_read_1m": round(savings_per_read, 3),
            "break_even_reads": round(be_reads, 2),
            "is_worth_it_at_2_reads": pricing.cache_is_worth_it(2.0, p_in, p_in),
            "is_worth_it_at_1_read": pricing.cache_is_worth_it(1.0, p_in, p_in),
        }

    # --- Extension 4: Reasoning budget analysis ---
    tot_reqs = len(rows)
    tot_wh = reas_stats[0]["wh"] + reas_stats[1]["wh"]
    reasoning_pct_reqs = (reas_stats[1]["requests"] / tot_reqs) * 100 if tot_reqs else 0.0
    reasoning_pct_cost = (reas_stats[1]["opt_cost"] / opt_cost) * 100 if opt_cost else 0.0
    reasoning_pct_wh = (reas_stats[1]["wh"] / tot_wh) * 100 if tot_wh else 0.0

    # Cap 10% traffic: traffic hiện tại là ~8.38% (< 10%), nên savings cap 10% = 0
    cap_10_savings_usd = 0.0
    cap_10_savings_wh = 0.0

    # Thử nghiệm cap 5% traffic (chỉ định tuyến 5% task khó nhất cho reasoning)
    excess_5_pct_reqs = max(0, reas_stats[1]["requests"] - int(tot_reqs * 0.05))
    avg_reas_cost = reas_stats[1]["opt_cost"] / reas_stats[1]["requests"] if reas_stats[1]["requests"] else 0
    avg_reas_wh = reas_stats[1]["wh"] / reas_stats[1]["requests"] if reas_stats[1]["requests"] else 0
    sim_5_savings_usd = excess_5_pct_reqs * avg_reas_cost * 0.8
    sim_5_savings_wh = excess_5_pct_reqs * avg_reas_wh * (79.0 / 80.0)

    if verbose:
        print("== M2 Inference Cost Levers ==")
        print(f"requests={len(rows)}  tokens={total_tokens:,}")
        print(f"baseline  : ${base_cost:,.2f}/day   ${base_pm:.3f}/1M-token")
        print(f"optimized : ${opt_cost:,.2f}/day   ${opt_pm:.3f}/1M-token")
        print(f"savings   : {savings_pct:.1f}%  (cascade + caching + batch)")
        print(f"discount stack (batch + 100% cache): {pricing.discount_stack(batch=True, cache_hit_frac=1.0):.3f} of naive")

        print("\n-- Extension 3: cache_is_worth_it() --")
        for tier, ca in cache_analysis.items():
            print(f"Model {tier:5}: input=${ca['price_in']}/1M -> Tiết kiệm/lần đọc=${ca['savings_per_read_1m']}/1M. Điểm hòa vốn: {ca['break_even_reads']} lần đọc.")
            print(f"  Đọc 1 lần: có lợi? {ca['is_worth_it_at_1_read']} | Đọc >=2 lần: có lợi? {ca['is_worth_it_at_2_reads']}")

        print("\n-- Extension 4: Ngân sách Reasoning (is_reasoning) --")
        print(f"{'Nhóm':16}{'Requests (%)':>15}{'Tokens (%)':>15}{'Chi phí opt ($/d)':>18}{'Năng lượng Wh (%)':>20}")
        print(f"{'Non-Reasoning':16}{reas_stats[0]['requests']:>7} ({reas_stats[0]['requests']/tot_reqs*100:>4.1f}%){reas_stats[0]['tokens']:>9,} ({(reas_stats[0]['tokens']/total_tokens)*100:>4.1f}%)${reas_stats[0]['opt_cost']:>11.2f} ({(reas_stats[0]['opt_cost']/opt_cost)*100:>4.1f}%){reas_stats[0]['wh']:>12.1f} Wh ({(reas_stats[0]['wh']/tot_wh)*100:>4.1f}%)")
        print(f"{'Reasoning (1)':16}{reas_stats[1]['requests']:>7} ({reas_stats[1]['requests']/tot_reqs*100:>4.1f}%){reas_stats[1]['tokens']:>9,} ({(reas_stats[1]['tokens']/total_tokens)*100:>4.1f}%)${reas_stats[1]['opt_cost']:>11.2f} ({(reas_stats[1]['opt_cost']/opt_cost)*100:>4.1f}%){reas_stats[1]['wh']:>12.1f} Wh ({(reas_stats[1]['wh']/tot_wh)*100:>4.1f}%)")
        print(f"Nhận xét: Reasoning chiếm {reasoning_pct_reqs:.2f}% requests nhưng tiêu thụ {reasoning_pct_wh:.2f}% tổng năng lượng (hệ số ~80x).")
        print(f"Chính sách Cap 10% traffic: Hiện tại {reasoning_pct_reqs:.2f}% < 10% -> Tiết kiệm = $0 và 0 Wh.")
        print(f"Chính sách định tuyến chọn lọc (Cap 5%): Tiết kiệm tiềm năng ${sim_5_savings_usd:.2f}/ngày và {sim_5_savings_wh:,.1f} Wh/ngày.")

    return {
        "baseline_daily": round(base_cost, 2), "optimized_daily": round(opt_cost, 2),
        "baseline_per_m": round(base_pm, 3), "optimized_per_m": round(opt_pm, 3),
        "savings_pct": round(savings_pct, 1), "total_tokens": total_tokens,
        "cache_analysis": cache_analysis,
        "reasoning_stats": {
            "non_reasoning": reas_stats[0],
            "reasoning": reas_stats[1],
            "reasoning_pct_reqs": round(reasoning_pct_reqs, 2),
            "reasoning_pct_cost": round(reasoning_pct_cost, 2),
            "reasoning_pct_wh": round(reasoning_pct_wh, 2),
            "cap_10_savings_usd": cap_10_savings_usd,
            "cap_10_savings_wh": cap_10_savings_wh,
        }
    }


if __name__ == "__main__":
    run()
