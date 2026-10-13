"""Unit tests for Lab 25 Extensions:
- Extension 2: MBU Right-sizing
- Extension 3: cache_is_worth_it()
- Extension 4: Reasoning budget
"""
import os
import sys
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

from finops import pricing, metrics, sustainability
from missions import m1_efficiency_audit, m2_inference_levers


def test_cache_is_worth_it_break_even():
    # 90% discount on $3.00/1M -> savings = $2.70/read
    # If write cost = $3.00, break even reads = 3.0 / 2.7 = 1.11 reads
    assert pricing.cache_is_worth_it(avg_cache_reads=1.0, write_cost_per_m=3.0, input_price_per_m=3.0) is False
    assert pricing.cache_is_worth_it(avg_cache_reads=1.11, write_cost_per_m=3.0, input_price_per_m=3.0) is False
    assert pricing.cache_is_worth_it(avg_cache_reads=2.0, write_cost_per_m=3.0, input_price_per_m=3.0) is True


def test_cache_is_worth_it_zero_or_negative():
    assert pricing.cache_is_worth_it(avg_cache_reads=5.0, write_cost_per_m=3.0, input_price_per_m=0.0) is False
    assert pricing.cache_is_worth_it(avg_cache_reads=5.0, write_cost_per_m=3.0, input_price_per_m=3.0, cache_discount=1.0) is False


def test_m1_extension_right_sizing():
    r1 = m1_efficiency_audit.run(verbose=False)
    assert "rightsize_recommendations" in r1
    assert "vram_economics" in r1
    assert r1["rightsize_monthly_savings"] > 0
    # gpu-h100-4 must be recommended to downsize to A100
    h100_rec = [r for r in r1["rightsize_recommendations"] if r["gpu_id"] == "gpu-h100-4"]
    assert len(h100_rec) == 1
    assert h100_rec[0]["target_type"] == "A100"


def test_m2_extension_reasoning_and_cache():
    r2 = m2_inference_levers.run(verbose=False)
    assert "reasoning_stats" in r2
    assert "cache_analysis" in r2
    stats = r2["reasoning_stats"]
    assert stats["reasoning_pct_reqs"] < 10.0
    assert stats["cap_10_savings_usd"] == 0.0
    assert stats["reasoning_pct_wh"] > 90.0  # ~94% energy
