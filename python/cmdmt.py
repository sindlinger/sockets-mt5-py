#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
CMD MT – CLI interativo unificado
- socket (default): host/porta (gateway 127.0.0.1:9095 ou serviço MQL 9090)
- file: cmd_*.txt / resp_*.txt (EA CommandListener/OficialTelnetListener)

Comandos:
  help
  exemplos [cmd]
  ping
  debug MSG
  use SYMBOL TF            (define contexto padrão)
  ctx                      (mostra contexto)
  open [SYMBOL] [TF]
  charts (alias listcharts)
  buy [SYMBOL] LOTS [sl] [tp]
  sell [SYMBOL] LOTS [sl] [tp]
  positions | trades
  tcloseall | closepos | closepositions
  applytpl [SYMBOL] [TF] TEMPLATE
  savetpl [SYMBOL] [TF] TEMPLATE
  closechart [SYMBOL] [TF]
  closeall
  attach (att) ind [SYMBOL] [TF] NAME [SUB|sub=N] [k=v ...] [-- k=v ...]
  deattach (dtt) ind [SYMBOL] [TF] NAME [SUB|sub=N]
  indtotal [SYMBOL] [TF] [SUB]
  indname [SYMBOL] [TF] [SUB] INDEX
  indhandle [SYMBOL] [TF] [SUB] NAME
  indget [SYMBOL] [TF] [SUB] SHORTNAME
  indrelease HANDLE
  findea NOME
  attach (att) ea [SYMBOL] [TF] NAME [k=v ...] [-- k=v ...]
  deattach (dtt) ea [SYMBOL] [TF]
  attach (att) run [SYMBOL] [TF] TEMPLATE
  gset NAME VALUE
  gget NAME
  gdel NAME
  gdelprefix PREFIX
  glist [PREFIX [LIMIT]]
  compile ARQUIVO|NOME
  compile service NOME
  service compile NOME
  compile here
  service start NOME
  service stop NOME
  service windows
  hotkeys / hotkey
  tester [--root PATH] [--ini FILE] [--timeout SEC] [--width W --height H] [--minimized|--headless] (default 640x480)
  run NOME --ind|--ea [SYMBOL] [TF] [3 dias] [--predownload] [--logtail N] [--quiet] (tester simples)
  logs [last|ARQUIVO.log] [N] (listar/mostrar logs do run)
  cmd TYPE [PARAMS...]     (envia TYPE direto)
  selftest [full]          (smoke test do serviço)
  raw <linha>
  json <json>
  quit
"""

import argparse
import json
import os
import random
import sys
import time
from datetime import datetime, timedelta
from pathlib import Path
import subprocess
import socket
import shlex
import re
import shutil
import signal
from collections import OrderedDict

BLUE_BG = "\033[44m"
WHITE   = "\033[97m"
RESET   = "\033[0m"

def set_blue():
    sys.stdout.write(BLUE_BG + WHITE)
    sys.stdout.flush()

def reset_color():
    sys.stdout.write(RESET)
    sys.stdout.flush()

def maybe_wslpath(p: str) -> str:
    p = p.strip().strip('"').strip("'")
    if not p:
        return p
    if p.startswith("/"):
        return p
    if ":" in p and ("\\" in p or p[1:3] == ":\\" or p[1:3] == ":/"):
        try:
            out = subprocess.check_output(["wslpath", "-u", p], stderr=subprocess.DEVNULL)
            return out.decode("utf-8", errors="replace").strip()
        except Exception:
            # fallback manual para WSL
            try:
                drive = p[0].lower()
                if p[1:3] in (":\\", ":/"):
                    rest = p[3:].replace("\\", "/")
                    return f"/mnt/{drive}/{rest}"
            except Exception:
                pass
            return p
    return p

def to_windows_path(p: str) -> str:
    p = p.strip().strip('"').strip("'")
    if not p:
        return p
    if os.name == "nt":
        return p
    if p.startswith("/"):
        try:
            out = subprocess.check_output(["wslpath", "-w", p], stderr=subprocess.DEVNULL)
            return out.decode("utf-8", errors="replace").strip()
        except Exception:
            return p
    return p

def _wsl_host_ip() -> str:
    try:
        if os.name == "nt":
            return ""
        ver = Path("/proc/version")
        if not ver.exists():
            return ""
        if "microsoft" not in ver.read_text().lower():
            return ""
        # prefer default gateway from /proc/net/route
        route = Path("/proc/net/route")
        if route.exists():
            for line in route.read_text().splitlines()[1:]:
                cols = line.split()
                if len(cols) >= 3 and cols[1] == "00000000":
                    gw_hex = cols[2]
                    try:
                        gw = int(gw_hex, 16)
                        ip = ".".join(str((gw >> (8 * i)) & 0xFF) for i in range(4))
                        if ip and ip != "0.0.0.0":
                            return ip
                    except Exception:
                        pass
        resolv = Path("/etc/resolv.conf")
        if not resolv.exists():
            return ""
        for line in resolv.read_text().splitlines():
            if line.startswith("nameserver"):
                parts = line.split()
                if len(parts) >= 2 and parts[1] != "127.0.0.1":
                    return parts[1]
    except Exception:
        return ""
    return ""

def gen_id() -> str:
    return f"{int(time.time()*1000)}_{random.randint(1000,9999)}"

def is_tf(tok: str) -> bool:
    t = tok.strip().upper()
    return t in ("M1","M5","M15","M30","H1","H4","D1","W1","MN1")

def is_number(tok: str) -> bool:
    try:
        float(tok)
        return True
    except Exception:
        return False

def ensure_ctx(ctx, need_sym=True, need_tf=True):
    if need_sym and not ctx.get("symbol"):
        print("defina SYMBOL com 'use SYMBOL TF' ou passe SYMBOL no comando ou --symbol")
        return False
    if need_tf and not ctx.get("tf"):
        print("defina TF com 'use SYMBOL TF' ou passe TF no comando ou --tf")
        return False
    return True

def parse_sym_tf(tokens, ctx):
    sym = None; tf = None; rest = tokens[:]
    if len(rest) >= 2 and is_tf(rest[1]):
        sym = rest[0]; tf = rest[1]; rest = rest[2:]
    elif len(rest) >= 1:
        if is_tf(rest[0]) and ctx.get("symbol"):
            sym = ctx.get("symbol"); tf = rest[0]; rest = rest[1:]
        else:
            sym = rest[0]; rest = rest[1:]
            tf = ctx.get("tf")
    else:
        sym = ctx.get("symbol"); tf = ctx.get("tf")
    return sym, tf, rest

def _parse_host_port(args, default_hosts, default_port):
    host = default_hosts
    port = default_port
    if len(args) >= 1:
        host = args[0]
    if len(args) >= 2 and args[1].isdigit():
        port = int(args[1])
    return host, port

def _parse_host_port_workers(args, default_hosts, default_port, default_workers):
    workers = default_workers
    args2 = list(args)
    # flags --workers / -w
    if "--workers" in args2:
        idx = args2.index("--workers")
        if idx + 1 < len(args2) and args2[idx + 1].lstrip("-").isdigit():
            workers = int(args2[idx + 1])
        del args2[idx:idx + 2]
    if "-w" in args2:
        idx = args2.index("-w")
        if idx + 1 < len(args2) and args2[idx + 1].lstrip("-").isdigit():
            workers = int(args2[idx + 1])
        del args2[idx:idx + 2]
    # positional third arg
    if len(args2) >= 3 and args2[2].lstrip("-").isdigit():
        workers = int(args2[2])
    host, port = _parse_host_port(args2, default_hosts, default_port)
    return host, port, workers

DEFAULT_SYMBOL = "EURUSD"
DEFAULT_TF = "H1"
DEFAULT_EA_BASE_TPL = "Moving Average.tpl"
DEBUG_TPL_ENV = "CMDMT_DEBUG_TPL"
DEFAULT_HOSTS = "host.docker.internal,127.0.0.1"
_wsl_ip = _wsl_host_ip()
if _wsl_ip:
    DEFAULT_HOSTS = f"{_wsl_ip},{DEFAULT_HOSTS}"
DEFAULT_PORT = 9090
# automação de serviços
CMDMT_SERVICE_AUTO_COMPILE = os.environ.get("CMDMT_SERVICE_AUTO_COMPILE", "1") != "0"
# handshake desabilitado por padrão (conexão direta no serviço)
CMDMT_HELLO_ENABLED = os.environ.get("CMDMT_HELLO", "0") != "0"
CMDMT_HELLO_LINE = os.environ.get("CMDMT_HELLO_LINE", "HELLO CMDMT")

def find_terminal_data_dir():
    # Allow override
    env = os.environ.get("CMDMT_MT5_DATA") or os.environ.get("MT5_DATA_DIR")
    if env:
        p = Path(maybe_wslpath(env))
        if p.exists():
            return p
    candidates = []
    if os.name == "nt":
        base = Path(os.environ.get("APPDATA", "")) / "MetaQuotes" / "Terminal"
        pattern = str(base / "*" / "MQL5" / "Services" / "SocketTelnetService.*")
        for svc in base.glob("*/MQL5/Services/SocketTelnetService.*"):
            candidates.append(svc)
    else:
        base = Path("/mnt/c/Users")
        for svc in base.glob("*/AppData/Roaming/MetaQuotes/Terminal/*/MQL5/Services/SocketTelnetService.*"):
            candidates.append(svc)
    if not candidates:
        return None
    # pick most recent service file
    svc = max(candidates, key=lambda p: p.stat().st_mtime)
    # .../Terminal/<id>/MQL5/Services/SocketTelnetService.*
    return svc.parents[2]

def find_mt5_compiler():
    # Allow override
    env = os.environ.get("CMDMT_MT5_COMPILE") or os.environ.get("MT5_COMPILE_EXE")
    if env:
        p = Path(maybe_wslpath(env))
        if p.exists():
            return str(p)
    # PATH lookup
    for exe in ("mt5-compile.exe", "MetaEditor64.exe"):
        w = shutil.which(exe)
        if w:
            return w
    # Common locations
    common = [
        "/mnt/c/Program Files/MetaTrader 5/MetaEditor64.exe",
        "/mnt/c/Program Files/Dukascopy MetaTrader 5/MetaEditor64.exe",
        "C:\\Program Files\\MetaTrader 5\\MetaEditor64.exe",
        "C:\\Program Files\\Dukascopy MetaTrader 5\\MetaEditor64.exe",
    ]
    for c in common:
        p = Path(maybe_wslpath(c))
        if p.exists():
            return str(p)
    return None

def resolve_mql5_candidates(target: str, term: Path):
    target = target.strip().strip('"').strip("'")
    if not target:
        return []
    t = target
    # Absolute path (POSIX or Windows)
    p0 = Path(target)
    if p0.is_absolute():
        p = p0
        if p.suffix.lower() != ".mq5":
            p = p.with_suffix(".mq5")
        if p.exists():
            return [p]
    # If path-like (Windows)
    if "/" in t or "\\" in t or ":" in t:
        t = t.replace("/", "\\")
        if t.lower().startswith("mql5\\"):
            t = t[5:]
        p = Path(maybe_wslpath(t))
        if not p.is_absolute():
            p = term / "MQL5" / Path(*t.split("\\"))
        if p.suffix.lower() != ".mq5":
            p = p.with_suffix(".mq5")
        if p.exists():
            return [p]
        return []
    # Try common folders first
    name = t
    if not name.lower().endswith(".mq5"):
        name = name + ".mq5"
    hits = []
    for sub in ("Experts", "Indicators", "Scripts", "Services"):
        p = term / "MQL5" / sub / name
        if p.exists():
            hits.append(p)
    if hits:
        return hits
    # Fallback: search anywhere in MQL5
    root = term / "MQL5"
    for p in root.rglob(name):
        if p.is_file():
            hits.append(p)
    return hits

def _is_blank_text_file(path: Path) -> bool:
    if not path.exists():
        return True
    try:
        data = path.read_bytes()
    except Exception:
        return False
    if not data:
        return True
    # best-effort decode and trim
    try:
        txt = data.decode("utf-8", "ignore")
    except Exception:
        try:
            txt = data.decode("latin-1", "ignore")
        except Exception:
            return False
    return txt.strip() == ""

def _rel_include_path(from_dir: Path, target: Path) -> str:
    rel = os.path.relpath(str(target), str(from_dir))
    return rel.replace("/", "\\")

def _stfft_indicator_stub(ind_name: str, buffers: int, include_path: str) -> str:
    if buffers < 0:
        buffers = 0
    colors = [
        "clrDodgerBlue",
        "clrOrangeRed",
        "clrSeaGreen",
        "clrGold",
        "clrViolet",
        "clrSlateBlue",
        "clrTomato",
        "clrDeepSkyBlue",
    ]
    prop = []
    if buffers > 0:
        prop.append(f"#property indicator_buffers {buffers}")
        prop.append(f"#property indicator_plots   {buffers}")
        for i in range(buffers):
            idx = i + 1
            color = colors[i % len(colors)]
            prop.append(f"#property indicator_type{idx}   DRAW_LINE")
            prop.append(f"#property indicator_color{idx}  {color}")
            prop.append(f"#property indicator_label{idx}  \"STFFT{idx}\"")
    else:
        prop.append("#property indicator_buffers 0")
        prop.append("#property indicator_plots   0")

    buf_decl = []
    buf_init = []
    buf_clear = []
    buf_copy = []
    if buffers > 0:
        for i in range(buffers):
            idx = i + 1
            buf_decl.append(f"double Buf{idx}[];")
            buf_init.append(f"  SetIndexBuffer({i}, Buf{idx}, INDICATOR_DATA);")
            buf_init.append(f"  ArraySetAsSeries(Buf{idx}, true);")
            buf_clear.append(f"""  for(int i=0;i<clearN;i++) Buf{idx}[i]=0.0;""")
            buf_copy.append(f"""  int off{idx} = {i} * seg;
  int len{idx} = out_count - off{idx};
  if(len{idx} > 0)
  {{
    int copyN = MathMin(len{idx}, rates_total);
    for(int i=0;i<copyN;i++) Buf{idx}[i] = out[off{idx}+i];
  }}""")

    prop_block = "\\n".join(prop)
    buf_decl_block = "\\n".join(buf_decl)
    buf_init_block = "\\n".join(buf_init)
    buf_clear_block = "\\n".join(buf_clear)
    buf_copy_block = "\\n\\n".join(buf_copy)

    return f"""//+------------------------------------------------------------------+
//| {ind_name}.mq5
//| Gerado por cmdmt (scaffold stfft)
//+------------------------------------------------------------------+
#property indicator_separate_window
{prop_block}
#property strict

#include \"{include_path}\"

input int    InpLen    = 1024;      // total de amostras enviadas
input int    InpWin    = 256;       // janela STFT
input int    InpHop    = 128;       // hop STFT
input bool   InpHalf   = true;
input bool   InpLog    = false;
input bool   InpNorm   = false;
input string InpWindow = \"hann\";  // hann|hamming|blackman|\"\" (none)
input bool   InpGPU    = true;
input bool   InpNewBarOnly = true;
input string InpHost = \"host.docker.internal\";
input int    InpPort = 9091;

{buf_decl_block}
static datetime last_bar = 0;

string BuildStfftName()
{{
  string name = \"stfft\";
  name += \"?n=\" + IntegerToString(InpWin);
  name += \"&hop=\" + IntegerToString(InpHop);
  name += \"&half=\" + (InpHalf?\"1\":\"0\");
  name += \"&log=\" + (InpLog?\"1\":\"0\");
  name += \"&norm=\" + (InpNorm?\"1\":\"0\");
  if(InpWindow!=\"\") name += \"&win=\" + InpWindow;
  if(InpGPU) name += \"&gpu=1\";
  return name;
}}

int OnInit()
{{
{buf_init_block}
  return INIT_SUCCEEDED;
}}

int OnCalculate(const int rates_total,
                const int prev_calculated,
                const datetime &time[],
                const double &open[],
                const double &high[],
                const double &low[],
                const double &close[],
                const long &tick_volume[],
                const long &volume[],
                const int &spread[])
{{
  int n = InpLen;
  if(n < InpWin) n = InpWin;
  if(n < 8) n = 8;
  if(rates_total < n) return 0;
  if(InpNewBarOnly)
  {{
    if(time[0]==last_bar) return rates_total;
    last_bar = time[0];
  }}

  double inbuf[];
  ArrayResize(inbuf, n);
  for(int i=0;i<n;i++) inbuf[i]=close[i];

  double out[];
  string err=\"\";
  string func = BuildStfftName();
  if(!PyBridgeCalcF64(inbuf, n, out, func, InpHost, InpPort, err))
    return rates_total;

  int out_count = ArraySize(out);
  if(out_count <= 0) return rates_total;
"""+(f"""
  int seg = out_count / {buffers};
  if(seg <= 0) seg = out_count;
  int clearN = MathMin(rates_total, seg);

{buf_clear_block}

{buf_copy_block}
""" if buffers > 0 else "")+"""
  return rates_total;
}}
"""

def _resolve_new_mq5_path(target: str, term: Path):
    t = target.strip()
    if not t:
        return None
    # Absolute or path-like
    if "/" in t or "\\" in t or ":" in t:
        t = t.replace("/", "\\")
        if t.lower().startswith("mql5\\"):
            t = t[5:]
        p = Path(maybe_wslpath(t))
        if not p.is_absolute():
            p = term / "MQL5" / Path(*t.split("\\"))
        if p.suffix.lower() != ".mq5":
            p = p.with_suffix(".mq5")
        return p
    # Name only -> Indicators root
    name = t
    if not name.lower().endswith(".mq5"):
        name += ".mq5"
    return term / "MQL5" / "Indicators" / name

def read_compile_log(log_path: Path):
    if not log_path.exists():
        return ""
    data = log_path.read_bytes()
    if data.startswith(b"\xff\xfe"):
        txt = data[2:].decode("utf-16-le", "ignore")
    elif data.startswith(b"\xfe\xff"):
        txt = data[2:].decode("utf-16-be", "ignore")
    else:
        txt = data.decode("utf-8", "ignore")
    return txt

def run_mt5_compile(target: str):
    term = find_terminal_data_dir()
    if not term:
        print("não encontrei o Terminal do MT5. Defina CMDMT_MT5_DATA ou MT5_DATA_DIR.")
        return False
    candidates = resolve_mql5_candidates(target, term)
    if not candidates:
        print("arquivo não encontrado. Informe o caminho completo ou o nome exato do .mq5.")
        return False
    if len(candidates) > 1:
        print("mais de um arquivo encontrado. Use o caminho completo:")
        for p in candidates:
            print(f"  {p}")
        return False
    src = candidates[0]

    compiler = find_mt5_compiler()
    if not compiler:
        print("MetaEditor/mt5-compile não encontrado. Defina CMDMT_MT5_COMPILE.")
        return False

    log_path = Path(os.getcwd()) / "mt5-compile.log"
    win_src = to_windows_path(str(src))
    win_log = to_windows_path(str(log_path))
    cmd = [compiler, f"/compile:{win_src}", f"/log:{win_log}"]
    try:
        subprocess.run(cmd, check=False)
    except Exception as e:
        print(f"falha ao executar compilador: {e}")
        return False

    txt = read_compile_log(log_path)
    if not txt:
        print("compilado, mas não consegui ler o log.")
        return True
    lines = [ln for ln in txt.splitlines() if ln.strip()]
    # print last summary and errors
    summary = ""
    errors = []
    warnings = []
    for ln in lines:
        low = ln.lower()
        if "result:" in low:
            summary = ln
        if " error" in low:
            if " 0 error" in low or " 0 errors" in low:
                continue
            errors.append(ln)
        elif " warning" in low:
            if " 0 warning" in low or " 0 warnings" in low:
                continue
            warnings.append(ln)
    if summary:
        print(summary)
    if errors:
        print("erros:")
        for ln in errors[-10:]:
            print("  " + ln)
    if warnings:
        print("warnings:")
        for ln in warnings[-10:]:
            print("  " + ln)
    return True

def _compile_log_has_errors(txt: str) -> bool:
    if not txt:
        return False
    # procura "Result: X errors"
    for ln in txt.splitlines():
        low = ln.lower()
        if "result:" in low and "error" in low:
            m = re.search(r"(\\d+)\\s+error", low)
            if m:
                try:
                    return int(m.group(1)) > 0
                except Exception:
                    return True
    # fallback: linhas com " error" (sem ser 0)
    for ln in txt.splitlines():
        low = ln.lower()
        if " error" in low and " 0 error" not in low:
            return True
    return False

def _find_service_mq5(name: str, term: Path):
    hits = resolve_mql5_candidates(name, term)
    if not hits:
        return None
    for p in hits:
        if "Services" in p.parts:
            return p
    return hits[0]

def ensure_service_compiled(name: str) -> bool:
    term = find_terminal_data_dir()
    if not term:
        print("não encontrei o Terminal do MT5. Defina CMDMT_MT5_DATA ou MT5_DATA_DIR.")
        return False
    svc = _find_service_mq5(name, term)
    if not svc or not svc.exists():
        print("serviço .mq5 não encontrado.")
        return False
    ex5 = svc.with_suffix(".ex5")
    need_compile = (not ex5.exists()) or (ex5.stat().st_mtime < svc.stat().st_mtime)
    if not need_compile:
        return True
    print("compilando serviço:", svc)
    ok = run_mt5_compile(str(svc))
    if not ok:
        return False
    # verifica ex5 e log
    if not ex5.exists():
        print("compilação falhou: EX5 não foi gerado.")
        return False
    log_txt = read_compile_log(Path(os.getcwd()) / "mt5-compile.log")
    if _compile_log_has_errors(log_txt):
        print("compilação com erros. Verifique mt5-compile.log")
        return False
    return True

def run_mt5_compile_service():
    term = find_terminal_data_dir()
    if not term:
        print("não encontrei o Terminal do MT5. Defina CMDMT_MT5_DATA ou MT5_DATA_DIR.")
        return False
    svc = term / "MQL5" / "Services" / "SocketTelnetService.mq5"
    if not svc.exists():
        print("serviço não encontrado. Informe o caminho completo.")
        return False
    return run_mt5_compile(str(svc))

def run_mt5_compile_service_name(name: str):
    term = find_terminal_data_dir()
    if not term:
        print("não encontrei o Terminal do MT5. Defina CMDMT_MT5_DATA ou MT5_DATA_DIR.")
        return False
    n = (name or "").strip().strip('"').strip("'")
    if not n:
        print("uso: compile service NOME")
        return False
    n = n.replace("/", "\\")
    if not n.lower().startswith("services\\"):
        n = "Services\\" + n
    if not n.lower().endswith(".mq5"):
        n += ".mq5"
    return run_mt5_compile(n)

def run_mt5_start_service(name: str):
    base = Path(__file__).resolve().parent.parent
    script = base / "scripts" / "mt5_start_service.sh"
    if not script.exists():
        print("script de start não encontrado: scripts/mt5_start_service.sh")
        return False
    svc = (name or "").strip()
    if not svc:
        print("uso: service start NOME")
        return False
    tokens = shlex.split(svc)
    svc_name = tokens[0] if tokens else ""
    extra = tokens[1:] if len(tokens) > 1 else []
    if not svc_name:
        print("uso: service start NOME")
        return False
    if CMDMT_SERVICE_AUTO_COMPILE:
        if not ensure_service_compiled(svc_name):
            return False
    try:
        env = os.environ.copy()
        if extra:
            env["UIA_ARGS"] = " ".join(extra)
        subprocess.run([str(script), svc_name, "Start"], env=env, check=False)
        return True
    except Exception as e:
        print(f"falha ao iniciar serviço: {e}")
        return False

def run_mt5_stop_service(name: str):
    base = Path(__file__).resolve().parent.parent
    script = base / "scripts" / "mt5_start_service.sh"
    if not script.exists():
        print("script de stop não encontrado: scripts/mt5_start_service.sh")
        return False

def run_mt5_list_service_windows():
    base = Path(__file__).resolve().parent.parent
    script = base / "scripts" / "mt5_start_service.sh"
    if not script.exists():
        print("script de listagem não encontrado: scripts/mt5_start_service.sh")
        return False
    try:
        subprocess.run([str(script), "SocketTelnetService", "List"], check=False)
        return True
    except Exception as e:
        print(f"falha ao listar janelas: {e}")
        return False
    svc = (name or "").strip()
    if not svc:
        print("uso: service stop NOME")
        return False
    tokens = shlex.split(svc)
    svc_name = tokens[0] if tokens else ""
    extra = tokens[1:] if len(tokens) > 1 else []
    if not svc_name:
        print("uso: service stop NOME")
        return False
    try:
        env = os.environ.copy()
        if extra:
            env["UIA_ARGS"] = " ".join(extra)
        subprocess.run([str(script), svc_name, "Stop"], env=env, check=False)
        return True
    except Exception as e:
        print(f"falha ao parar serviço: {e}")
        return False


def run_mt5_compile_all_services():
    return run_mt5_compile_service()

def _read_text_auto(path: Path):
    data = path.read_bytes()
    encoding = "utf-8"
    bom = b""
    if data.startswith(b"\xff\xfe"):
        encoding = "utf-16-le"
        bom = b"\xff\xfe"
        data = data[2:]
    elif data.startswith(b"\xfe\xff"):
        encoding = "utf-16-be"
        bom = b"\xfe\xff"
        data = data[2:]
    txt = data.decode(encoding, "ignore")
    return txt, encoding, bom

def _default_ini_map():
    # mapeamento base (chaves do exemplo) – cada chave pode ser sobrescrita via --set Section.Key=Valor
    m = OrderedDict()
    m["Common"] = OrderedDict([
        ("Login", ""),
        ("Password", ""),
        ("Server", ""),
        ("CertPassword", ""),
        ("ProxyEnable", "0"),
        ("ProxyType", "0"),
        ("ProxyAddress", ""),
        ("ProxyLogin", ""),
        ("ProxyPassword", ""),
        ("KeepPrivate", "1"),
        ("NewsEnable", "1"),
        ("CertInstall", "1"),
        ("MQL5Login", ""),
        ("MQL5Password", ""),
    ])
    m["Charts"] = OrderedDict([
        ("ProfileLast", ""),
        ("MaxBars", "50000"),
        ("PrintColor", "0"),
        ("SaveDeleted", "1"),
    ])
    m["Experts"] = OrderedDict([
        ("AllowLiveTrading", "0"),
        ("AllowDllImport", "0"),
        ("Enabled", "1"),
        ("Account", "0"),
        ("Profile", "0"),
    ])
    m["Objects"] = OrderedDict([
        ("ShowPropertiesOnCreate", "0"),
        ("SelectOneClick", "0"),
        ("MagnetSens", "10"),
    ])
    m["StartUp"] = OrderedDict([
        ("Expert", ""),
        ("ExpertParameters", ""),
        ("Script", ""),
        ("ScriptParameters", ""),
        ("Symbol", ""),
        ("Period", ""),
        ("Template", ""),
        ("ShutdownTerminal", "1"),
    ])
    m["Email"] = OrderedDict([
        ("Enable", "0"),
        ("Server", ""),
        ("Auth", ""),
        ("Login", ""),
        ("Password", ""),
        ("From", ""),
        ("To", ""),
    ])
    m["Tester"] = OrderedDict([
        ("Expert", ""),
        ("ExpertParameters", ""),
        ("Symbol", ""),
        ("Period", ""),
        ("Login", ""),
        ("Deposit", ""),
        ("Currency", ""),
        ("Leverage", ""),
        ("Model", "0"),
        ("ExecutionMode", "1"),
        ("Optimization", "0"),
        ("OptimizationCriterion", "0"),
        ("FromDate", ""),
        ("ToDate", ""),
        ("ForwardMode", "0"),
        ("ForwardDate", ""),
        ("Report", ""),
        ("ReplaceReport", "1"),
        ("Visual", "0"),
        ("UseLocal", "1"),
        ("UseRemote", "0"),
        ("UseCloud", "0"),
        ("Port", ""),
        ("ShutdownTerminal", "1"),
    ])
    return m

def _parse_ini_to_map(path: Path):
    base = _default_ini_map()
    try:
        txt, _, _ = _read_text_auto(path)
    except Exception:
        return base
    section = None
    for raw in txt.splitlines():
        line = raw.strip()
        if not line or line.startswith(";") or line.startswith("#"):
            continue
        if line.startswith("[") and line.endswith("]"):
            section = line[1:-1].strip()
            if section not in base:
                base[section] = OrderedDict()
            continue
        if "=" in line and section:
            k, v = line.split("=", 1)
            base.setdefault(section, OrderedDict())[k.strip()] = v.strip()
    return base

def _apply_overrides(ini_map, overrides):
    for sec, key, val in overrides:
        if not sec or not key:
            continue
        if sec not in ini_map:
            ini_map[sec] = OrderedDict()
        ini_map[sec][key] = val
    return ini_map

def _ini_map_to_text(ini_map):
    lines = []
    for sec, items in ini_map.items():
        lines.append(f"[{sec}]")
        for k, v in items.items():
            lines.append(f"{k}={v}")
        lines.append("")
    return "\n".join(lines).rstrip() + "\n"

def _parse_set_pairs(items):
    out = []
    for it in items:
        if "=" not in it:
            return None, f"formato invalido: {it} (use Section.Key=Valor)"
        left, val = it.split("=", 1)
        sec = None; key = None
        if "." in left:
            sec, key = left.split(".", 1)
        elif ":" in left:
            sec, key = left.split(":", 1)
        else:
            sec, key = "Tester", left
        out.append((sec.strip(), key.strip(), val))
    return out, ""

def _ini_set(root: Path, items):
    ini_path = root / "tester.ini"
    ini_map = _parse_ini_to_map(ini_path) if ini_path.exists() else _default_ini_map()
    overrides, err = _parse_set_pairs(items)
    if not overrides:
        return False, err
    ini_map = _apply_overrides(ini_map, overrides)
    # garante Tester.Login se Common.Login estiver setado
    try:
        c_login = str(ini_map.get("Common", {}).get("Login", "")).strip()
        t_login = str(ini_map.get("Tester", {}).get("Login", "")).strip()
        if c_login and not t_login:
            ini_map.setdefault("Tester", OrderedDict())["Login"] = c_login
    except Exception:
        pass
    _write_text_auto(ini_path, _ini_map_to_text(ini_map), "utf-8", b"")
    return True, str(ini_path)

def _ini_get(root: Path, items):
    ini_path = root / "tester.ini"
    ini_map = _parse_ini_to_map(ini_path) if ini_path.exists() else _default_ini_map()
    res = []
    for it in items:
        sec = None; key = None
        if "." in it:
            sec, key = it.split(".", 1)
        elif ":" in it:
            sec, key = it.split(":", 1)
        else:
            sec, key = "Tester", it
        sec = sec.strip(); key = key.strip()
        val = ""
        if sec in ini_map and key in ini_map[sec]:
            val = ini_map[sec][key]
            if sec.lower() == "common" and key.lower() == "password":
                val = "*****"
        res.append(f"{sec}.{key}={val}")
    return True, res

def _ini_list(root: Path):
    ini_path = root / "tester.ini"
    ini_map = _parse_ini_to_map(ini_path) if ini_path.exists() else _default_ini_map()
    lines = []
    for sec, items in ini_map.items():
        lines.append(f"[{sec}]")
        for k, v in items.items():
            val = v
            if sec.lower() == "common" and k.lower() == "password":
                val = "*****"
            lines.append(f"{k}={val}")
        lines.append("")
    return True, lines

def _ini_sync(root: Path):
    # copia Common.Login/Password/Server do Config/common.ini para tester.ini
    c_login, c_pass, c_srv = _read_common_credentials(root)
    if not (c_login and c_pass and c_srv):
        return False, "common.ini incompleto (Login/Password/Server)"
    ok, msg = _ini_set(root, [
        f"Common.Login={c_login}",
        f"Common.Password={c_pass}",
        f"Common.Server={c_srv}",
        f"Tester.Login={c_login}",
    ])
    if not ok:
        return False, msg
    return True, "synced"

def _write_text_auto(path: Path, text: str, encoding: str, bom: bytes):
    if encoding.startswith("utf-16"):
        data = text.encode(encoding, "ignore")
        if bom:
            data = bom + data
        path.write_bytes(data)
    else:
        path.write_text(text, encoding="utf-8", errors="ignore")

def _kill_terminal_processes(root: Path):
    try:
        exe = _find_terminal_exe(root)
        if not exe:
            return
        exe_path = to_windows_path(str(exe))
        # mata somente o terminal do caminho dedicado
        cmd = [
            "powershell.exe", "-NoProfile", "-Command",
            f"Get-Process terminal64 -ErrorAction SilentlyContinue | Where-Object {{$_.Path -eq '{exe_path}'}} | Stop-Process -Force"
        ]
        subprocess.run(cmd, check=False)
    except Exception:
        pass

def _list_windows_user_dirs():
    if os.name == "nt":
        base = Path(os.environ.get("USERPROFILE", "C:\\Users\\Public")).parent
    else:
        base = Path("/mnt/c/Users")
    if not base.exists():
        return []
    skip = {"Public", "Default", "Default User", "All Users", "desktop.ini"}
    users = []
    for p in base.iterdir():
        if p.is_dir() and p.name not in skip:
            users.append(p)
    return users

def _walk_depth(root: Path, max_depth: int = 3):
    root = Path(root)
    for path, dirs, files in os.walk(root):
        depth = len(Path(path).relative_to(root).parts)
        if depth > max_depth:
            dirs[:] = []
            continue
        yield Path(path), files

def _find_terminal_exe(root: Path):
    root = Path(root)
    if not root.exists():
        return None
    direct = root / "terminal64.exe"
    if direct.exists():
        return direct
    direct = root / "terminal.exe"
    if direct.exists():
        return direct
    for path, files in _walk_depth(root, max_depth=4):
        if "terminal64.exe" in files:
            return path / "terminal64.exe"
        if "terminal.exe" in files:
            return path / "terminal.exe"
    return None

def _find_ini(root: Path, ini_hint=None):
    root = Path(root)
    if ini_hint:
        p = Path(maybe_wslpath(ini_hint))
        if not p.is_absolute():
            p = root / ini_hint
        if p.exists():
            return p
    preferred = [
        "tester.ini",
        "tester_run.ini",
        "tester_indicator.ini",
        "test.ini",
        "config.ini",
        "terminal.ini",
    ]
    for name in preferred:
        p = root / name
        if p.exists():
            return p
    # fallback: first ini in root
    for p in root.glob("*.ini"):
        return p
    return None

def _find_rach_root():
    # caminho hardcoded: pasta Terminal dentro do repo
    repo = _find_repo_root(Path.cwd())
    if repo:
        p = repo / "Terminal"
        if p.exists():
            return p
        p2 = repo / "terminal"
        if p2.exists():
            return p2
        # fallback: Terminal no pai do repo
        p3 = repo.parent / "Terminal"
        if p3.exists():
            return p3
        p4 = repo.parent / "terminal"
        if p4.exists():
            return p4
    return None

def _patch_ini_window(src: Path, width=None, height=None):
    if not width and not height:
        return src
    txt, enc, bom = _read_text_auto(src)
    lines = txt.splitlines()
    width = width or 1024
    height = height or 720
    keys = {
        "WindowLeft": "0",
        "WindowTop": "0",
        "WindowWidth": str(width),
        "WindowHeight": str(height),
        "Maximized": "0",
    }
    out = []
    seen = {k: False for k in keys}
    in_common = False
    injected = False
    for ln in lines:
        stripped = ln.strip()
        if stripped.startswith("[") and stripped.endswith("]"):
            if in_common and not injected:
                for k, v in keys.items():
                    if not seen[k]:
                        out.append(f"{k}={v}")
                        seen[k] = True
                injected = True
            in_common = (stripped[1:-1].strip().lower() == "common")
            out.append(ln)
            continue
        if "=" in stripped and not stripped.startswith(";") and not stripped.startswith("#"):
            k, v = stripped.split("=", 1)
            k = k.strip()
            if k in keys:
                out.append(f"{k}={keys[k]}")
                seen[k] = True
                continue
        out.append(ln)
    if in_common and not injected:
        for k, v in keys.items():
            if not seen[k]:
                out.append(f"{k}={v}")
                seen[k] = True
        injected = True
    if not injected:
        out.append("[Common]")
        for k, v in keys.items():
            if not seen[k]:
                out.append(f"{k}={v}")
                seen[k] = True
    dst = src.with_name("cmdmt_tester.ini")
    _write_text_auto(dst, "\n".join(out) + "\n", enc, bom)
    return dst

def _tail_lines(path: Path, n: int = 200):
    try:
        txt, _, _ = _read_text_auto(path)
    except Exception:
        return []
    lines = txt.splitlines()
    return lines[-n:]

def _parse_time_sec(line: str):
    m = re.search(r"\\b(\\d{2}):(\\d{2}):(\\d{2})\\.(\\d{3})\\b", line)
    if not m:
        return None
    hh, mm, ss, ms = m.groups()
    return int(hh) * 3600 + int(mm) * 60 + int(ss) + int(ms) / 1000.0

def _filter_lines_since(lines, start_ts: float):
    try:
        start_dt = datetime.fromtimestamp(start_ts)
    except Exception:
        return lines
    start_sec = start_dt.hour * 3600 + start_dt.minute * 60 + start_dt.second + start_dt.microsecond / 1e6
    out = []
    for ln in lines:
        tsec = _parse_time_sec(ln)
        if tsec is None:
            out.append(ln)
            continue
        if tsec + 1.0 >= start_sec:  # tolerancia 1s
            out.append(ln)
    return out

def _latest_file(dir_path: Path, exts=None, after_ts=None):
    if not dir_path.exists():
        return None
    files = []
    for p in dir_path.iterdir():
        if not p.is_file():
            continue
        if exts and p.suffix.lower() not in exts:
            continue
        if after_ts and p.stat().st_mtime < after_ts - 1:
            continue
        files.append(p)
    if not files:
        return None
    return max(files, key=lambda p: p.stat().st_mtime)

def _latest_log_in_dirs(dirs):
    latest = None
    for d in dirs:
        cand = _latest_file(d, exts={".log"})
        if cand and (not latest or cand.stat().st_mtime > latest.stat().st_mtime):
            latest = cand
    return latest

def _filter_lines(lines, include=None, exclude=None):
    if not lines:
        return []
    out = lines
    if include:
        inc = [s.lower() for s in include]
        out = [ln for ln in out if any(s in ln.lower() for s in inc)]
    if exclude:
        exc = [s.lower() for s in exclude]
        out = [ln for ln in out if not any(s in ln.lower() for s in exc)]
    return out

def _print_block(title: str, lines):
    if not lines:
        return
    print(title)
    for ln in lines:
        print("  " + ln)

def _ensure_run_logs_dir():
    root = _find_repo_root(Path.cwd())
    if not root:
        root = Path.cwd()
    out = root / "run_logs"
    out.mkdir(parents=True, exist_ok=True)
    return out

def _append_run_log(path: Path, title: str, lines):
    with path.open("a", encoding="utf-8") as f:
        f.write(title + "\n")
        for ln in lines:
            f.write(ln + "\n")
        f.write("\n")

def _list_run_logs(limit=20):
    run_dir = _ensure_run_logs_dir()
    logs = sorted(run_dir.glob("run_*.log"), key=lambda p: p.stat().st_mtime, reverse=True)
    print(f"run_logs: {run_dir}")
    for p in logs[:limit]:
        print(f"  {p.name}")

def _show_run_log(name=None, tail=200):
    run_dir = _ensure_run_logs_dir()
    if name and name != "last":
        path = run_dir / name
    else:
        logs = sorted(run_dir.glob("run_*.log"), key=lambda p: p.stat().st_mtime, reverse=True)
        if not logs:
            print("run_logs vazio")
            return
        path = logs[0]
    lines = _tail_lines(path, tail)
    _print_block(f"log: {path}", lines)

def _follow_file(path: Path, include=None, exclude=None):
    try:
        with path.open("r", encoding="utf-8", errors="ignore") as f:
            f.seek(0, 2)
            while True:
                line = f.readline()
                if not line:
                    time.sleep(0.2)
                    continue
                line = line.rstrip("\n")
                if include and not any(s.lower() in line.lower() for s in include):
                    continue
                if exclude and any(s.lower() in line.lower() for s in exclude):
                    continue
                print(line)
    except KeyboardInterrupt:
        return

def _show_file_filtered(path: Path, title: str, tail: int, include=None, exclude=None, follow=False):
    if not path or not path.exists():
        print("log não encontrado")
        return
    want = max(tail * 5, 200) if tail > 0 else 200
    lines = _tail_lines(path, want)
    lines = _filter_lines(lines, include=include, exclude=exclude)
    if tail > 0 and len(lines) > tail:
        lines = lines[-tail:]
    _print_block(f"{title}: {path}", lines or ["(sem linhas)"])
    if follow:
        _follow_file(path, include=include, exclude=exclude)

def _show_mt5_log_filtered(term: Path, title: str, tail: int, include=None, exclude=None, follow=False):
    if not term:
        print("ERROR terminal_dir (defina CMDMT_MT5_DATA)")
        return
    log_path = _latest_log_in_dirs([term / "MQL5" / "Logs", term / "Logs"])
    if not log_path:
        print("logs MT5 não encontrados")
        return
    _show_file_filtered(log_path, title, tail, include=include, exclude=exclude, follow=follow)

def _normalize_prog_name(name):
    name = name.strip().strip('"').strip("'")
    return name.replace("/", "\\")

def _strip_ext(name):
    low = name.lower()
    if low.endswith(".ex5") or low.endswith(".mq5"):
        return name[:-4]
    return name

def _find_prog_in_dir(base, name):
    base = Path(base)
    if not base.exists():
        return None, None
    name = _normalize_prog_name(name)
    rel = _strip_ext(name)
    rel_path = Path(*rel.split("\\"))
    for ext in (".ex5", ".mq5"):
        cand = base / (str(rel_path) + ext)
        if cand.exists():
            return cand, rel
    target = rel_path.name
    for ext in (".ex5", ".mq5"):
        for p in base.rglob(target + ext):
            if p.is_file():
                rel2 = str(p.relative_to(base)).replace("/", "\\")
                rel2 = _strip_ext(rel2)
                return p, rel2
    return None, None

def _find_repo_root(start=None):
    p = Path(start or Path(__file__).resolve()).resolve()
    for _ in range(12):
        if (p / ".git").exists():
            return p
        if p.parent == p:
            break
        p = p.parent
    return None

def _find_prog_in_repo(kind, name):
    repo = _find_repo_root(Path.cwd())
    if not repo:
        return None, None
    for root in repo.rglob("MQL5"):
        base = root / kind
        if not base.exists():
            continue
        src, rel2 = _find_prog_in_dir(base, name)
        if src:
            return src, rel2
    return None, None

def _find_prog_in_terminal(kind, name, term_dir: Path):
    base = Path(term_dir) / "MQL5" / kind
    return _find_prog_in_dir(base, name)

def _read_common_credentials(data_dir: Path):
    for folder in ("config", "Config"):
        p = Path(data_dir) / folder / "common.ini"
        if p.exists():
            ini = _parse_ini_to_map(p)
            common = ini.get("Common", {})
            login = str(common.get("Login", "")).strip()
            password = str(common.get("Password", "")).strip()
            server = str(common.get("Server", "")).strip()
            return login, password, server
    return "", "", ""

def _ensure_dirs(data_dir):
    for sub in ("MQL5/Profiles/Tester", "MQL5/Experts", "MQL5/Indicators"):
        (Path(data_dir) / sub).mkdir(parents=True, exist_ok=True)

def _write_indicator_stub_set(data_dir, indicator_rel):
    tester_dir = Path(data_dir) / "MQL5" / "Profiles" / "Tester"
    tester_dir.mkdir(parents=True, exist_ok=True)
    set_path = tester_dir / "IndicatorStub.set"
    txt = f"IndicatorPath={indicator_rel}\nIndicatorParams=\n"
    set_path.write_text(txt, encoding="utf-8")
    return set_path

def _ensure_indicator_stub(data_dir):
    _ensure_dirs(data_dir)
    dst = Path(data_dir) / "MQL5" / "Experts" / "IndicatorStub.ex5"
    repo = _find_repo_root(Path.cwd())
    src_ex5 = None
    src_mq5 = None
    if repo:
        cand = repo / "IndicatorStub.ex5"
        cand_mq5 = repo / "IndicatorStub.mq5"
        if cand.exists():
            src_ex5 = cand
        if cand_mq5.exists():
            src_mq5 = cand_mq5
    if not src_ex5 or not src_mq5:
        # fallback: procura no diretório pai (mt5-shellscripts)
        try:
            parent = Path.cwd().resolve().parent
            cand = parent / "IndicatorStub.ex5"
            cand_mq5 = parent / "IndicatorStub.mq5"
            if cand.exists():
                src_ex5 = cand
            if cand_mq5.exists():
                src_mq5 = cand_mq5
        except Exception:
            pass
    if not src_ex5 and not src_mq5:
        return dst if dst.exists() else None

    # se existir mq5 mais novo, compila no diretório do terminal
    try:
        dst_mq5 = dst.with_suffix(".mq5")
        if src_mq5 and (not dst.exists() or not dst_mq5.exists() or src_mq5.stat().st_mtime > dst.stat().st_mtime):
            shutil.copy2(src_mq5, dst_mq5)
            _compile_mq5_path(dst_mq5)
    except Exception:
        pass

    # fallback: copia ex5 se necessário
    try:
        if src_ex5 and ((not dst.exists()) or (src_ex5.stat().st_mtime > dst.stat().st_mtime)):
            shutil.copy2(src_ex5, dst)
    except Exception:
        if not dst.exists():
            return None
    return dst

def _ensure_predownload_script(data_dir):
    scripts_dir = Path(data_dir) / "MQL5" / "Scripts"
    scripts_dir.mkdir(parents=True, exist_ok=True)
    dst_mq5 = scripts_dir / "CmdmtPreDownload.mq5"
    repo = _find_repo_root(Path.cwd())
    src_mq5 = None
    if repo:
        cand = repo / "CmdmtPreDownload.mq5"
        if cand.exists():
            src_mq5 = cand
    if not src_mq5:
        try:
            parent = Path.cwd().resolve().parent
            cand = parent / "CmdmtPreDownload.mq5"
            if cand.exists():
                src_mq5 = cand
        except Exception:
            src_mq5 = None
    if src_mq5:
        try:
            if (not dst_mq5.exists()) or (src_mq5.stat().st_mtime > dst_mq5.stat().st_mtime):
                shutil.copy2(src_mq5, dst_mq5)
        except Exception:
            pass
    if dst_mq5.exists():
        _compile_mq5_path(dst_mq5)
        ex5 = dst_mq5.with_suffix(".ex5")
        if ex5.exists():
            return "CmdmtPreDownload"
    return None

def _write_predownload_set(data_dir, days_back=30, bars_target=0):
    presets_dir = Path(data_dir) / "MQL5" / "Presets"
    presets_dir.mkdir(parents=True, exist_ok=True)
    set_path = presets_dir / "CmdmtPreDownload.set"
    txt = (
        f"DaysBack={int(days_back)}\n"
        f"BarsTarget={int(bars_target)}\n"
        "SleepMs=1000\n"
        "MaxAttempts=120\n"
        "WaitSync=1\n"
        "MaxSyncAttempts=120\n"
    )
    set_path.write_text(txt, encoding="utf-8")
    return set_path

def _predownload_marker_path(data_dir: Path) -> Path:
    return Path(data_dir) / "MQL5" / "Files" / "cmdmt_predownload.json"

def _load_predownload_state(data_dir: Path):
    try:
        p = _predownload_marker_path(data_dir)
        if not p.exists():
            return None
        txt, _, _ = _read_text_auto(p)
        return json.loads(txt)
    except Exception:
        return None

def _save_predownload_state(data_dir: Path, state: dict):
    try:
        p = _predownload_marker_path(data_dir)
        p.parent.mkdir(parents=True, exist_ok=True)
        _write_text_auto(p, json.dumps(state, indent=2) + "\n", "utf-8", b"")
    except Exception:
        pass

def _is_existing_path(p: str) -> bool:
    try:
        return Path(maybe_wslpath(p)).exists()
    except Exception:
        return False

def _is_path_intent(p: str) -> bool:
    s = p.strip().strip('"').strip("'")
    if not s:
        return False
    if "\\" in s or "/" in s:
        return True
    if len(s) >= 2 and s[1] == ":":
        return True
    return False

def _resolve_user_path(p: str) -> Path | None:
    raw = p.strip().strip('"').strip("'")
    if not raw:
        return None
    # caminho absoluto/relativo explicitado
    if _is_path_intent(raw):
        base = Path(maybe_wslpath(raw))
        if base.exists():
            return base
        if base.suffix.lower() in (".mq5", ".ex5"):
            return None
        for ext in (".mq5", ".ex5"):
            cand = base.with_suffix(ext)
            if cand.exists():
                return cand
        return None
    # nome simples: tenta no cwd (relativo)
    base = Path(raw)
    if base.exists():
        return base
    if base.suffix.lower() in (".mq5", ".ex5"):
        return None
    for ext in (".mq5", ".ex5"):
        cand = base.with_suffix(ext)
        if cand.exists():
            return cand
    return None

def _is_wsl() -> bool:
    if os.environ.get("WSL_DISTRO_NAME") or os.environ.get("WSL_INTEROP"):
        return True
    try:
        return "microsoft" in Path("/proc/version").read_text().lower()
    except Exception:
        return False

def _is_mnt_path(p: Path) -> bool:
    try:
        s = str(p).replace("\\", "/").lower()
        return s.startswith("/mnt/")
    except Exception:
        return False

def _safe_symlink(src: Path, dst: Path) -> bool:
    try:
        if dst.exists():
            return True
    except Exception:
        pass
    # Em WSL, prefira mklink/junction para o MT5 (Windows) enxergar corretamente
    if _is_wsl() and _is_mnt_path(src) and _is_mnt_path(dst):
        try:
            dst_win = to_windows_path(str(dst))
            src_win = to_windows_path(str(src))
            if src.is_dir():
                cmd = ["cmd.exe", "/c", "mklink", "/J", dst_win, src_win]
            else:
                cmd = ["cmd.exe", "/c", "mklink", "/H", dst_win, src_win]
            res = subprocess.run(cmd, capture_output=True)
            if res.returncode == 0:
                return True
        except Exception:
            pass
    try:
        os.symlink(str(src), str(dst))
        return True
    except Exception:
        return False

def _compile_mq5_path(src: Path) -> bool:
    compiler = find_mt5_compiler()
    if not compiler:
        print("ERROR MetaEditor/mt5-compile não encontrado.")
        return False
    log_path = Path(os.getcwd()) / "mt5-compile.log"
    win_src = to_windows_path(str(src))
    win_log = to_windows_path(str(log_path))
    cmd = [compiler, f"/compile:{win_src}", f"/log:{win_log}"]
    try:
        subprocess.run(cmd, check=False)
    except Exception as e:
        print(f"falha ao executar compilador: {e}")
        return False
    return True

def _prepare_external_file(src_path: Path, data_dir: Path, target_kind: str, prefer_link: bool = False):
    # target_kind: "Indicators" or "Experts"
    cleanup = []
    src_path = Path(src_path)
    orig_src = src_path
    if src_path.is_dir():
        print("ERROR passe um arquivo .ex5 ou .mq5, não pasta")
        return None, cleanup
    base = Path(data_dir) / "MQL5" / target_kind
    base.mkdir(parents=True, exist_ok=True)
    # se o usuário passou .mq5, compilar no terminal local (evita ex5 com build incompatível)
    # decide se cria link/copia de diretório
    parent_name = src_path.parent.name.lower()
    use_dir = parent_name not in ("indicators", "experts")
    if use_dir:
        dir_name = src_path.parent.name
        dst_dir = base / dir_name
        dst_existed = dst_dir.exists()
        if dst_existed and dst_dir.is_symlink():
            try:
                dst_dir.unlink()
                dst_existed = False
            except Exception:
                pass
        try:
            if dst_dir.resolve() == src_path.parent.resolve():
                # já está no diretório destino
                pass
            else:
                if not dst_existed:
                    if prefer_link and _safe_symlink(src_path.parent, dst_dir):
                        cleanup.append((dst_dir, "linkdir"))
                    else:
                        cleanup.append((dst_dir, "copydir"))
                        shutil.copytree(src_path.parent, dst_dir, dirs_exist_ok=True)
        except Exception as e:
            print("ERROR não foi possível copiar diretório: " + str(e))
            return None, cleanup
        rel_name = dir_name + "\\" + _strip_ext(src_path.name)
        dst = dst_dir / src_path.name
    else:
        rel_name = _strip_ext(src_path.name)
        dst = base / src_path.name
        dst_existed = dst.exists()
        if dst_existed and dst.is_symlink():
            try:
                dst.unlink()
                dst_existed = False
            except Exception:
                pass
        if dst.resolve() == src_path.resolve():
            # já está no destino
            pass
        else:
            if not dst_existed:
                if prefer_link and _safe_symlink(src_path, dst):
                    cleanup.append((dst, "linkfile"))
                else:
                    cleanup.append((dst, "copyfile"))
                    shutil.copy2(src_path, dst)

    # if mq5, compile in place
    if dst.suffix.lower() == ".mq5":
        okc = _compile_mq5_path(dst)
        ex5_dst = dst.with_suffix(".ex5")
        if not ex5_dst.exists():
            # tenta usar ex5 gerado no diretório origem
            src_ex5 = orig_src.with_suffix(".ex5")
            if src_ex5.exists():
                ex5_existed = ex5_dst.exists()
                if not ex5_existed:
                    cleanup.append((ex5_dst, "copyfile"))
                shutil.copy2(src_ex5, ex5_dst)
        if not okc or not ex5_dst.exists():
            print("ERROR compilação falhou para " + str(dst))
            return None, cleanup
    return rel_name, cleanup

def _rel_name_if_inside(path: Path, term_dir: Path, kind: str) -> str | None:
    try:
        base = (Path(term_dir) / "MQL5" / kind).resolve()
        p_res = path.resolve()
    except Exception:
        base = Path(term_dir) / "MQL5" / kind
        p_res = path
    base_s = str(base).replace("\\", "/").lower().rstrip("/")
    p_s = str(p_res).replace("\\", "/").lower()
    if p_s.startswith(base_s + "/"):
        try:
            rel = os.path.relpath(str(p_res), str(base))
        except Exception:
            rel = str(p_res)[len(str(base)) + 1:]
        return _strip_ext(rel.replace("/", "\\"))
    return None

def _resolve_attach_indicator_name(raw_name: str, term_dir: Path):
    raw = raw_name.strip().strip('"').strip("'")
    if not raw:
        return None, "nome vazio"
    # nome simples (sem caminho): mantém como está (apenas remove extensão se houver)
    if not _is_path_intent(raw) and not raw.lower().endswith((".mq5", ".ex5")):
        return raw, None
    # com extensão mas sem caminho: só remove extensão
    if not _is_path_intent(raw) and raw.lower().endswith((".mq5", ".ex5")):
        return _strip_ext(raw), None

    # caminho explícito
    if _is_path_intent(raw):
        cand = Path(maybe_wslpath(raw))
        if cand.is_absolute() and cand.exists():
            rel = _rel_name_if_inside(cand, term_dir, "Indicators")
            if rel:
                return rel, None
            rel_name, _ = _prepare_external_file(cand, term_dir, "Indicators", prefer_link=True)
            if rel_name:
                return rel_name, None
            return None, "falha ao copiar/linkar indicador para o terminal"

        # relativo ao MQL5
        t = raw.replace("/", "\\")
        if t.lower().startswith("mql5\\"):
            t = t[5:]
        if t.lower().startswith("indicators\\"):
            t = t[len("indicators\\"):]
        t = _strip_ext(t)
        src, rel = _find_prog_in_terminal("Indicators", t, term_dir)
        if src and rel:
            return rel, None

        # tenta resolver como caminho relativo ao cwd
        p2 = _resolve_user_path(raw)
        if p2 and p2.exists():
            rel_name, _ = _prepare_external_file(p2, term_dir, "Indicators", prefer_link=True)
            if rel_name:
                return rel_name, None
        return None, f"arquivo não encontrado: {raw}"

    return raw, None

def _parse_days(tokens):
    num_words = {
        "um": 1, "uma": 1,
        "dois": 2, "duas": 2,
        "tres": 3, "três": 3,
        "quatro": 4,
        "cinco": 5,
        "seis": 6,
        "sete": 7,
        "oito": 8,
        "nove": 9,
        "dez": 10,
    }
    for i, t in enumerate(tokens):
        low = t.lower()
        m = re.match(r"(\d+)\s*d", low)
        if m:
            return int(m.group(1))
        if low.endswith("dias") or low.endswith("dia"):
            num = re.sub(r"\D", "", low)
            if num.isdigit():
                return int(num)
            if i > 0:
                prev = tokens[i-1].lower()
                if prev.isdigit():
                    return int(prev)
                if prev in num_words:
                    return num_words[prev]
        if low in num_words:
            if i+1 < len(tokens) and tokens[i+1].lower().startswith("dia"):
                return num_words[low]
    return None

def _parse_dates(tokens):
    dates = [t for t in tokens if re.match(r"^\d{4}\.\d{2}\.\d{2}$", t)]
    if len(dates) >= 2:
        return dates[0], dates[1]
    return None, None

def _wants_last_month(tokens):
    txt = " ".join(tokens).lower()
    # aceita variações simples
    if "ultimo mes" in txt or "último mês" in txt or "mes passado" in txt or "mês passado" in txt:
        return True
    return False

def run_simple(tokens, ctx):
    if not tokens:
        print("uso: run CAMINHO --ind|--ea [SYMBOL] [TF] [3 dias] [--model N] [--timeout SEC] [--keep-open|--shutdown] [--predownload] [--logtail N] [--quiet]")
        return
    predownload = os.environ.get("CMDMT_PREDOWNLOAD", "1").strip().lower() not in ("0", "false", "no")
    timeout_sec = 120
    keep_open = False
    shutdown_override = None
    model_override = None
    pre_period = None
    pre_days = None
    pre_bars = None
    logtail = None
    quiet = False
    name_parts = []
    rest = []
    i = 0
    while i < len(tokens):
        t = tokens[i]
        low = t.lower()
        if low in ("--predownload", "--pre", "--pre-download"):
            predownload = True
            i += 1
            continue
        if low in ("--no-predownload", "--nopredownload"):
            predownload = False
            i += 1
            continue
        if low.startswith("--predownload-period=") or low.startswith("--pre-period=") or low.startswith("--pre-tf="):
            _, val = t.split("=", 1)
            pre_period = val.strip()
            i += 1
            continue
        if low in ("--predownload-period", "--pre-period", "--pre-tf"):
            i += 1
            if i < len(tokens):
                pre_period = tokens[i].strip()
                i += 1
                continue
            continue
        if low.startswith("--predownload-days=") or low.startswith("--pre-days="):
            _, val = t.split("=", 1)
            if val.isdigit():
                pre_days = int(val)
            i += 1
            continue
        if low in ("--predownload-days", "--pre-days"):
            i += 1
            if i < len(tokens) and tokens[i].isdigit():
                pre_days = int(tokens[i])
                i += 1
                continue
            continue
        if low.startswith("--predownload-bars=") or low.startswith("--pre-bars="):
            _, val = t.split("=", 1)
            if val.isdigit():
                pre_bars = int(val)
            i += 1
            continue
        if low in ("--predownload-bars", "--pre-bars"):
            i += 1
            if i < len(tokens) and tokens[i].isdigit():
                pre_bars = int(tokens[i])
                i += 1
                continue
            continue
        if low.startswith("--model="):
            _, val = t.split("=", 1)
            if val.isdigit():
                model_override = int(val)
            i += 1
            continue
        if low in ("--model",):
            i += 1
            if i < len(tokens) and tokens[i].isdigit():
                model_override = int(tokens[i])
                i += 1
                continue
            continue
        if low in ("--keep-open", "--keep", "--no-shutdown"):
            keep_open = True
            shutdown_override = 0
            i += 1
            continue
        if low in ("--shutdown", "--close"):
            shutdown_override = 1
            i += 1
            continue
        if low.startswith("--timeout=") or low.startswith("--limit="):
            _, val = t.split("=", 1)
            if val.isdigit():
                timeout_sec = int(val)
            i += 1
            continue
        if low in ("--timeout", "--limit"):
            i += 1
            if i < len(tokens) and tokens[i].isdigit():
                timeout_sec = int(tokens[i])
                i += 1
                continue
            # sem valor, ignora
            continue
        if low in ("--quiet", "--silent", "-q"):
            quiet = True
            i += 1
            continue
        if low.startswith("--logtail=") or low.startswith("--log="):
            _, val = t.split("=", 1)
            if val.isdigit():
                logtail = int(val)
            i += 1
            continue
        if low in ("--logtail", "--log"):
            i += 1
            if i < len(tokens) and tokens[i].isdigit():
                logtail = int(tokens[i])
                i += 1
                continue
            # sem valor, ignora
            continue
        if t.startswith("--"):
            rest.append(t)
        else:
            name_parts.append(t)
        i += 1
    mode = None
    for t in rest:
        low = t.lower()
        if low in ("--ind", "--indicator"):
            mode = "ind"
        if low in ("--ea", "--expert"):
            mode = "ea"
    if not name_parts:
        print("uso: run CAMINHO --ind|--ea [SYMBOL] [TF] [3 dias] [--model N] [--timeout SEC] [--keep-open|--shutdown] [--predownload] [--predownload-period TF] [--predownload-days N] [--predownload-bars N] [--logtail N] [--quiet]")
        return
    if mode is None:
        print("erro: informe se é indicador ou expert usando --ind ou --ea")
        return
    sym = None
    tf = None
    if len(name_parts) >= 2 and is_tf(name_parts[-1]):
        tf = name_parts[-1]
        sym = name_parts[-2]
        name_parts = name_parts[:-2]
    elif len(name_parts) >= 1 and is_tf(name_parts[-1]):
        tf = name_parts[-1]
        sym = ctx.get("symbol")
        name_parts = name_parts[:-1]
    if not sym:
        sym = ctx.get("symbol") or DEFAULT_SYMBOL
    if not tf:
        tf = ctx.get("tf") or DEFAULT_TF
    prog_name = " ".join(name_parts).strip()
    if not prog_name:
        print("uso: run CAMINHO --ind|--ea [SYMBOL] [TF] [3 dias] [--model N] [--timeout SEC] [--keep-open|--shutdown] [--predownload] [--predownload-period TF] [--predownload-days N] [--predownload-bars N] [--logtail N] [--quiet]")
        return

    from_d, to_d = _parse_dates(tokens)
    if not from_d or not to_d:
        today = datetime.now().date()
        if _wants_last_month(tokens):
            # primeiro e último dia do mês anterior
            first_this = today.replace(day=1)
            last_prev = first_this - timedelta(days=1)
            first_prev = last_prev.replace(day=1)
            from_d = first_prev.strftime("%Y.%m.%d")
            to_d = last_prev.strftime("%Y.%m.%d")
        else:
            ndays = _parse_days(tokens)
            if ndays is not None:
                start = today - timedelta(days=ndays)
                from_d = start.strftime("%Y.%m.%d")
                to_d = today.strftime("%Y.%m.%d")
            else:
                # default: último mês (mês calendário anterior)
                first_this = today.replace(day=1)
                last_prev = first_this - timedelta(days=1)
                first_prev = last_prev.replace(day=1)
                from_d = first_prev.strftime("%Y.%m.%d")
                to_d = last_prev.strftime("%Y.%m.%d")

    root = _find_rach_root()
    if not root:
        root = Path("/mnt/c/mql/mt5-shellscripts/Terminal")
    data_dir = root
    _ensure_dirs(data_dir)

    ind_src = ind_rel = exp_src = exp_rel = None
    cleanup = []
    src_path = _resolve_user_path(prog_name)
    if not src_path:
        print("ERROR caminho do arquivo nao encontrado (use caminho absoluto ou relativo ao cwd)")
        return
    if src_path.is_dir():
        print("ERROR passe um arquivo .ex5 ou .mq5 (nao pasta)")
        return
    if mode == "ind":
        ind_rel, cleanup = _prepare_external_file(src_path, data_dir, "Indicators")
    else:
        exp_rel, cleanup = _prepare_external_file(src_path, data_dir, "Experts")

    overrides = []
    if mode == "ind" and not ind_rel:
        print("ERROR indicador nao encontrado (use caminho correto)")
        return
    if mode == "ea" and not exp_rel:
        print("ERROR expert nao encontrado (use caminho correto)")
        return

    if ind_rel and not exp_rel:
        stub = _ensure_indicator_stub(data_dir)
        if not stub:
            print("ERROR IndicatorStub.ex5 não encontrado")
            return
        _write_indicator_stub_set(data_dir, ind_rel)
        overrides.append(("Tester", "Expert", "IndicatorStub.ex5"))
        overrides.append(("Tester", "ExpertParameters", "IndicatorStub.set"))
    elif exp_rel:
        overrides.append(("Tester", "Expert", exp_rel))
    else:
        overrides.append(("Tester", "Expert", _strip_ext(prog_name)))

    overrides += [
        ("Tester", "Symbol", sym),
        ("Tester", "Period", tf),
        ("Tester", "FromDate", from_d),
        ("Tester", "ToDate", to_d),
    ]
    if model_override is not None:
        overrides.append(("Tester", "Model", str(model_override)))
    if shutdown_override is not None:
        overrides.append(("Tester", "ShutdownTerminal", "0" if shutdown_override == 0 else "1"))

    # credenciais hardcoded no terminal dedicado (Config/common.ini)
    env_login = ""
    env_pass  = ""
    env_srv   = ""
    c_login, c_pass, c_srv = _read_common_credentials(data_dir)
    if c_login:
        env_login = c_login
    if c_pass:
        env_pass = c_pass
    if c_srv:
        env_srv = c_srv
    if env_login:
        overrides.append(("Tester", "Login", env_login))
        overrides.append(("Common", "Login", env_login))
    if env_pass:
        overrides.append(("Common", "Password", env_pass))
    if env_srv:
        overrides.append(("Common", "Server", env_srv))

    # predownload de histórico (antes do teste)
    if predownload:
        pre_name = _ensure_predownload_script(data_dir)
        if pre_name:
            # predownload usa variaveis (sem hardcode):
            # - Period: --predownload-period/--pre-period, ou StartUp.Period do tester.ini, ou Period do teste
            # - Days/Bars: --predownload-days/--predownload-bars ou derivado do intervalo do teste
            pre_period_eff = None
            if pre_period:
                pre_period_eff = pre_period
            else:
                try:
                    ini_base = _parse_ini_to_map(Path(data_dir) / "tester.ini")
                    pre_period_eff = str(ini_base.get("StartUp", {}).get("Period", "")).strip()
                except Exception:
                    pre_period_eff = ""
            if not pre_period_eff:
                pre_period_eff = tf
            try:
                fd = datetime.strptime(from_d, "%Y.%m.%d").date()
                td = datetime.strptime(to_d, "%Y.%m.%d").date()
                days_needed = max(1, (td - fd).days + 1)
            except Exception:
                days_needed = 30
            if pre_days is not None:
                days_back = int(pre_days)
            else:
                days_back = max(days_needed + 2, 10)
            bars_target = int(pre_bars) if pre_bars is not None else 0
            # evita baixar toda hora se já houver predownload recente para o mesmo símbolo
            state = _load_predownload_state(data_dir)
            now_ts = int(time.time())
            explicit_pre = (pre_period is not None) or (pre_days is not None) or (pre_bars is not None)
            if (not explicit_pre) and state and state.get("symbol")==sym and state.get("period")==pre_period_eff:
                if int(state.get("days_back", 0)) >= int(days_back) and int(state.get("bars_target", 0)) >= int(bars_target) and (now_ts - int(state.get("ts", 0))) < 12*3600:
                    pre_name = None
            if pre_name:
                _write_predownload_set(data_dir, days_back=days_back, bars_target=bars_target)
                pre_tokens = [
                    "--root", str(root),
                    "--timeout", str(timeout_sec),
                    "--minimized",
                    "--portable",
                    "--phase", "predownload",
                    "--no-tester",
                    "--set", f"StartUp.Script={pre_name}",
                    "--set", "StartUp.ScriptParameters=CmdmtPreDownload.set",
                    "--set", f"StartUp.Symbol={sym}",
                    "--set", f"StartUp.Period={pre_period_eff}",
                    "--set", "StartUp.ShutdownTerminal=1",
                    "--set", "Tester.Expert=",
                    "--set", "Tester.ExpertParameters=",
                ]
                if logtail is not None:
                    pre_tokens += ["--logtail", str(logtail)]
                if quiet:
                    pre_tokens += ["--quiet"]
                if env_login:
                    pre_tokens += ["--set", f"Common.Login={env_login}"]
                if env_pass:
                    pre_tokens += ["--set", f"Common.Password={env_pass}"]
                if env_srv:
                    pre_tokens += ["--set", f"Common.Server={env_srv}"]
                run_mt5_tester(pre_tokens)
                _save_predownload_state(data_dir, {"symbol": sym, "period": pre_period_eff, "days_back": int(days_back), "bars_target": int(bars_target), "ts": now_ts})

    tester_tokens = [
        "--root", str(root),
        "--timeout", str(timeout_sec),
        "--minimized",
        "--portable",
        "--phase", "tester",
    ]
    if logtail is not None:
        tester_tokens += ["--logtail", str(logtail)]
    if quiet:
        tester_tokens += ["--quiet"]
    for sec, key, val in overrides:
        tester_tokens += ["--set", f"{sec}.{key}={val}"]
    run_mt5_tester(tester_tokens)
    # cleanup links/copias criadas em tempo de execução
    for item in cleanup:
        try:
            if isinstance(item, tuple):
                p, kind = item
            else:
                p, kind = item, "linkdir" if item.is_dir() else "linkfile"
            if kind == "copydir":
                shutil.rmtree(p, ignore_errors=True)
            elif kind == "copyfile":
                try:
                    p.unlink()
                except Exception:
                    pass
            elif kind == "linkdir":
                try:
                    p.rmdir()
                except Exception:
                    pass
            else:
                try:
                    p.unlink()
                except Exception:
                    pass
        except Exception:
            pass

def run_mt5_tester(tokens):
    # parse tokens
    opts = {
        "root": None,
        "ini": None,
        "timeout": 60,
        "width": 640,
        "height": 480,
        "headless": False,
        "minimized": False,
        "portable": None,
        "logtail": 50,
        "quiet": False,
        "buffers": True,
        "phase": "tester",
        "no_tester": False,
        "set": [],
    }
    i = 0
    while i < len(tokens):
        t = tokens[i]
        if t.startswith("--") and "=" in t:
            key, val = t[2:].split("=", 1)
            tokens = tokens[:i] + [f"--{key}", val] + tokens[i+1:]
            continue
        if t in ("--root", "-r"):
            i += 1; opts["root"] = tokens[i] if i < len(tokens) else None
        elif t in ("--ini", "-i"):
            i += 1; opts["ini"] = tokens[i] if i < len(tokens) else None
        elif t in ("--timeout", "-t"):
            i += 1
            if i < len(tokens) and tokens[i].isdigit():
                opts["timeout"] = int(tokens[i])
        elif t == "--width":
            i += 1
            if i < len(tokens) and tokens[i].isdigit():
                opts["width"] = int(tokens[i])
        elif t == "--height":
            i += 1
            if i < len(tokens) and tokens[i].isdigit():
                opts["height"] = int(tokens[i])
        elif t == "--headless":
            opts["headless"] = True
        elif t == "--minimized":
            opts["minimized"] = True
        elif t == "--portable":
            opts["portable"] = True
        elif t == "--no-portable":
            opts["portable"] = False
        elif t in ("--logtail", "--log"):
            i += 1
            if i < len(tokens) and tokens[i].isdigit():
                opts["logtail"] = int(tokens[i])
        elif t in ("--quiet", "--silent", "-q"):
            opts["quiet"] = True
        elif t == "--phase":
            i += 1
            if i < len(tokens):
                opts["phase"] = tokens[i].strip().lower()
        elif t == "--no-tester":
            opts["no_tester"] = True
        elif t in ("--set", "-S"):
            i += 1
            if i < len(tokens):
                opts["set"].append(tokens[i])
        elif t == "--no-buffers":
            opts["buffers"] = False
        elif t == "--expert":
            i += 1
            if i < len(tokens):
                opts["set"].append(f"Tester.Expert={tokens[i]}")
        elif t == "--expertparams":
            i += 1
            if i < len(tokens):
                opts["set"].append(f"Tester.ExpertParameters={tokens[i]}")
        elif t == "--symbol":
            i += 1
            if i < len(tokens):
                opts["set"].append(f"Tester.Symbol={tokens[i]}")
        elif t == "--period":
            i += 1
            if i < len(tokens):
                opts["set"].append(f"Tester.Period={tokens[i]}")
        elif t == "--from":
            i += 1
            if i < len(tokens):
                opts["set"].append(f"Tester.FromDate={tokens[i]}")
        elif t == "--to":
            i += 1
            if i < len(tokens):
                opts["set"].append(f"Tester.ToDate={tokens[i]}")
        elif t == "--report":
            i += 1
            if i < len(tokens):
                opts["set"].append(f"Tester.Report={tokens[i]}")
        elif t == "--shutdown":
            i += 1
            if i < len(tokens):
                opts["set"].append(f"Tester.ShutdownTerminal={tokens[i]}")
        else:
            if "=" in t:
                opts["set"].append(t)
        i += 1

    root = Path(maybe_wslpath(opts["root"])) if opts["root"] else _find_rach_root()
    if not root or not root.exists():
        print("ERROR terminal_root_not_found (esperado ./Terminal dentro do repo)")
        return False

    exe = _find_terminal_exe(root)
    if not exe:
        print("ERROR terminal_not_found (não achei terminal64.exe em rash)")
        return False

    ini = _find_ini(root, opts["ini"])
    # monta ini a partir de template + overrides
    overrides = []
    env_set = os.environ.get("CMDMT_TESTER_SET", "")
    if env_set:
        for part in env_set.split(";"):
            if part.strip():
                opts["set"].append(part.strip())
    for item in opts["set"]:
        if "=" not in item:
            continue
        left, val = item.split("=", 1)
        sec = None; key = None
        if "." in left:
            sec, key = left.split(".", 1)
        elif ":" in left:
            sec, key = left.split(":", 1)
        else:
            sec, key = "Tester", left
        overrides.append((sec.strip(), key.strip(), val.strip()))

    if ini:
        ini_map = _parse_ini_to_map(ini)
        base_dir = ini.parent
    else:
        ini_map = _default_ini_map()
        base_dir = Path.cwd()

    ini_map = _apply_overrides(ini_map, overrides)

    # força shutdown se não foi definido explicitamente
    for sec in ("StartUp", "Tester"):
        if sec not in ini_map:
            ini_map[sec] = OrderedDict()
        if "ShutdownTerminal" not in ini_map[sec] or str(ini_map[sec]["ShutdownTerminal"]).strip() == "":
            ini_map[sec]["ShutdownTerminal"] = "1"

    if opts["no_tester"]:
        if "Tester" in ini_map:
            ini_map.pop("Tester", None)
    tester_expert = str(ini_map.get("Tester", {}).get("Expert", "")).strip()
    startup_expert = str(ini_map.get("StartUp", {}).get("Expert", "")).strip()
    startup_script = str(ini_map.get("StartUp", {}).get("Script", "")).strip()
    if startup_script.lower() in ("none", "null"):
        ini_map.setdefault("StartUp", OrderedDict())["Script"] = ""
        startup_script = ""
    if (not opts["no_tester"]) and (not tester_expert and not startup_expert and not startup_script):
        print("ERROR Tester.Expert vazio (use --expert ou --set Tester.Expert=...)")
        return False
    if opts["no_tester"] and (not startup_expert and not startup_script):
        print("ERROR StartUp vazio (use --set StartUp.Script=...)")
        return False

    ini_out = base_dir / "cmdmt_tester.ini"
    ini_text = _ini_map_to_text(ini_map)
    _write_text_auto(ini_out, ini_text, "utf-8", b"")

    ini_use = _patch_ini_window(ini_out, opts["width"], opts["height"])

    # detect data dir (portable)
    data_dir = root if (root / "MQL5").exists() else root
    # allow DataPath override in ini
    try:
        ini_txt, _, _ = _read_text_auto(ini_use)
        for ln in ini_txt.splitlines():
            if ln.strip().lower().startswith("datapath="):
                data_dir = Path(maybe_wslpath(ln.split("=", 1)[1].strip()))
                break
    except Exception:
        pass

    exe_cmd = to_windows_path(str(exe)) if os.name == "nt" else str(exe)
    cmd = [exe_cmd, f"/config:{to_windows_path(str(ini_use))}"]
    if opts["portable"] is True or ((root / "MQL5").exists() and opts["portable"] is not False):
        cmd.append("/portable")

    def _qprint(msg):
        if not opts["quiet"]:
            print(msg)

    start_ts = time.time()
    _qprint(f"tester: root={root}")
    _qprint(f"tester: exe={exe}")
    _qprint(f"tester: ini={ini_use}")
    try:
        if os.name == "nt":
            startupinfo = None
            creationflags = 0
            if opts["headless"] or opts["minimized"]:
                startupinfo = subprocess.STARTUPINFO()
                startupinfo.dwFlags |= subprocess.STARTF_USESHOWWINDOW
                startupinfo.wShowWindow = 0 if opts["headless"] else 2
                if opts["headless"]:
                    creationflags = subprocess.CREATE_NO_WINDOW
            proc = subprocess.Popen(cmd, startupinfo=startupinfo, creationflags=creationflags)
        else:
            proc = subprocess.Popen(cmd)
    except Exception as e:
        print(f"ERROR start_failed {e}")
        return False

    try:
        proc.wait(timeout=opts["timeout"])
    except subprocess.TimeoutExpired:
        try:
            proc.terminate()
        except Exception:
            pass
        try:
            proc.wait(timeout=5)
        except Exception:
            try:
                proc.kill()
            except Exception:
                pass

    # logs + save to run_logs
    run_dir = _ensure_run_logs_dir()
    run_stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    run_log = run_dir / f"run_{run_stamp}.log"
    _append_run_log(run_log, "run", [
        f"root={data_dir}",
        f"exe={exe}",
        f"ini={ini_use}",
        f"start_ts={start_ts}",
    ])
    logs_dirs = [data_dir / "MQL5" / "Logs", data_dir / "Logs"]
    tlogs_dirs = [data_dir / "MQL5" / "Tester" / "Logs", data_dir / "Tester" / "Logs"]
    latest_term = None
    for d in logs_dirs:
        cand = _latest_file(d, exts={".log"}, after_ts=start_ts)
        if cand and (not latest_term or cand.stat().st_mtime > latest_term.stat().st_mtime):
            latest_term = cand
    if not latest_term:
        for d in logs_dirs:
            cand = _latest_file(d, exts={".log"})
            if cand and (not latest_term or cand.stat().st_mtime > latest_term.stat().st_mtime):
                latest_term = cand
    latest_test = None
    for d in tlogs_dirs:
        cand = _latest_file(d, exts={".log"}, after_ts=start_ts)
        if cand and (not latest_test or cand.stat().st_mtime > latest_test.stat().st_mtime):
            latest_test = cand
    if not latest_test:
        for d in tlogs_dirs:
            cand = _latest_file(d, exts={".log"})
            if cand and (not latest_test or cand.stat().st_mtime > latest_test.stat().st_mtime):
                latest_test = cand
    term_lines = _tail_lines(latest_term, opts["logtail"]) if latest_term else []

    # logs de scripts/experts (MQL5/Logs)
    mql5_log = None
    for d in [data_dir / "MQL5" / "Logs"]:
        cand = _latest_file(d, exts={".log"}, after_ts=start_ts)
        if cand and (not mql5_log or cand.stat().st_mtime > mql5_log.stat().st_mtime):
            mql5_log = cand
    if not mql5_log:
        for d in [data_dir / "MQL5" / "Logs"]:
            cand = _latest_file(d, exts={".log"})
            if cand and (not mql5_log or cand.stat().st_mtime > mql5_log.stat().st_mtime):
                mql5_log = cand
    mql5_lines = _tail_lines(mql5_log, opts["logtail"]) if mql5_log else []
    test_lines = _tail_lines(latest_test, opts["logtail"]) if latest_test else []

    # resumo de erros (linhas relevantes nas últimas linhas dos logs)
    def _err_lines(lines, phase, label):
        if not lines:
            return []
        pats = [
            "error", "fail", "failed", "no history", "not synchronized",
            "cannot select", "tester didn't start", "shutdown with",
            "no expert specified", "invalid", "denied", "timeout"
        ]
        success_markers = ("test passed", "automatical testing started")
        has_success = any(sm in ln.lower() for ln in lines for sm in success_markers)
        out = []
        for ln in lines:
            l = ln.lower()
            if "shutdown with 0" in l or "shutdown with 1" in l or "exit with code 0" in l or "stopped with 0" in l:
                continue
            if has_success and ("no expert specified" in l or "tester didn't start" in l):
                continue
            if phase == "predownload" and "no expert specified" in l:
                continue
            if any(p in l for p in pats):
                out.append(f"[{label}] {ln}")
        return out

    err_bucket = []
    for lines, label in ((term_lines, "terminal"), (test_lines, "tester"), (mql5_lines, "mql5")):
        if not lines:
            continue
        lines = _filter_lines_since(lines, start_ts)
        err_bucket += _err_lines(lines, opts["phase"], label)
    if not opts["quiet"]:
        _print_block("erros:", err_bucket[-50:] if err_bucket else ["(nenhum)"])
    _append_run_log(run_log, "erros:", err_bucket[-50:] if err_bucket else ["(nenhum)"])

    if latest_term:
        if not opts["quiet"]:
            _print_block(f"terminal log: {latest_term}", term_lines)
        _append_run_log(run_log, f"terminal log: {latest_term}", term_lines)
    else:
        _append_run_log(run_log, "terminal log: (none)", [])

    if mql5_log:
        if not opts["quiet"]:
            _print_block(f"mql5 log: {mql5_log}", mql5_lines)
        _append_run_log(run_log, f"mql5 log: {mql5_log}", mql5_lines)
    else:
        _append_run_log(run_log, "mql5 log: (none)", [])

    if latest_test:
        if not opts["quiet"]:
            _print_block(f"tester log: {latest_test}", test_lines)
        _append_run_log(run_log, f"tester log: {latest_test}", test_lines)
    else:
        _append_run_log(run_log, "tester log: (none)", [])

    # buffers (heurística: linhas com 'buffer' nos logs)
    if opts["buffers"]:
        for log in (latest_test, latest_term):
            if not log:
                continue
            lines = _tail_lines(log, max(200, opts["logtail"]))
            hits = [ln for ln in lines if re.search(r"buffer", ln, re.I)]
            if hits:
                if not opts["quiet"]:
                    _print_block(f"buffers em {log.name}", hits[-50:])
                _append_run_log(run_log, f"buffers em {log.name}", hits[-50:])

    # dados (buffers) em arquivo, se existirem
    data_dirs = [
        data_dir / "MQL5" / "Tester" / "Files",
        data_dir / "Tester" / "Files",
        data_dir / "MQL5" / "Files",
        data_dir / "Files",
    ]
    # arquivos do agente do tester (onde o stub escreve)
    try:
        agent_base = data_dir / "Tester"
        if agent_base.exists():
            agents = sorted([p for p in agent_base.glob("Agent-*") if p.is_dir()], key=lambda p: p.stat().st_mtime, reverse=True)
            for a in agents[:3]:
                data_dirs.insert(0, a / "MQL5" / "Files")
                data_dirs.insert(0, a / "Files")
    except Exception:
        pass
    data_latest = None
    for d in data_dirs:
        cand = _latest_file(d, exts={".txt", ".csv"}, after_ts=start_ts)
        if cand and (not data_latest or cand.stat().st_mtime > data_latest.stat().st_mtime):
            data_latest = cand
    if not data_latest:
        for d in data_dirs:
            cand = _latest_file(d, exts={".txt", ".csv"})
            if cand and (not data_latest or cand.stat().st_mtime > data_latest.stat().st_mtime):
                data_latest = cand
    if data_latest:
        lines = _tail_lines(data_latest, 50)
        if not opts["quiet"]:
            _print_block(f"data file: {data_latest}", lines)
        _append_run_log(run_log, f"data file: {data_latest}", lines)
    else:
        _append_run_log(run_log, "data file: (none)", [])
    if opts["quiet"]:
        print(f"run_log: {run_log}")
    return True

def _state_dir():
    base = os.environ.get("CMDMT_HOME")
    if base:
        p = Path(maybe_wslpath(base))
    else:
        p = Path.home() / ".cmdmt"
    p.mkdir(parents=True, exist_ok=True)
    return p


def _hotkeys_path():
    env = os.environ.get("CMDMT_HOTKEYS_FILE")
    if env:
        return Path(maybe_wslpath(env))
    return _state_dir() / "hotkeys.json"

def _load_hotkeys():
    path = _hotkeys_path()
    if not path.exists():
        return {}
    try:
        txt, _, _ = _read_text_auto(path)
        data = json.loads(txt)
        if isinstance(data, dict):
            # normaliza para str->str
            out = {}
            for k, v in data.items():
                if isinstance(k, str) and isinstance(v, str):
                    out[k.strip().upper()] = v.strip()
            return out
    except Exception:
        pass
    return {}

def _save_hotkeys(hk: dict):
    path = _hotkeys_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    data = {}
    for k, v in hk.items():
        if not k:
            continue
        data[str(k).strip().upper()] = str(v)
    _write_text_auto(path, json.dumps(data, indent=2, ensure_ascii=False) + "\n", "utf-8", b"")
    return path

def _normalize_hotkey_name(name: str) -> str:
    if name is None:
        return ""
    n = str(name).strip()
    # aceita apenas @prefixo, não @no-fim
    if n.startswith("@"):
        n = n[1:]
    return n.strip().upper()

def resolve_expert_path(terminal_dir: Path, expert_name: str) -> str:
    name = expert_name.strip().replace("/", "\\")
    # if absolute path includes MQL5\Experts\, keep only relative part
    low = name.lower()
    marker = "\\mql5\\experts\\"
    idx = low.find(marker)
    if idx >= 0:
        name = name[idx + len(marker):]
    if name.lower().startswith("experts\\"):
        name = name[len("experts\\"):]
    if name.lower().endswith(".ex5") or name.lower().endswith(".mq5"):
        name = name[:-4]
    experts_dir = terminal_dir / "MQL5" / "Experts"
    def exists_rel(rel: str) -> bool:
        rel_path = Path(*rel.split("\\"))
        return (experts_dir / (str(rel_path) + ".ex5")).exists() or (experts_dir / (str(rel_path) + ".mq5")).exists()
    if exists_rel(name):
        return name
    alt = f"Examples\\{name}\\{name}"
    if exists_rel(alt):
        return alt
    # recursive search by filename
    target_ex5 = name + ".ex5"
    target_mq5 = name + ".mq5"
    for p in experts_dir.rglob("*"):
        if p.is_file() and p.name in (target_ex5, target_mq5):
            rel = p.relative_to(experts_dir).with_suffix("")
            return str(rel).replace("/", "\\")
    return name

def build_expert_block(name: str, path: str, params_str: str) -> str:
    lines = []
    lines.append("<expert>")
    lines.append(f"name={name}")
    lines.append(f"path={path}")
    lines.append("expertmode=5")
    lines.append("<inputs>")
    if params_str:
        for item in params_str.split(";"):
            if "=" in item:
                k, v = item.split("=", 1)
                k = k.strip()
                v = v.strip()
                if k:
                    lines.append(f"{k}={v}")
    lines.append("</inputs>")
    lines.append("</expert>")
    return "\n".join(lines) + "\n"

def insert_expert_block(content: str, block: str) -> str:
    # Templates do MT5 normalmente colocam <expert> antes do primeiro <window>
    idx = content.lower().find("<window>")
    if idx != -1:
        return content[:idx] + block + content[idx:]
    if "</chart>" in content:
        return content.replace("</chart>", block + "</chart>", 1)
    return content + "\n" + block

def _dbg_enabled(flag: bool = False) -> bool:
    if flag:
        return True
    v = os.environ.get(DEBUG_TPL_ENV, "").strip().lower()
    return v in ("1", "true", "yes", "on")

def _dbg(msg: str, flag: bool = False):
    if not _dbg_enabled(flag):
        return
    line = f"[DEBUG_TPL] {msg}"
    print(line)
    try:
        Path.cwd().joinpath("cmdmt-debug.log").open("a", encoding="utf-8").write(line + "\n")
    except Exception:
        pass

def expert_basename(name: str) -> str:
    n = name.replace("/", "\\").split("\\")[-1]
    if n.lower().endswith((".mq5", ".ex5", ".tpl")):
        n = n[:-4]
    return n

def expert_template_path(term: Path, expert_name: str) -> str:
    rel = resolve_expert_path(term, expert_name)
    rel_path = Path(*rel.split("\\")) if rel else Path()
    base = term / "MQL5" / "Experts" / rel_path
    if (base.with_suffix(".ex5")).exists():
        return f"Experts\\{rel}.ex5"
    if (base.with_suffix(".mq5")).exists():
        return f"Experts\\{rel}.mq5"
    # fallback sem extensão
    return f"Experts\\{rel}"

def detect_tpl_encoding(data: bytes):
    if data.startswith(b"\xff\xfe"):
        return "utf-16-le", True
    if data.startswith(b"\xfe\xff"):
        return "utf-16-be", True
    if b"\x00" in data[:200]:
        return "utf-16-le", False
    return "utf-8", False

def ensure_stub_template(stub_name: str = "Stub.tpl", base_tpl_name: str = "", debug: bool = False):
    term = find_terminal_data_dir()
    if not term:
        return None
    tpl_dir = term / "MQL5" / "Profiles" / "Templates"
    tpl_dir.mkdir(parents=True, exist_ok=True)
    stub_path = tpl_dir / stub_name
    if stub_path.exists():
        _dbg(f"stub exists: {stub_path}", debug)
        return stub_path

    base_name = base_tpl_name or DEFAULT_EA_BASE_TPL
    base_tpl = tpl_dir / base_name
    if not base_tpl.exists():
        # fallback to Default.tpl then any template
        base_tpl = tpl_dir / "Default.tpl"
        if not base_tpl.exists():
            tpls = list(tpl_dir.glob("*.tpl"))
            if tpls:
                base_tpl = tpls[0]
    if not base_tpl.exists():
        _dbg("base template not found for stub", debug)
        return None

    _dbg(f"stub base: {base_tpl}", debug)
    raw = base_tpl.read_bytes()
    enc, has_bom = detect_tpl_encoding(raw)
    try:
        content = raw.decode("utf-16" if has_bom and enc.startswith("utf-16") else enc, errors="ignore")
    except Exception:
        content = raw.decode("utf-8", errors="ignore")
    content = re.sub(r"(?is)<expert>.*?</expert>\s*", "", content)

    if enc.startswith("utf-16"):
        if has_bom:
            data = content.encode("utf-16", errors="ignore")
        else:
            data = content.encode(enc, errors="ignore")
        stub_path.write_bytes(data)
    else:
        stub_path.write_text(content, encoding="utf-8", errors="ignore")
    _dbg(f"stub written: {stub_path}", debug)
    return stub_path

def ensure_ea_template_from_stub(expert_name: str, params_str: str, stub_name: str = "Stub.tpl", base_tpl_name: str = "", debug: bool = False):
    term = find_terminal_data_dir()
    if not term:
        return None
    tpl_dir = term / "MQL5" / "Profiles" / "Templates"
    tpl_dir.mkdir(parents=True, exist_ok=True)
    stub_path = ensure_stub_template(stub_name=stub_name, base_tpl_name=base_tpl_name, debug=debug)
    if not stub_path or not stub_path.exists():
        _dbg("stub missing after ensure", debug)
        return None

    raw = stub_path.read_bytes()
    enc, has_bom = detect_tpl_encoding(raw)
    try:
        content = raw.decode("utf-16" if has_bom and enc.startswith("utf-16") else enc, errors="ignore")
    except Exception:
        content = raw.decode("utf-8", errors="ignore")

    content = re.sub(r"(?is)<expert>.*?</expert>\s*", "", content)
    exp_name = expert_basename(expert_name)
    exp_path = expert_template_path(term, expert_name)
    block = build_expert_block(exp_name, exp_path, params_str)
    loc = "<window>" if "<window>" in content.lower() else "</chart>" if "</chart>" in content else "append"
    _dbg(f"attach ea name={exp_name} path={exp_path} insert={loc}", debug)
    content = insert_expert_block(content, block)

    out_name = expert_basename(expert_name) + ".tpl"
    out_path = tpl_dir / out_name
    if enc.startswith("utf-16"):
        if has_bom:
            data = content.encode("utf-16", errors="ignore")
        else:
            data = content.encode(enc, errors="ignore")
        out_path.write_bytes(data)
    else:
        out_path.write_text(content, encoding="utf-8", errors="ignore")
    _dbg(f"template written: {out_path}", debug)
    # verify expert block exists in output
    try:
        out_raw = out_path.read_bytes()
        enc2, has_bom2 = detect_tpl_encoding(out_raw)
        out_txt = out_raw.decode("utf-16" if has_bom2 and enc2.startswith("utf-16") else enc2, errors="ignore")
        low = out_txt.lower()
        ok = "<expert>" in low and f"name={exp_name.lower()}" in low and f"path={exp_path.lower()}" in low
        _dbg(f"verify block ok={ok}", debug)
        if debug:
            s = low.find("<expert>")
            e = low.find("</expert>", s)
            if s != -1 and e != -1:
                _dbg("expert block:\\n" + out_txt[s:e+9], debug)
    except Exception:
        pass
    return out_name

def ensure_ea_template(expert_name: str, params_str: str, base_tpl_name: str = ""):
    term = find_terminal_data_dir()
    if not term:
        return None
    tpl_dir = term / "MQL5" / "Profiles" / "Templates"
    tpl_dir.mkdir(parents=True, exist_ok=True)
    # choose base template
    base_tpl = tpl_dir / (base_tpl_name or "Default.tpl")
    if not base_tpl.exists():
        # fallback to Default.tpl then any template
        if base_tpl_name:
            base_tpl = tpl_dir / "Default.tpl"
        if not base_tpl.exists():
            tpls = list(tpl_dir.glob("*.tpl"))
            if tpls:
                base_tpl = tpls[0]
    if not base_tpl.exists():
        return None
    raw = base_tpl.read_bytes()
    enc, has_bom = detect_tpl_encoding(raw)
    try:
        content = raw.decode("utf-16" if has_bom and enc.startswith("utf-16") else enc, errors="ignore")
    except Exception:
        content = raw.decode("utf-8", errors="ignore")
    # remove existing <expert> block
    content = re.sub(r"(?is)<expert>.*?</expert>\s*", "", content)
    # insert new block before <window> (fallback to </chart>)
    exp_name = expert_basename(expert_name)
    exp_path = expert_template_path(term, expert_name)
    block = build_expert_block(exp_name, exp_path, params_str)
    content = insert_expert_block(content, block)
    # write template
    safe = re.sub(r"[^A-Za-z0-9_.-]+", "_", expert_name.strip()) or "ea"
    tpl_name = f"cmdmt_{safe}.tpl"
    out_path = tpl_dir / tpl_name
    if enc.startswith("utf-16"):
        if has_bom:
            data = content.encode("utf-16", errors="ignore")
        else:
            data = content.encode(enc, errors="ignore")
        out_path.write_bytes(data)
    else:
        out_path.write_text(content, encoding="utf-8", errors="ignore")
    return tpl_name

def resolve_base_template():
    name = os.environ.get("CMDMT_EA_BASE_TPL") or DEFAULT_EA_BASE_TPL
    term = find_terminal_data_dir()
    if not term:
        return ""
    path = term / "MQL5" / "Profiles" / "Templates" / name
    return name if path.exists() else ""

def template_has_expert(path: Path, expected: str) -> bool:
    if not path.exists():
        return False
    raw = path.read_bytes()
    enc, has_bom = detect_tpl_encoding(raw)
    try:
        text = raw.decode("utf-16" if has_bom and enc.startswith("utf-16") else enc, errors="ignore")
    except Exception:
        text = raw.decode("utf-8", errors="ignore")
    low = text.lower()
    exp = expected.lower()
    s = low.find("<expert>")
    if s == -1:
        return False
    e = low.find("</expert>", s)
    if e == -1:
        return False
    block = low[s:e]
    return f"name={exp}" in block

def find_log_error(term: Path, name: str):
    log_dir = term / "MQL5" / "Logs"
    if not log_dir.exists():
        return None
    fname = datetime.now().strftime("%Y%m%d") + ".log"
    log_path = log_dir / fname
    if not log_path.exists():
        return None
    try:
        lines = log_path.read_text(encoding="utf-8", errors="ignore").splitlines()
    except Exception:
        return None
    tail = lines[-200:] if len(lines) > 200 else lines
    lname = name.lower()
    keywords = ("cannot load", "init failed", "failed", "error")
    for line in reversed(tail):
        low = line.lower()
        if lname in low and any(k in low for k in keywords):
            return line
    return None

# ------------------- Transportes -------------------
class TransportFile:
    def __init__(self, directory: str, timeout: float = 6.0):
        self.dir = Path(directory)
        self.dir.mkdir(parents=True, exist_ok=True)
        self.timeout = timeout

    def send_text(self, line: str) -> str:
        cmd_id = gen_id()
        fname = self.dir / f"cmd_{cmd_id}.txt"
        with open(fname, "w", encoding="ascii", errors="ignore", newline="\n") as f:
            f.write(line.strip() + "\n")
        resp = self.dir / f"resp_{cmd_id}.txt"
        deadline = time.time() + self.timeout
        while time.time() < deadline:
            if resp.exists():
                break
            time.sleep(0.05)
        if not resp.exists():
            return "ERROR\ntimeout\n"
        txt = resp.read_text(encoding="utf-8", errors="replace")
        try:
            resp.unlink()
        except Exception:
            pass
        return txt

    def send_json(self, obj: dict) -> dict:
        resp_txt = self.send_text(json.dumps(obj))
        try:
            return json.loads(resp_txt.strip())
        except Exception:
            return {"ok": False, "error": resp_txt.strip()}

class TransportSocket:
    def __init__(self, host: str, port: int, timeout: float = 3.0):
        self.host = host
        self.port = port
        self.timeout = timeout
        # suporte a fallback: "h1,h2;h3"
        self.hosts = []
        if host:
            parts = [h.strip() for h in host.replace(";", ",").split(",") if h.strip()]
            self.hosts = parts if parts else [host]
        else:
            self.hosts = []

    def send_text(self, line: str) -> str:
        if not line.endswith("\n"):
            line += "\n"
        last_err = None
        # tenta cada host com algumas tentativas (fallback automático)
        for host in (self.hosts or [self.host]):
            for _ in range(3):  # até 3 tentativas em caso de reset/timeout
                try:
                    with socket.create_connection((host, self.port), timeout=self.timeout) as s:
                        # handshake (gateway single-port)
                        if CMDMT_HELLO_ENABLED:
                            s.sendall((CMDMT_HELLO_LINE + "\n").encode("utf-8"))
                        s.sendall(line.encode("utf-8"))
                        data = b""
                        while True:
                            chunk = s.recv(4096)
                            if not chunk:
                                break
                            data += chunk
                            if b"\n" in data:
                                break
                    return data.decode("utf-8", errors="ignore")
                except Exception as e:
                    last_err = e
                    time.sleep(0.1)
        raise last_err

    def send_json(self, obj: dict) -> dict:
        resp = self.send_text(json.dumps(obj))
        try:
            return json.loads(resp.strip())
        except Exception:
            return {"ok": False, "error": resp.strip()}

# ------------------- Parsing de comandos -------------------
def _cmd_attachind_args(r, ctx):
    r = list(r)
    sym = None; tf = None
    if len(r) >= 2 and is_tf(r[1]):
        sym = r[0]; tf = r[1]; r = r[2:]
    elif len(r) >= 1 and is_tf(r[0]) and ctx.get("symbol"):
        sym = ctx.get("symbol"); tf = r[0]; r = r[1:]
    else:
        # usa defaults; não interpreta o primeiro token como símbolo
        sym = ctx.get("symbol"); tf = ctx.get("tf")
    if not ensure_ctx(ctx, not sym, not tf):
        return None
    if not r:
        print("uso: attach ind [SYMBOL] [TF] NAME [SUB|sub=N] [-- k=v ...]")
        return None
    # allow params after "--"
    params_tokens = []
    if "--" in r:
        idx = r.index("--")
        params_tokens = r[idx+1:]
        r = r[:idx]
    else:
        for i, tok in enumerate(r):
            if "=" in tok and not tok.lower().startswith("sub="):
                params_tokens = r[i:]
                r = r[:i]
                break
    # explicit sub token
    sub = str(ctx.get("sub", 1))
    sub_idx = None
    for i, tok in enumerate(r):
        low = tok.lower()
        if low.startswith("sub="):
            sub = tok.split("=", 1)[1]; sub_idx = i; break
        if (tok.startswith("@") or tok.startswith("#")) and tok[1:].isdigit():
            sub = tok[1:]; sub_idx = i; break
    if sub_idx is not None:
        r = r[:sub_idx] + r[sub_idx+1:]
    elif len(r) >= 2 and r[-1].isdigit():
        # mantém compatibilidade com "NOME SUB"
        sub = r[-1]; r = r[:-1]
    elif len(r) == 1 and r[0].isdigit():
        print("uso: attach ind [SYMBOL] [TF] NAME [SUB|sub=N] [-- k=v ...]")
        return None
    name = " ".join(r)
    # se veio caminho (WSL/Windows), prepara e converte para path relativo do terminal
    if _is_path_intent(name) or name.lower().endswith((".mq5", ".ex5")):
        term = find_terminal_data_dir()
        if not term:
            print("erro: não encontrei o Terminal do MT5 (CMDMT_MT5_DATA/MT5_DATA_DIR)")
            return None
        resolved, err = _resolve_attach_indicator_name(name, term)
        if not resolved:
            print("erro: " + (err or "indicador não encontrado"))
            return None
        name = resolved
    params_str = ";".join(params_tokens) if params_tokens else ""
    payload = [sym, tf, name, sub]
    if params_str:
        payload.append(params_str)
    return "ATTACH_IND_FULL", payload

def _cmd_detachind_args(r, ctx):
    r = list(r)
    sym = None; tf = None
    if len(r) >= 2 and is_tf(r[1]):
        sym = r[0]; tf = r[1]; r = r[2:]
    elif len(r) >= 1 and is_tf(r[0]) and ctx.get("symbol"):
        sym = ctx.get("symbol"); tf = r[0]; r = r[1:]
    else:
        # usa defaults; não interpreta o primeiro token como símbolo
        sym = ctx.get("symbol"); tf = ctx.get("tf")
    if not ensure_ctx(ctx, not sym, not tf):
        return None
    if not r:
        print("uso: deattach ind [SYMBOL] [TF] NAME [SUB|sub=N]")
        return None
    sub = str(ctx.get("sub", 1))
    sub_idx = None
    for i, tok in enumerate(r):
        low = tok.lower()
        if low.startswith("sub="):
            sub = tok.split("=", 1)[1]; sub_idx = i; break
        if (tok.startswith("@") or tok.startswith("#")) and tok[1:].isdigit():
            sub = tok[1:]; sub_idx = i; break
    if sub_idx is not None:
        r = r[:sub_idx] + r[sub_idx+1:]
    elif len(r) >= 2 and r[-1].isdigit():
        sub = r[-1]; r = r[:-1]
    elif len(r) == 1 and r[0].isdigit():
        print("uso: deattach ind [SYMBOL] [TF] NAME [SUB|sub=N]")
        return None
    name = " ".join(r)
    return "DETACH_IND_FULL", [sym, tf, name, sub]

def _cmd_attachea_args(r, ctx):
    r = list(r)
    sym = None; tf = None
    if len(r) >= 2 and is_tf(r[1]):
        sym = r[0]; tf = r[1]; r = r[2:]
    elif len(r) >= 1 and is_tf(r[0]) and ctx.get("symbol"):
        sym = ctx.get("symbol"); tf = r[0]; r = r[1:]
    else:
        sym = ctx.get("symbol"); tf = ctx.get("tf")
    if not ensure_ctx(ctx, not sym, not tf):
        return None
    if not r:
        print("uso: attach ea [SYMBOL] [TF] NAME [-- k=v ...]")
        return None
    params_tokens = []
    debug_flag = False
    if "--debug" in r:
        debug_flag = True
        r = [t for t in r if t != "--debug"]
    if "--" in r:
        idx = r.index("--")
        params_tokens = r[idx+1:]
        r = r[:idx]
    else:
        for i, tok in enumerate(r):
            if "=" in tok and not tok.lower().startswith("sub="):
                params_tokens = r[i:]
                r = r[:i]
                break
    name = " ".join(r)
    params_str = ";".join(params_tokens) if params_tokens else ""
    return "ATTACH_EA_SMART", [sym, tf, name, params_str, "1" if debug_flag else ""]

def _cmd_detachea_args(r, ctx):
    return "DETACH_EA_FULL", list(r)

def _cmd_runscript_args(r, ctx):
    r = list(r)
    tpl = r[-1] if r else ""
    if not tpl:
        print("uso: attach run [SYMBOL] [TF] TEMPLATE")
        return None
    r = r[:-1]
    sym, tf, _ = parse_sym_tf(r, ctx)
    if not ensure_ctx(ctx, not sym, not tf):
        return None
    return "RUN_SCRIPT", [sym, tf, tpl]

def parse_user_line(line: str, ctx):
    line_str = line.strip()
    try:
        parts = shlex.split(line_str)
        # se houver caminho Windows sem aspas, o shlex pode remover '\\'
        if re.search(r"[A-Za-z]:[\\\\/]", line_str) and not any("\\" in p for p in parts):
            parts = shlex.split(line_str, posix=False)
    except Exception:
        parts = line_str.split()
    # remove aspas externas se vierem no token (posix=False)
    cleaned = []
    for p in parts:
        if len(p) >= 2 and ((p[0] == p[-1]) and p[0] in ("'", '"')):
            cleaned.append(p[1:-1])
        else:
            cleaned.append(p)
    parts = cleaned
    if not parts:
        return None
    # ---- Frases amigáveis em primeira palavra ----
    head = parts[0].lower()
    if head in ("cmd", "type") and len(parts) >= 2:
        return parts[1].upper(), parts[2:]

    if head in ("selftest", "test", "teste"):
        mode = parts[1].lower() if len(parts) >= 2 else "quick"
        return "SELFTEST", [mode]

    if head in ("compile", "compilar"):
        if len(parts) >= 2 and parts[1].lower() in ("service","servico"):
            if len(parts) >= 3:
                target = " ".join(parts[2:])
                return "COMPILE_SERVICE_NAME", [target]
            return "COMPILE_HERE", []
        if len(parts) >= 2 and parts[1].lower() in ("here",):
            return "COMPILE_HERE", []
        if len(parts) >= 2 and parts[1].lower() in ("all","todos","ambos","services","servicos"):
            return "COMPILE_ALL", []
        if len(parts) < 2:
            print("uso: compile <arquivo.mq5|nome|caminho> | compile here")
            return None
        target = " ".join(parts[1:])
        return "COMPILE", [target]

    if head in ("service","servico") and len(parts) >= 2 and parts[1].lower() in ("compile","compilar"):
        if len(parts) >= 3:
            target = " ".join(parts[2:])
            return "COMPILE_SERVICE_NAME", [target]
        return "COMPILE_HERE", []

    if head in ("service","servico") and len(parts) >= 2 and parts[1].lower() in ("start","iniciar","run"):
        target = " ".join(parts[2:]) if len(parts) >= 3 else ""
        return "SERVICE_START", [target]
    if head in ("start","iniciar","run") and len(parts) >= 2 and parts[1].lower() in ("service","servico"):
        target = " ".join(parts[2:]) if len(parts) >= 3 else ""
        return "SERVICE_START", [target]
    if head in ("service","servico") and len(parts) >= 2 and parts[1].lower() in ("windows","window","janela","janelas","hwnd","uia"):
        return "SERVICE_WINDOWS", []
    if head in ("service","servico") and len(parts) >= 2 and parts[1].lower() in ("list","listar","ls"):
        print("use: service windows  (lista janelas/HWND)")
        return None
    if head in ("service","servico") and len(parts) >= 2 and parts[1].lower() in ("stop","parar"):
        target = " ".join(parts[2:]) if len(parts) >= 3 else ""
        return "SERVICE_STOP", [target]
    if head in ("stop","parar") and len(parts) >= 2 and parts[1].lower() in ("service","servico"):
        target = " ".join(parts[2:]) if len(parts) >= 3 else ""
        return "SERVICE_STOP", [target]

    if head in ("ini", "config"):
        if len(parts) < 2:
            print("uso: ini set Section.Key=Valor | ini get Section.Key")
            return None
        action = parts[1].lower()
        if action in ("set", "add", "put"):
            if len(parts) < 3:
                print("uso: ini set Section.Key=Valor"); return None
            return "INI_SET", parts[2:]
        if action in ("get", "show"):
            if len(parts) < 3:
                print("uso: ini get Section.Key"); return None
            return "INI_GET", parts[2:]
        if action in ("ls", "list", "all"):
            return "INI_LIST", []
        if action in ("sync", "pull"):
            return "INI_SYNC", []
        print("uso: ini set Section.Key=Valor | ini get Section.Key")
        return None

    if head in ("run", "rodar"):
        return "RUN_SIMPLE", parts[1:]
    if head == "logs":
        return "RUN_LOGS", parts[1:]

    if head in ("tester", "mt5tester", "testermt5"):
        return "TESTER_RUN", parts[1:]

    # Chart commands: "chart open symbol tf", "chart close", "chart list", "chart add ind/ea/tpl ..."
    if head == "chart":
        if len(parts) < 2:
            print("uso: chart <open|close|list|redraw|detachall|windowfind|add|obj|screenshot|save> ...")
            return None
        action = parts[1].lower()
        rest = parts[2:]
        if action == "open":
            sym, tf, _ = parse_sym_tf(rest, ctx)
            if not ensure_ctx(ctx, not sym, not tf):
                return None
            return "OPEN_CHART", [sym, tf]
        if action == "close":
            sym, tf, _ = parse_sym_tf(rest, ctx)
            if not ensure_ctx(ctx, not sym, not tf):
                return None
            return "CLOSE_CHART", [sym, tf]
        if action == "list":
            return "LIST_CHARTS", []
        if action == "redraw":
            sym, tf, _ = parse_sym_tf(rest, ctx)
            if not ensure_ctx(ctx, not sym, not tf):
                return None
            return "REDRAW_CHART", [sym, tf]
        if action == "detachall":
            sym, tf, _ = parse_sym_tf(rest, ctx)
            if not ensure_ctx(ctx, not sym, not tf):
                return None
            return "DETACH_ALL", [sym, tf]
        if action == "windowfind":
            sym, tf, rem = parse_sym_tf(rest, ctx)
            if not ensure_ctx(ctx, not sym, not tf):
                return None
            if len(rem) < 1:
                print("uso: chart windowfind [SYMBOL] [TF] NAME"); return None
            return "WINDOW_FIND", [sym, tf, rem[0]]
        if action == "add" and len(rest) >= 1:
            what = rest[0].lower()
            if what in ("ind","indicator"):
                name_tokens = rest[1:]
                if len(name_tokens) == 0:
                    print("uso: chart add ind [SYMBOL] [TF] NAME [SUB]"); return None
                return _cmd_attachind_args(name_tokens, ctx)
            if what in ("ea","expert"):
                ea_tokens = rest[1:]
                if len(ea_tokens) == 0:
                    print("uso: chart add ea [SYMBOL] [TF] NAME"); return None
                return _cmd_attachea_args(ea_tokens, ctx)
            if what in ("tpl","template"):
                tpl_tokens = rest[1:]
                if len(tpl_tokens) == 0:
                    print("uso: chart add tpl [SYMBOL] [TF] TEMPLATE"); return None
                return parse_user_line("applytpl " + " ".join(tpl_tokens), ctx)
        if action == "save" and len(rest) >= 1 and rest[0].lower() in ("tpl","template"):
            tpl_tokens = rest[1:]
            if len(tpl_tokens) == 0:
                print("uso: chart save tpl [SYMBOL] [TF] TEMPLATE"); return None
            return parse_user_line("savetpl " + " ".join(tpl_tokens), ctx)
        if action in ("saveid","savechart","savetplid") and len(rest) >= 2:
            chart_id = rest[0]
            name = " ".join(rest[1:])
            if not chart_id.isdigit():
                print("uso: chart saveid CHART_ID NAME"); return None
            return "CHART_SAVE_TPL", [chart_id, name]
        if action == "screenshot" and len(rest) >= 4:
            # chart screenshot SYMBOL TF FILE WIDTH [HEIGHT]
            params = rest[0:4]
            if len(rest) >=5: params.append(rest[4])
            return "SCREENSHOT", params
        if action == "obj":
            if len(rest)==0:
                print("uso: chart obj <list|delete|delprefix|move|create> ..."); return None
            sub = rest[0].lower()
            r = rest[1:]
            if sub == "list":
                return "OBJ_LIST", r
            if sub == "delete" and len(r)>=1:
                return "OBJ_DELETE", [r[0]]
            if sub == "delprefix" and len(r)>=1:
                return "OBJ_DELETE_PREFIX", [r[0]]
            if sub == "move" and len(r)>=3:
                params=[r[0], r[1], r[2]]
                if len(r)>=4: params.append(r[3])
                return "OBJ_MOVE", params
            if sub == "create" and len(r)>=6:
                return "OBJ_CREATE", r[0:6]
        print("comando chart desconhecido ou params insuficientes")
        return None

    # Trade commands: "trade buy/sell/list/closeall"
    if head == "trade":
        if len(parts) < 2: print("uso: trade <buy|sell|list|closeall> ..."); return None
        act = parts[1].lower()
        r = parts[2:]
        if act == "buy" and len(r) >= 1:
            return parse_user_line("buy " + " ".join(r), ctx)
        if act == "sell" and len(r) >= 1:
            return parse_user_line("sell " + " ".join(r), ctx)
        if act == "list": return "TRADE_LIST", []
        if act == "closeall": return "TRADE_CLOSE_ALL", []
        print("uso: trade buy|sell symbol lots [sl] [tp]"); return None

    if head == "use":
        if len(parts) < 3:
            print("uso: use SYMBOL TF")
            return None
        ctx["symbol"] = parts[1]
        ctx["tf"] = parts[2]
        print(f"contexto: SYMBOL={ctx['symbol']} TF={ctx['tf']}")
        return None

    if head in ("ctx","contexto"):
        print(f"contexto: SYMBOL={ctx.get('symbol','')} TF={ctx.get('tf','')} SUB={ctx.get('sub','')}")
        return None

    # Debug para log do MT5
    if head in ("debug", "dbg"):
        if len(parts) < 2:
            print("uso: debug MSG")
            return None
        return "DEBUG_MSG", [" ".join(parts[1:])]

    # Template direto
    if head == "template" and len(parts) >= 5:
        act = parts[1].lower(); sym=parts[2]; tf=parts[3]; tpl=parts[4]
        if act == "apply": return "APPLY_TPL", [sym, tf, tpl]
        if act == "save":  return "SAVE_TPL",  [sym, tf, tpl]
        print("uso: template apply|save SYMBOL TF TPL"); return None

    # Globals simples
    if head in ("set","gset") and len(parts)>=3: return "GLOBAL_SET",[parts[1], parts[2]]
    if head in ("get","gget") and len(parts)>=2: return "GLOBAL_GET",[parts[1]]
    if head in ("del","gdel") and len(parts)>=2: return "GLOBAL_DEL",[parts[1]]
    if head in ("delprefix","gdelprefix") and len(parts)>=2: return "GLOBAL_DEL_PREFIX",[parts[1]]
    if head in ("glist","listglobals"):
        pref = parts[1] if len(parts)>=2 else ""
        lim  = parts[2] if len(parts)>=3 else ""
        params=[]; 
        if pref: params.append(pref)
        if lim: params.append(lim)
        return "GLOBAL_LIST", params

    # ---- Aliases curtos anteriores ----
    alias = {
        "oc":"open","openchart":"open",
        "charts":"charts","listcharts":"charts","lc":"charts",
        "tpl":"applytpl","tplapply":"applytpl","tplsave":"savetpl","savetpl":"savetpl",
        "close":"closechart","cc":"closechart",
        "buy":"buy","sell":"sell",
        "pos":"positions","positions":"positions","trades":"positions",
        "tclose":"tcloseall","tcloseall":"tcloseall","closepos":"tcloseall","closepositions":"tcloseall",
        "redraw":"redraw","detachall":"detachall",
        "wfind":"windowfind",
        "li":"listinputs","setinp":"setinput",
        "shot":"screenshot","ss":"screenshot_sweep",
        "objlist":"obj_list","objs":"obj_list",
        "objdel":"obj_delete","objdelp":"obj_delete_prefix",
        "objmove":"obj_move","objcreate":"obj_create",
        "gs":"gset","gg":"gget","gd":"gdel","gdp":"gdelprefix","gl":"glist",
        "dbg":"debug",
        "mt5compile":"compile",
        "comp":"compile",
        "compile_service":"compile",
        "indget":"indhandle",
        "indrelease":"indrelease",
        "chartsavetpl":"chartsavetpl",
        "chartsave":"chartsavetpl",
        "savetplea":"savetplea",
    }
    cmd = alias.get(parts[0].lower(), parts[0].lower())

    if cmd == "help":
        print(
            "\nComandos (resumo):\n"
            "  Básico     : ping | debug MSG | use SYMBOL TF | ctx | help | exemplos [cmd]\n"
            "  Charts     : open [SYMBOL] [TF] | charts | closechart [SYMBOL] [TF] | closeall | redraw [SYMBOL] [TF] | detachall [SYMBOL] [TF] | windowfind [SYMBOL] [TF] NAME | drop_info\n"
            "  Templates  : applytpl [SYMBOL] [TF] TEMPLATE | savetpl [SYMBOL] [TF] TEMPLATE | chartsavetpl CHART_ID NAME | savetplea EA OUT_TPL [BASE_TPL] [k=v;...]\n"
            "  Indicadores: attach (att) ind ... | deattach (dtt) ind ... | indtotal ... | indname ... | indhandle ... | indget ... | indrelease HANDLE\n"
            "  Experts    : attach (att) ea ... | deattach (dtt) ea ... | findea NOME\n"
            "  Scripts    : attach (att) run [SYMBOL] [TF] TEMPLATE\n"
            "  Trades     : buy [SYMBOL] LOTS [sl] [tp] | sell [SYMBOL] LOTS [sl] [tp] | positions | tcloseall|closepos\n"
            "  Globais    : gset NAME VALUE | gget NAME | gdel NAME | gdelprefix PREFIX | glist [PREFIX [LIMIT]]\n"
            "  Inputs     : listinputs | setinput NAME VAL\n"
            "  Snapshot   : snapshot_save NAME | snapshot_apply NAME | snapshot_list\n"
            "  Objetos    : obj_list [PREFIX] | obj_delete NAME | obj_delete_prefix PREFIX | obj_move NAME TIME PRICE [INDEX] | obj_create TYPE NAME TIME PRICE TIME2 PRICE2\n"
            "  Screens    : screenshot SYMBOL TF FILE WIDTH [HEIGHT] | screenshot_sweep ...\n"
            "  Serviço    : compile ARQUIVO|NOME | compile service NOME | compile here | compile all | service start NOME | service stop NOME\n"
            "  Hotkeys    : hotkeys | hotkey save NOME \"CMD; CMD\" | hotkey run NOME | hotkey show NOME | hotkey del NOME | hotkey <seq> [save NOME]\n"
            "  INI        : ini set/get/list/sync\n"
            "  Tester     : tester ... | run CAMINHO --ind|--ea ... | logs [last|ARQUIVO.log] [N]\n"
            "  Outros     : cmd TYPE [PARAMS...] | selftest [full|compile] | raw <linha> | json <json> | quit\n"
            "\nComandos principais:\n"
            "  attach (att) ind ... | attach (att) ea ... | attach (att) run ...\n"
            "  deattach (dtt) ind ... | deattach (dtt) ea ...\n"
            "\nObs: default = EURUSD H1 (se não informar SYMBOL/TF)\n"
            "Obs: ';' separa múltiplos comandos. No modo não-interativo use aspas SOMENTE com ';':\n"
            "      python cmdmt.py \"open EURUSD H1; attach ind ZigZag 1\"\n"
        )
        return None

    if cmd == "exemplos":
        topic = " ".join(parts[1:]).strip().lower()
        if topic:
            if topic in ("attach","att","anexar","ind","indicador","indicator","ea","expert","run","script","scr"):
                print(
                    "\nExemplos - attach:\n"
                    "  attach ind EURUSD H1 ZigZag sub=1 depth=12 deviation=5 backstep=3\n"
                    "  attach ind EURUSD H1 CustomInd sub=2 -- k1=v1 k2=v2\n"
                    "  attach ea EURUSD H1 MyEA lot=0.1 --debug\n"
                    "  attach run EURUSD H1 MyScript\n"
                )
                return None
            if topic in ("deattach","dtt","detach","desanexar","remove","remover"):
                print(
                    "\nExemplos - deattach:\n"
                    "  deattach ind EURUSD H1 ZigZag sub=1\n"
                    "  deattach ind EURUSD H1 CustomInd sub=2\n"
                    "  deattach ea EURUSD H1\n"
                )
                return None
            if topic in ("tpl","template","templates","applytpl","savetpl"):
                print(
                    "\nExemplos - templates:\n"
                    "  applytpl EURUSD H1 \"Moving Average\"\n"
                    "  savetpl EURUSD H1 MinhaTemplate\n"
                    "  chartsavetpl 123456 MinhaTemplate\n"
                )
                return None
            if topic in ("snapshot","snap","screenshot","screen"):
                print(
                    "\nExemplos - snapshot/screen:\n"
                    "  snapshot_save teste | snapshot_list | snapshot_apply teste\n"
                    "  screenshot EURUSD H1 MQL5\\\\Files\\\\shot.png 1280 720\n"
                )
                return None
            if topic in ("trade","buy","sell","positions","tcloseall"):
                print(
                    "\nExemplos - trades:\n"
                    "  buy EURUSD 0.10 1.0900 1.1100\n"
                    "  sell EURUSD 0.10 1.0900 1.1100\n"
                    "  positions | tcloseall\n"
                )
                return None
            if topic in ("service","compile","tester","run"):
                print(
                    "\nExemplos - serviço/tester:\n"
                    "  compile service SocketTelnetService\n"
                    "  compile here\n"
                    "  service start SocketTelnetService\n"
                )
                return None
        print(
            "\nExemplos rápidos:\n"
            "  ping\n"
            "  use EURUSD H1\n"
            "  open EURUSD H1\n"
            "  charts\n"
            "  attach ind EURUSD H1 ZigZag sub=1 depth=12 deviation=5 backstep=3\n"
            "  deattach ind EURUSD H1 ZigZag sub=1\n"
            "  attach ea EURUSD H1 MyEA lot=0.1\n"
            "  attach run EURUSD H1 MyScript\n"
            "  applytpl EURUSD H1 \"Moving Average\"\n"
            "  snapshot_save teste | snapshot_list | snapshot_apply teste\n"
            "  buy EURUSD 0.10 1.0900 1.1100\n"
            "  tcloseall\n"
            "  obj_create HLINE linha1 0 1.2345 0 0\n"
            "  screenshot EURUSD H1 MQL5\\\\Files\\\\shot.png 1280 720\n"
            "  compile service SocketTelnetService\n"
            "\nDica: exemplos <cmd> (ex: exemplos attach)\n"
        )
        return None

    if cmd in ("attachind","detachind","attachea","detachea","runscript","attach_ea"):
        print("comando desativado: use attach/deattach (ex: attach ind ... | attach ea ... | attach run ...)")
        return None

    if cmd == "ping":
        return "PING", []
    if cmd in ("attach","att"):
        if len(parts) < 2:
            print("uso: attach (att) ind|ea|run [SYMBOL] [TF] NOME [SUB|sub=N] [k=v ...]")
            return None
        sub = parts[1].lower()
        if sub in ("ind","indicador","indicator","i"):
            if len(parts) < 3:
                print("uso: attach (att) ind [SYMBOL] [TF] NOME [SUB|sub=N] [k=v ...]")
                return None
            return _cmd_attachind_args(parts[2:], ctx)
        if sub in ("ea","expert","e","robo","robot","advisor"):
            if len(parts) < 3:
                print("uso: attach (att) ea [SYMBOL] [TF] NOME [k=v ...]")
                return None
            return _cmd_attachea_args(parts[2:], ctx)
        if sub in ("run","script","scr","s"):
            if len(parts) < 3:
                print("uso: attach (att) run [SYMBOL] [TF] TEMPLATE")
                return None
            return _cmd_runscript_args(parts[2:], ctx)
        print("uso: attach (att) ind|ea|run [SYMBOL] [TF] NOME [SUB|sub=N] [k=v ...]")
        return None
    if cmd in ("deattach","dtt"):
        if len(parts) < 2:
            print("uso: deattach (dtt) ind|ea [SYMBOL] [TF] NOME [SUB|sub=N]")
            return None
        sub = parts[1].lower()
        if sub in ("ind","indicador","indicator","i"):
            if len(parts) < 3:
                print("uso: deattach (dtt) ind [SYMBOL] [TF] NOME [SUB|sub=N]")
                return None
            return _cmd_detachind_args(parts[2:], ctx)
        if sub in ("ea","expert","e","robo","robot","advisor"):
            return _cmd_detachea_args(parts[2:], ctx)
        print("uso: deattach (dtt) ind|ea [SYMBOL] [TF] NOME [SUB|sub=N]")
        return None
    if cmd == "open":
        sym, tf, _ = parse_sym_tf(parts[1:], ctx)
        if not ensure_ctx(ctx, not sym, not tf):
            return None
        return "OPEN_CHART", [sym, tf]
    if cmd in ("charts", "listcharts"):
        return "LIST_CHARTS", []
    if cmd in ("cmd+hotkeys", "cmd+hotkey"):
        return "HOTKEY_HELP", ["full"]
    if cmd in ("hotkeys", "hotkey", "hk"):
        # hotkeys -> lista/uso; hotkey <seq> [save NAME] -> salva ou executa
        if len(parts) == 1:
            return "HOTKEY_HELP", []
        action = parts[1].lower()
        if action in ("list", "ls"):
            return "HOTKEY_LIST", []
        if action in ("show", "get") and len(parts) >= 3:
            return "HOTKEY_SHOW", [_normalize_hotkey_name(parts[2])]
        if action in ("del", "rm", "remove") and len(parts) >= 3:
            return "HOTKEY_DEL", [_normalize_hotkey_name(parts[2])]
        if action in ("save", "set") and len(parts) >= 4:
            name = _normalize_hotkey_name(parts[2])
            seq = " ".join(parts[3:]).strip()
            return "HOTKEY_SAVE", [name, seq]
        if action in ("run", "exec") and len(parts) >= 3:
            return "HOTKEY_RUN", [_normalize_hotkey_name(parts[2])]
        # caso geral: hotkey <sequencia> [save NOME]
        seq = " ".join(parts[1:]).strip()
        return "HOTKEY_INLINE", [seq]
    if cmd == "buy" and len(parts) >= 2:
        r = parts[1:]
        if is_number(r[0]):
            if not ensure_ctx(ctx, need_sym=True, need_tf=False):
                return None
            sym = ctx.get("symbol")
            return "TRADE_BUY", [sym] + r[0:3]
        else:
            return "TRADE_BUY", r[0:4]
    if cmd == "sell" and len(parts) >= 2:
        r = parts[1:]
        if is_number(r[0]):
            if not ensure_ctx(ctx, need_sym=True, need_tf=False):
                return None
            sym = ctx.get("symbol")
            return "TRADE_SELL", [sym] + r[0:3]
        else:
            return "TRADE_SELL", r[0:4]
    if cmd in ("positions","pos","trades"):
        return "TRADE_LIST", []
    if cmd in ("tcloseall","closepos","closepositions","tclose"):
        return "TRADE_CLOSE_ALL", []
    if cmd == "applytpl" and len(parts) >= 2:
        r = parts[1:]
        tpl = r[-1] if r else ""
        if not tpl:
            print("uso: applytpl [SYMBOL] [TF] TEMPLATE"); return None
        r = r[:-1]
        sym, tf, _ = parse_sym_tf(r, ctx)
        if not ensure_ctx(ctx, not sym, not tf):
            return None
        return "APPLY_TPL", [sym, tf, tpl]
    if cmd == "savetpl" and len(parts) >= 2:
        r = parts[1:]
        tpl = r[-1] if r else ""
        if not tpl:
            print("uso: savetpl [SYMBOL] [TF] TEMPLATE"); return None
        r = r[:-1]
        sym, tf, _ = parse_sym_tf(r, ctx)
        if not ensure_ctx(ctx, not sym, not tf):
            return None
        return "SAVE_TPL", [sym, tf, tpl]
    if cmd == "savetplea" and len(parts) >= 3:
        ea = parts[1]
        out_tpl = parts[2]
        base_tpl = ""
        params_tokens = parts[3:]
        if params_tokens:
            if params_tokens[0].lower().startswith("base="):
                base_tpl = params_tokens[0][5:]
                params_tokens = params_tokens[1:]
                # suporte a base template com espaços (ex: "Moving Average.tpl")
                if base_tpl and not base_tpl.lower().endswith(".tpl") and params_tokens:
                    if params_tokens[0].lower().endswith(".tpl"):
                        base_tpl = base_tpl + " " + params_tokens[0]
                        params_tokens = params_tokens[1:]
            elif params_tokens[0].lower().endswith(".tpl"):
                base_tpl = params_tokens[0]
                params_tokens = params_tokens[1:]
        pstr = " ".join(params_tokens).strip()
        return "SAVE_TPL_EA", [ea, out_tpl, base_tpl, pstr]
    if cmd == "closechart":
        sym, tf, _ = parse_sym_tf(parts[1:], ctx)
        if not ensure_ctx(ctx, not sym, not tf):
            return None
        return "CLOSE_CHART", [sym, tf]
    if cmd == "redraw":
        sym, tf, _ = parse_sym_tf(parts[1:], ctx)
        if not ensure_ctx(ctx, not sym, not tf):
            return None
        return "REDRAW_CHART", [sym, tf]
    if cmd == "detachall":
        sym, tf, _ = parse_sym_tf(parts[1:], ctx)
        if not ensure_ctx(ctx, not sym, not tf):
            return None
        return "DETACH_ALL", [sym, tf]
    if cmd == "windowfind":
        sym, tf, rem = parse_sym_tf(parts[1:], ctx)
        if not ensure_ctx(ctx, not sym, not tf):
            return None
        if len(rem) < 1:
            print("uso: windowfind [SYMBOL] [TF] NAME"); return None
        return "WINDOW_FIND", [sym, tf, rem[0]]
    if cmd == "closeall":
        return "CLOSE_ALL", []
    if cmd == "indtotal" and len(parts) >= 1:
        r = parts[1:]
        sub = str(ctx.get("sub",1))
        sym=None; tf=None
        if len(r)==0:
            sym=ctx.get("symbol"); tf=ctx.get("tf")
        elif len(r)==1:
            if r[0].isdigit():
                sub=r[0]; sym=ctx.get("symbol"); tf=ctx.get("tf")
            elif is_tf(r[0]):
                sym=ctx.get("symbol"); tf=r[0]
            else:
                sym=r[0]; tf=ctx.get("tf")
        else:
            if is_tf(r[1]):
                sym=r[0]; tf=r[1]
                if len(r)>=3 and r[2].isdigit(): sub=r[2]
            else:
                sym=r[0]; tf=ctx.get("tf")
                if len(r)>=2 and r[1].isdigit(): sub=r[1]
        if not ensure_ctx(ctx, not sym, not tf): return None
        return "IND_TOTAL", [sym, tf, sub]
    if cmd == "indname" and len(parts) >= 2:
        r = parts[1:]
        idx = r[-1] if r else ""
        if not idx.isdigit():
            print("uso: indname [SYMBOL] [TF] [SUB] INDEX"); return None
        r = r[:-1]
        sub = str(ctx.get("sub",1))
        if len(r)>=1 and r[-1].isdigit():
            sub = r[-1]; r = r[:-1]
        sym, tf, _ = parse_sym_tf(r, ctx)
        if not ensure_ctx(ctx, not sym, not tf): return None
        return "IND_NAME", [sym, tf, sub, idx]
    if cmd == "indhandle" and len(parts) >= 2:
        r = parts[1:]
        name = r[-1] if r else ""
        if not name:
            print("uso: indhandle [SYMBOL] [TF] [SUB] NAME"); return None
        r = r[:-1]
        sub = str(ctx.get("sub",1))
        if len(r)>=1 and r[-1].isdigit():
            sub = r[-1]; r = r[:-1]
        sym, tf, _ = parse_sym_tf(r, ctx)
        if not ensure_ctx(ctx, not sym, not tf): return None
        return "IND_HANDLE", [sym, tf, sub, name]
    if cmd == "indrelease" and len(parts) >= 2:
        return "IND_RELEASE", [parts[1]]
    if cmd == "chartsavetpl" and len(parts) >= 3:
        chart_id = parts[1]
        name = " ".join(parts[2:])
        if not chart_id.isdigit():
            print("uso: chartsavetpl CHART_ID NAME"); return None
        return "CHART_SAVE_TPL", [chart_id, name]
    if cmd == "gset" and len(parts) >= 3:
        return "GLOBAL_SET", [parts[1], parts[2]]
    if cmd == "gget" and len(parts) >= 2:
        return "GLOBAL_GET", [parts[1]]
    if cmd == "gdel" and len(parts) >= 2:
        return "GLOBAL_DEL", [parts[1]]
    if cmd == "gdelprefix" and len(parts) >= 2:
        return "GLOBAL_DEL_PREFIX", [parts[1]]
    if cmd == "glist":
        pref = parts[1] if len(parts) >= 2 else ""
        lim  = parts[2] if len(parts) >= 3 else ""
        params = [pref] if pref else []
        if lim: params.append(lim)
        return "GLOBAL_LIST", params
    if cmd == "findea" and len(parts) >= 2:
        name = " ".join(parts[1:])
        return "FIND_EA", [name]
    # aliases legado
    if cmd == "closetpl":
        return parse_user_line("closechart " + " ".join(parts[1:]), ctx)
    if cmd == "listinputs":
        return "LIST_INPUTS", parts[1:]
    if cmd == "setinput":
        if len(parts) >= 3:
            return "SET_INPUT", [parts[1], parts[2]]
        if len(parts) == 2 and "=" in parts[1]:
            k, v = parts[1].split("=", 1)
            return "SET_INPUT", [k, v]
        print("uso: setinput NAME VAL")
        return None
    if cmd == "snapshot_save" and len(parts) >= 2:
        return "SNAPSHOT_SAVE", [parts[1]]
    if cmd == "snapshot_apply" and len(parts) >= 2:
        return "SNAPSHOT_APPLY", [parts[1]]
    if cmd == "snapshot_list":
        return "SNAPSHOT_LIST", []
    if cmd == "obj_list":
        pref = parts[1] if len(parts) >=2 else ""
        return "OBJ_LIST", [pref] if pref else []
    if cmd == "obj_delete" and len(parts) >= 2:
        return "OBJ_DELETE", [parts[1]]
    if cmd == "obj_delete_prefix" and len(parts) >= 2:
        return "OBJ_DELETE_PREFIX", [parts[1]]
    if cmd == "obj_move" and len(parts) >= 4:
        params = [parts[1], parts[2], parts[3]]
        if len(parts)>=5: params.append(parts[4])
        return "OBJ_MOVE", params
    if cmd == "obj_create" and len(parts) >= 7:
        return "OBJ_CREATE", parts[1:7]
    if cmd == "screenshot" and len(parts) >= 2:
        r = parts[1:]
        if len(r) >= 3 and is_tf(r[1]):
            params = r[0:3]
            if len(r) >= 4: params.append(r[3])
            if len(r) >= 5: params.append(r[4])
            return "SCREENSHOT", params
        if not ensure_ctx(ctx, True, True): return None
        file = r[0]
        params = [ctx.get("symbol"), ctx.get("tf"), file]
        if len(r) >= 2: params.append(r[1])
        if len(r) >= 3: params.append(r[2])
        return "SCREENSHOT", params
    if cmd == "screenshot_sweep":
        r = parts[1:]
        if len(r) >= 11 and len(r) >= 2 and is_tf(r[1]):
            return "SCREENSHOT_SWEEP", r
        if len(r) >= 9:
            if not ensure_ctx(ctx, True, True): return None
            params = [ctx.get("symbol"), ctx.get("tf")] + r
            return "SCREENSHOT_SWEEP", params
        print("uso: screenshot_sweep [SYMBOL] [TF] FOLDER BASE STEPS SHIFT ALIGN WIDTH HEIGHT FMT DELAY")
        return None
    if cmd == "drop_info":
        return "DROP_INFO", parts[1:]
    if cmd == "raw":
        payload = line[len("raw "):].strip()
        return "RAW", [payload]
    if cmd == "json":
        payload = line[len("json "):].strip()
        return "JSON", [payload]
    # fallback: permite enviar TYPE direto (ex: DEBUG_MSG, DETACH_EA_FULL)
    if cmd.isupper() or "_" in cmd:
        return cmd.upper(), parts[1:]

    print(f"comando desconhecido: {cmd} (digite help)")
    return None

# ------------------- Sequência no modo interativo -------------------
def split_seq_line(line: str):
    parts = []
    buf = []
    quote = None  # "'" or '"'
    for ch in line:
        if ch in ("'", '"'):
            if quote is None:
                quote = ch
            elif quote == ch:
                quote = None
            buf.append(ch)
            continue
        if ch == ";" and quote is None:
            part = "".join(buf).strip()
            if part:
                parts.append(part)
            buf = []
            continue
        buf.append(ch)
    part = "".join(buf).strip()
    if part:
        parts.append(part)
    return parts

def parse_response_text(resp_txt: str):
    txt = resp_txt.strip()
    if not txt:
        return False, "empty", []
    try:
        obj = json.loads(txt)
        if isinstance(obj, dict):
            if "resp" in obj:
                return parse_response_text(str(obj.get("resp", "")))
            if "ok" in obj:
                ok = bool(obj.get("ok"))
                msg = obj.get("error") or obj.get("msg") or ("ok" if ok else "error")
                return ok, str(msg), []
        return True, txt, []
    except Exception:
        pass
    lines = txt.replace("\r", "").splitlines()
    if lines and (lines[0] == "OK" or lines[0] == "ERROR"):
        msg = lines[1] if len(lines) >= 2 else ""
        data = lines[2:] if len(lines) >= 3 else []
        return lines[0] == "OK", msg, data
    return True, txt, []

def run_selftest(transport, ctx, mode: str):
    full = mode in ("full", "completo")
    do_compile = mode in ("full", "completo", "compile", "compilar")
    sym = ctx.get("symbol")
    tf = ctx.get("tf")

    def send_cmd(cmd_type, params):
        line_out = "|".join([gen_id(), cmd_type] + params)
        resp_txt = transport.send_text(line_out)
        return parse_response_text(resp_txt)

    def run(name, cmd_type, params, need_sym_tf=False):
        if need_sym_tf and (not sym or not tf):
            print(f"[{name}] SKIP (defina SYMBOL/TF com 'use SYMBOL TF')") 
            return True
        ok, msg, _ = send_cmd(cmd_type, params)
        status = "OK" if ok else "ERROR"
        print(f"[{name}] {status} {msg}")
        return ok

    all_ok = True
    all_ok &= run("ping", "PING", [])
    all_ok &= run("open_chart", "OPEN_CHART", [sym or "", tf or ""], need_sym_tf=True)
    run("list_charts", "LIST_CHARTS", [])
    run("redraw", "REDRAW_CHART", [sym or "", tf or ""], need_sym_tf=True)
    run("drop_info", "DROP_INFO", [])

    # snapshot
    run("snapshot_save", "SNAPSHOT_SAVE", ["cmdmt_selftest"])
    run("snapshot_list", "SNAPSHOT_LIST", [])
    run("snapshot_apply", "SNAPSHOT_APPLY", ["cmdmt_selftest"])

    # screenshot
    run("screenshot", "SCREENSHOT", [sym or "", tf or "", "MQL5\\Files\\cmdmt_selftest.png", "1280", "720"], need_sym_tf=True)

    if do_compile:
        if find_mt5_compiler() and find_terminal_data_dir():
            okc = run_mt5_compile_service()
            if not okc:
                all_ok = False
        else:
            print("[compile] SKIP (compiler/terminal não encontrado)")

    if full:
        run(
            "screenshot_sweep",
            "SCREENSHOT_SWEEP",
            [sym or "", tf or "", "MQL5\\Files", "cmdmt_sweep", "3", "50", "left", "1280", "720", "png", "50"],
            need_sym_tf=True,
        )

    print("selftest concluído")
    return all_ok

# ------------------- Main -------------------
def main():
    ap = argparse.ArgumentParser(description="CMD MT (socket)")
    ap.add_argument("--transport", choices=["socket", "file"], default="socket", help="transporte: socket ou file (cmd_/resp_)")
    ap.add_argument("--host", default=DEFAULT_HOSTS, help="host do serviço/gateway (socket). Suporta lista h1,h2 para fallback")
    ap.add_argument("--port", type=int, default=DEFAULT_PORT, help="porta (socket) (gateway 9095, serviço MT5 9090)")
    ap.add_argument("--timeout", type=float, default=6.0, help="timeout (s)")
    ap.add_argument("--dir", help="dir do MQL5/Files para modo file (cmd_/resp_)", default=None)
    ap.add_argument("--symbol", help="symbol padrão (ex: EURUSD)", default=None)
    ap.add_argument("--tf", help="timeframe padrão (ex: H1)", default=None)
    ap.add_argument("--sub", help="subwindow padrão para indicadores", default=None)
    ap.add_argument("--file", help="arquivo texto com um comando por linha (modo não interativo)", default=None)
    ap.add_argument("command", nargs="*", help="comando direto (ex: ping, \"chart list\")")
    args, extra = ap.parse_known_args()
    # anexa argumentos desconhecidos ao comando (ex: --ind/--ea no modo direto)
    if extra:
        if args.command is None:
            args.command = []
        args.command.extend(extra)

    ctx = {}
    ctx["symbol"] = args.symbol or DEFAULT_SYMBOL
    ctx["tf"] = args.tf or DEFAULT_TF
    if args.sub is not None:
        try:
            ctx["sub"] = int(args.sub)
        except Exception:
            ctx["sub"] = 1
    if "sub" not in ctx or ctx.get("sub") is None:
        ctx["sub"] = 1

    if args.transport == "file" or args.dir:
        if not args.dir:
            ap.error("--dir obrigatório quando --transport file")
        files_dir = maybe_wslpath(args.dir)
        transport = TransportFile(files_dir, args.timeout)
        set_blue(); print(f"MT5 CLI (file) {files_dir}")
    else:
        transport = TransportSocket(args.host, args.port, args.timeout)
        set_blue(); print(f"MT5 CLI (socket) {args.host}:{args.port}")
    print("Dica: digite help")

    # tenta sincronizar defaults com um chart aberto (sem exigir SYMBOL/TF do usuário)
    if isinstance(transport, TransportSocket):
        try:
            line_out = "|".join([gen_id(), "LIST_CHARTS"])
            resp_txt = transport.send_text(line_out)
            ok, msg, data = parse_response_text(resp_txt)
            if ok and data:
                parts = data[0].split("|")
                if len(parts) >= 3:
                    ctx["symbol"] = parts[1].strip()
                    tf_raw = parts[2].strip()
                    if tf_raw.upper().startswith("PERIOD_"):
                        tf_raw = tf_raw[7:]
                    if tf_raw.upper() != "CURRENT":
                        ctx["tf"] = tf_raw
            else:
                line_out = "|".join([gen_id(), "DROP_INFO"])
                resp_txt = transport.send_text(line_out)
                ok, msg, data = parse_response_text(resp_txt)
                if ok and data:
                    first = data[0].strip()
                    if first.lower().startswith("chart="):
                        rest = first.split("=", 1)[1].strip()
                        parts = rest.split()
                        if len(parts) >= 2:
                            ctx["symbol"] = parts[0]
                            tf_raw = parts[1]
                            if tf_raw.upper().startswith("PERIOD_"):
                                tf_raw = tf_raw[7:]
                            if tf_raw.upper() != "CURRENT":
                                ctx["tf"] = tf_raw
        except Exception:
            pass

    # Fonte de comandos não interativa: positional, --file ou stdin pipe
    lines = None
    if args.command:
        if len(args.command) == 1:
            line_raw = args.command[0]
            # fora do interativo, aspas só fazem sentido com ';' ou payloads especiais
            if " " in line_raw and ";" not in line_raw:
                low = line_raw.lstrip().lower()
                allow = False
                if low.startswith(("raw ", "json ")):
                    allow = True
                if any(ch in line_raw for ch in ("|", "&", "<", ">")):
                    allow = True
                if not allow:
                    print("ERROR: no modo nao-interativo use sem aspas; use aspas apenas com ';' (sequencia) ou raw/json")
                    reset_color()
                    return
            lines = [line_raw]
        else:
            lines = [" ".join(args.command)]
    elif args.file is not None:
        with open(args.file, "r", encoding="utf-8", errors="ignore") as f:
            lines = [ln.strip() for ln in f.readlines() if ln.strip()!=""]
    elif not sys.stdin.isatty():
        lines = [ln.rstrip("\n") for ln in sys.stdin.readlines() if ln.strip()!=""]

    def process_line(line: str):
        # permite chamar hotkey só digitando o código (ex: A1 ou @A1)
        line_str = line.strip()
        if line_str:
            hk = _load_hotkeys()
            key = _normalize_hotkey_name(line_str)
            if key in hk:
                # executa e retorna (com proteção de recursão)
                def _run_direct_hotkey(code: str, stack=None):
                    if stack is None:
                        stack = []
                    if code in stack:
                        print(f"ERROR hotkey recursion: {' -> '.join(stack+[code])}")
                        return
                    seq = hk.get(code, "")
                    if not seq:
                        print(f"ERROR hotkey not found: {code}")
                        return
                    stack.append(code)
                    for ln in split_seq_line(seq):
                        ln = ln.strip()
                        if not ln:
                            continue
                        process_line(ln)
                    stack.pop()
                _run_direct_hotkey(key)
                return
        parsed = parse_user_line(line, ctx)
        if not parsed:
            return
        cmd_type, params = parsed
        cmd_id = gen_id()

        if cmd_type == "INI_SET":
            root = _find_rach_root()
            if not root:
                print("ERROR terminal_root_not_found (esperado ./Terminal dentro do repo)")
                return
            ok, msg = _ini_set(root, params)
            if ok:
                print(f"OK ini set ({msg})")
            else:
                print(f"ERROR {msg}")
            return
        if cmd_type == "INI_GET":
            root = _find_rach_root()
            if not root:
                print("ERROR terminal_root_not_found (esperado ./Terminal dentro do repo)")
                return
            ok, res = _ini_get(root, params)
            if ok:
                for ln in res:
                    print(ln)
            else:
                print("ERROR ini get")
            return
        if cmd_type == "INI_LIST":
            root = _find_rach_root()
            if not root:
                print("ERROR terminal_root_not_found (esperado ./Terminal dentro do repo)")
                return
            ok, res = _ini_list(root)
            if ok:
                for ln in res:
                    print(ln)
            else:
                print("ERROR ini list")
            return
        if cmd_type == "INI_SYNC":
            root = _find_rach_root()
            if not root:
                print("ERROR terminal_root_not_found (esperado ./Terminal dentro do repo)")
                return
            ok, msg = _ini_sync(root)
            if ok:
                print("OK ini sync (" + msg + ")")
            else:
                print("ERROR " + msg)
            return

        def send_cmd(cmd_type_inner, params_inner):
            line_out = "|".join([gen_id(), cmd_type_inner] + params_inner)
            resp_txt = transport.send_text(line_out)
            txt = resp_txt.strip()
            lines_out = txt.splitlines()
            if len(lines_out) >= 1 and (lines_out[0] == "OK" or lines_out[0] == "ERROR"):
                ok = lines_out[0] == "OK"
                msg = lines_out[1] if len(lines_out) >= 2 else ""
                data = lines_out[2:]
                return ok, msg, data
            return False, txt, []
        def run_hotkey(code: str, stack=None):
            if stack is None:
                stack = []
            if code in stack:
                print(f"ERROR hotkey recursion: {' -> '.join(stack+[code])}")
                return
            hk = _load_hotkeys()
            if code not in hk:
                print(f"ERROR hotkey not found: {code}")
                return
            seq = hk[code]
            stack.append(code)
            for ln in split_seq_line(seq):
                ln = ln.strip()
                if not ln:
                    continue
                # permite chamar outro hotkey via linha "hotkey run X"
                process_line(ln)
            stack.pop()
        try:
            if cmd_type == "SELFTEST":
                mode = params[0] if params else "quick"
                run_selftest(transport, ctx, mode)
                return
            if cmd_type == "HOTKEY_HELP":
                hk = _load_hotkeys()
                print("Hotkeys (atalhos CMDMT):")
                if hk:
                    for k in sorted(hk.keys()):
                        print(f"  {k} -> {hk[k]}")
                else:
                    print("  (vazio)")
                print("")
                print("Uso:")
                print("  hotkey save NOME \"CMD; CMD\"")
                print("  hotkey run NOME | hotkey show NOME | hotkey del NOME")
                print("  hotkey <sequencia> [save NOME]")
                print("  digite NOME ou @NOME (somente @ no inicio)")
                if params and params[0] == "full":
                    print("")
                    print("Exemplo:")
                    print("  hotkey save salvar \"open EURUSD H1; attach ind ZigZag 1\"")
                    print("  salvar")
                return
            if cmd_type == "HOTKEY_LIST":
                hk = _load_hotkeys()
                if not hk:
                    print("hotkeys: (vazio)")
                else:
                    for k in sorted(hk.keys()):
                        print(f"{k} -> {hk[k]}")
                return
            if cmd_type == "HOTKEY_SHOW":
                code = _normalize_hotkey_name(params[0]) if params else ""
                hk = _load_hotkeys()
                if code in hk:
                    print(f"{code} -> {hk[code]}")
                else:
                    print(f"ERROR hotkey not found: {code}")
                return
            if cmd_type == "HOTKEY_SAVE":
                name = _normalize_hotkey_name(params[0]) if params else ""
                seq = params[1] if len(params) >= 2 else ""
                if not name or not seq:
                    print("uso: hotkey save NOME \"CMD; CMD\"")
                    return
                code = name.strip().upper()
                hk = _load_hotkeys()
                hk[code] = seq
                path = _save_hotkeys(hk)
                print(f"OK hotkey {code} salvo em {path}")
                return
            if cmd_type == "HOTKEY_DEL":
                code = _normalize_hotkey_name(params[0]) if params else ""
                hk = _load_hotkeys()
                if code in hk:
                    hk.pop(code, None)
                    path = _save_hotkeys(hk)
                    print(f"OK hotkey {code} removido ({path})")
                else:
                    print(f"ERROR hotkey not found: {code}")
                return
            if cmd_type == "HOTKEY_RUN":
                code = params[0] if params else ""
                if not code:
                    print("uso: hotkey run NOME")
                    return
                run_hotkey(code)
                return
            if cmd_type == "HOTKEY_INLINE":
                seq = params[0] if params else ""
                if not seq:
                    print("uso: hotkey <sequencia> [save NOME]")
                    return
                # se termina com "save NOME", salva; senão executa
                words = shlex.split(seq)
                if len(words) >= 2 and words[-2].lower() in ("save", "salvar"):
                    name = _normalize_hotkey_name(words[-1])
                    real_seq = " ".join(words[:-2]).strip()
                    if not real_seq:
                        print("uso: hotkey <sequencia> save NOME")
                        return
                    hk = _load_hotkeys()
                    hk[name] = real_seq
                    path = _save_hotkeys(hk)
                    print(f"OK hotkey {name} salvo em {path}")
                else:
                    # executa sequência imediata
                    for ln in split_seq_line(seq):
                        ln = ln.strip()
                        if not ln:
                            continue
                        process_line(ln)
                return
            if cmd_type == "COMPILE":
                target = params[0] if params else ""
                run_mt5_compile(target)
                return
            if cmd_type == "COMPILE_HERE":
                run_mt5_compile_service()
                return
            if cmd_type == "COMPILE_SERVICE_NAME":
                target = params[0] if params else ""
                run_mt5_compile_service_name(target)
                return
            if cmd_type == "COMPILE_ALL":
                run_mt5_compile_all_services()
                return
            if cmd_type == "SERVICE_START":
                target = params[0] if params else ""
                run_mt5_start_service(target)
                return
            if cmd_type == "SERVICE_STOP":
                target = params[0] if params else ""
                run_mt5_stop_service(target)
                return
            if cmd_type == "SERVICE_WINDOWS":
                run_mt5_list_service_windows()
                return
            if cmd_type == "RUN_SIMPLE":
                run_simple(params, ctx)
                return
            if cmd_type == "RUN_LOGS":
                if not params:
                    _list_run_logs()
                else:
                    name = params[0]
                    tail = int(params[1]) if len(params) >= 2 and params[1].isdigit() else 200
                    _show_run_log(name, tail)
                return
            if cmd_type == "TESTER_RUN":
                run_mt5_tester(params)
                return
            if cmd_type == "RAW":
                payload = params[0]
                try:
                    resp_txt = transport.send_text(payload)
                except Exception as e:
                    print(f"ERROR: conexão falhou ({e})")
                    return
                print(resp_txt.strip())
                return
            if cmd_type == "JSON":
                payload = params[0]
                try:
                    obj = json.loads(payload)
                except Exception as e:
                    print(f"JSON inválido: {e}"); return
                try:
                    resp_obj = transport.send_json(obj)
                except Exception as e:
                    print(f"ERROR: conexão falhou ({e})")
                    return
                print(resp_obj)
                return
            if cmd_type == "ATTACH_EA_SMART":
                sym = params[0]
                tf = params[1]
                name = params[2]
                params_str = params[3] if len(params) > 3 else ""
                debug_flag = bool(params[4]) if len(params) > 4 else False
                base_tpl = resolve_base_template()
                tpl_name = ensure_ea_template_from_stub(
                    name,
                    params_str,
                    stub_name="Stub.tpl",
                    base_tpl_name=base_tpl,
                    debug=debug_flag,
                )
                if not tpl_name:
                    print("ERROR stub_create_fail")
                    return
                _dbg(f"send ATTACH_EA_FULL tpl={tpl_name}", debug_flag)
                ok, msg, data = send_cmd("ATTACH_EA_FULL", [sym, tf, tpl_name])
                print(("OK " if ok else "ERROR ") + msg)
                for ln2 in data:
                    print("  " + ln2)
                return
            if cmd_type == "FIND_EA":
                term = find_terminal_data_dir()
                if not term:
                    print("ERROR terminal_dir"); return
                name = params[0]
                rel = resolve_expert_path(term, name)
                experts_dir = term / "MQL5" / "Experts"
                rel_path = Path(*rel.split("\\")) if rel else Path()
                ex5 = experts_dir / (str(rel_path) + ".ex5")
                mq5 = experts_dir / (str(rel_path) + ".mq5")
                if ex5.exists() or mq5.exists():
                    found = str(rel).replace("/", "\\")
                    abs_path = ex5 if ex5.exists() else mq5
                    print("OK " + found)
                    print("  " + str(abs_path))
                else:
                    print("ERROR not_found")
                return

            line_out = "|".join([cmd_id, cmd_type] + params)
            try:
                resp_txt = transport.send_text(line_out)
            except Exception as e:
                print(f"ERROR: conexão falhou ({e})")
                return

            # Se for arquivo, formato OK/ERROR
            txt = resp_txt.strip()
            try:
                resp_obj = json.loads(txt)
                if isinstance(resp_obj, dict):
                    if "resp" in resp_obj:
                        ok, msg, data = parse_response_text(str(resp_obj.get("resp", "")))
                        print(("OK " if ok else "ERROR ") + msg)
                        for ln2 in data:
                            print("  " + ln2)
                    elif "ok" in resp_obj:
                        ok = bool(resp_obj.get("ok"))
                        msg = resp_obj.get("error") or resp_obj.get("msg") or ("ok" if ok else "error")
                        print(("OK " if ok else "ERROR ") + str(msg))
                    else:
                        print(resp_obj)
                else:
                    print(resp_obj)
            except Exception:
                lines_out = txt.splitlines()
                if len(lines_out)>=1 and (lines_out[0]=="OK" or lines_out[0]=="ERROR"):
                    print(lines_out[0] + (" " + lines_out[1] if len(lines_out)>=2 else ""))
                    for ln2 in lines_out[2:]:
                        print("  " + ln2)
                else:
                    print(txt)
        except Exception as e:
            print(f"ERROR: {e}")

    try:
        if lines is not None:
            expanded = []
            for ln in lines:
                if not ln.strip():
                    continue
                for part in split_seq_line(ln):
                    if part.strip():
                        expanded.append(part.strip())
            for ln in expanded:
                process_line(ln)
        else:
            while True:
                try:
                    line = input("mt> ").strip()
                except (EOFError, KeyboardInterrupt):
                    print("\nsaindo...")
                    break
                if not line:
                    continue
                # permite sequências separadas por ';' no modo interativo
                seq_parts = split_seq_line(line)
                for part in seq_parts:
                    if not part:
                        continue
                    if part.lower() in ("quit", "exit"):
                        return
                    process_line(part)
    finally:
        reset_color()

if __name__ == "__main__":
    main()
