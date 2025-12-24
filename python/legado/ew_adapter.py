"""
ew_adapter.py
-------------
Adaptador usando ElliottWaveAnalyzer (Python) para detectar ondas impulsivas (12345) ou corretivas (ABC) via socket.

Entrada (cmd = ew_analyze):
{
  "cmd": "ew_analyze",
  "bars": [ {"time": 1700000000, "open":..., "high":..., "low":..., "close":...}, ...],
  "params": {
     "max_skip": 8,          # WaveOptions up_to
     "max_results": 5,       # nº máximo de padrões retornados
     "mode": "impulse",     # impulse | correction | both
     "verbose": false
  }
}

Saída:
{
  "ok": true,
  "waves": [ {"label":"1","idx_start":i0,"idx_end":i1,"dir":"up","price_start":p0,"price_end":p1}, ... ],
  "summary": {"patterns":N, "checked":M, "mode":..., "idx_start":...}
}

Se não conseguir importar ElliottWaveAnalyzer, retorna erro.
"""
from __future__ import annotations
from typing import List, Dict, Any
import sys, os

# tentar localizar o repo ElliottWaveAnalyzer
ROOT_CANDIDATES = [
    os.path.join(os.path.dirname(__file__), "ElliottWaveAnalyzer"),
    "/tmp/ElliottWaveAnalyzer",
]
for _p in ROOT_CANDIDATES:
    if os.path.isdir(_p) and _p not in sys.path:
        sys.path.insert(0, _p)

try:
    import pandas as pd
    import numpy as np
    from models.WaveAnalyzer import WaveAnalyzer
    from models.WaveOptions import WaveOptionsGenerator5, WaveOptionsGenerator3
    from models.WaveRules import Impulse, LeadingDiagonal, Correction
    from models.WavePattern import WavePattern
    HAVE_EW = True
    _IMPORT_ERR = None
except Exception as e:
    HAVE_EW = False
    _IMPORT_ERR = str(e)


def _bars_to_df(bars: List[Dict[str, Any]]):
    df = pd.DataFrame(bars)
    df = df.rename(columns={"time": "Date", "open": "Open", "high": "High", "low": "Low", "close": "Close"})
    df["Date"] = pd.to_datetime(df["Date"], unit="s", errors="coerce").fillna(method="ffill")
    return df[["Date", "Open", "High", "Low", "Close"]]


def _extract_pattern(wavepattern) -> List[Dict[str, Any]]:
    out = []
    for w in wavepattern.waves:
        out.append({
            "label": w.label,
            "idx_start": int(w.idx_start),
            "idx_end": int(w.idx_end),
            "dir": "up" if getattr(w, "direction", "up") == "up" else "down",
            "price_start": float(w.price_start),
            "price_end": float(w.price_end),
        })
    return out


def analyze(bars: List[Dict[str, Any]], params: Dict[str, Any]) -> Dict[str, Any]:
    if not HAVE_EW:
        return {"ok": False, "error": f"ElliottWaveAnalyzer não importado: {_IMPORT_ERR}"}
    if not bars:
        return {"ok": False, "error": "sem barras"}

    mode = (params.get("mode") or "impulse").lower()
    max_skip = int(params.get("max_skip", 8))
    max_results = int(params.get("max_results", 5))
    verbose = bool(params.get("verbose", False))

    bars = sorted(bars, key=lambda x: x.get("time", 0))
    df = _bars_to_df(bars)
    wa = WaveAnalyzer(df=df, verbose=verbose)

    results = []
    checked = 0
    idx_start = int(np.argmin(np.array(df["Low"])))

    if mode in ("impulse", "both"):
        gen5 = WaveOptionsGenerator5(up_to=max_skip)
        rules = [Impulse("impulse"), LeadingDiagonal("leading_diagonal")]
        for opt in gen5.options_sorted:
            checked += 1
            try:
                waves = wa.find_impulsive_wave(idx_start=idx_start, wave_config=opt.values)
            except Exception:
                waves = False
            if waves:
                wp = WavePattern(waves, verbose=False)
                for rule in rules:
                    if wp.check_rule(rule):
                        results.append(_extract_pattern(wp))
                        break
            if len(results) >= max_results:
                break

    if mode in ("correction", "both") and len(results) < max_results:
        gen3 = WaveOptionsGenerator3(up_to=max_skip)
        rule_corr = Correction("correction")
        for opt in gen3.options_sorted:
            checked += 1
            try:
                waves = wa.find_corrective_wave(idx_start=idx_start, wave_config=opt.values)
            except Exception:
                waves = False
            if waves:
                wp = WavePattern(waves, verbose=False)
                if wp.check_rule(rule_corr):
                    results.append(_extract_pattern(wp))
            if len(results) >= max_results:
                break

    if not results:
        return {"ok": True, "waves": [], "summary": {"patterns": 0, "checked": checked, "mode": mode}}

    best = results[0]
    return {
        "ok": True,
        "waves": best,
        "summary": {
            "patterns": len(results),
            "checked": checked,
            "mode": mode,
            "idx_start": idx_start
        }
    }


if __name__ == "__main__":
    import math
    sample = []
    for i in range(200):
        price = math.sin(i/10) + i*0.001
        sample.append({"time": i, "open": price, "high": price+0.02, "low": price-0.02, "close": price})
    out = analyze(sample, {"mode": "impulse", "max_skip": 5, "max_results": 1})
    print(out)
