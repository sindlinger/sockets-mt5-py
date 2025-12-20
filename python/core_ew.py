"""Análise de ondas (opcional, depende de ew_adapter)."""

try:
    import ew_adapter
except Exception:
    ew_adapter = None


def ew_analyze(bars, params):
    if ew_adapter is None:
        return False, "ew_adapter não importado"
    try:
        res = ew_adapter.analyze(bars, params or {})
        return True, {"waves": res.get("waves", []), "summary": res.get("summary", {})}
    except Exception as e:
        return False, str(e)

