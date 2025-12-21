//+------------------------------------------------------------------+
//| CommandBridgeService.mq5                                         |
//| Serviço: despacha comandos via PIPE (mt5_pipe_server.dll)        |
//| Foco em infraestrutura (chart/template/indicadores/globais).     |
//| Não executa trade nem objetos/screenshot.                        |
//+------------------------------------------------------------------+
#property service

// Timer (segundos) para varrer a fila do pipe
input int   InpTimerSec   = 1;
// Nome completo do pipe (ex.: \\.
input string InpPipeName  = "\\\\.\\pipe\\mt5pipe";

#include <PipeBridge.mqh>

string LISTENER_VERSION = "svc-pipe-1.0.1";

// Buffer para receber mensagens
uchar g_buf[65536];

// -------------------------------------------------------------------
// Utilidades
string PayloadGet(const string payload, const string key)
{
  if(payload=="") return "";
  string parts[]; int n=StringSplit(payload, ';', parts);
  for(int i=0;i<n;i++)
  {
    string kv[]; int c=StringSplit(parts[i], '=', kv);
    if(c==2 && kv[0]==key) return kv[1];
  }
  return "";
}

string Join(string &arr[], const string sep)
{
  string out="";
  int n=ArraySize(arr);
  for(int i=0;i<n;i++)
  {
    if(i>0) out+=sep;
    out+=arr[i];
  }
  return out;
}

bool WriteResp(string id, bool ok, string message, string &data[], int pipe_id)
{
  string text = (ok?"OK":"ERROR") + "\n" + message + "\n";
  for(int i=0;i<ArraySize(data);i++) text += data[i] + "\n";
  uchar bytes[];
  StringToCharArray(text, bytes, 0, StringLen(text), CP_UTF8);
  PipeReply(pipe_id, bytes, ArraySize(bytes));
  return true;
}

bool ReadCommandPipe(string &id, string &type, string &params[], int &pipe_id)
{
  int pend = PipePending();
  if(pend<=0) return false;
  int got = PipeNext(g_buf, ArraySize(g_buf), pipe_id);
  if(got<=0) return false;
  string line = CharArrayToString(g_buf, 0, got, CP_UTF8);
  StringReplace(line, "\r", "");
  StringReplace(line, "\n", "");
  string parts[]; int n=StringSplit(line, '|', parts);
  if(n<2) return false;
  id   = parts[0];
  type = parts[1];
  ArrayResize(params, MathMax(0,n-2));
  for(int i=2;i<n;i++) params[i-2]=parts[i];
  return true;
}

// -------------------------------------------------------------------
ENUM_TIMEFRAMES TfFromString(string &tf)
{
  string u=tf; StringToUpper(u);
  if(u=="M1") return PERIOD_M1;
  if(u=="M5") return PERIOD_M5;
  if(u=="M15") return PERIOD_M15;
  if(u=="M30") return PERIOD_M30;
  if(u=="H1") return PERIOD_H1;
  if(u=="H4") return PERIOD_H4;
  if(u=="D1") return PERIOD_D1;
  if(u=="W1") return PERIOD_W1;
  if(u=="MN1") return PERIOD_MN1;
  return (ENUM_TIMEFRAMES)0;
}

int SubwindowSafe(string &val)
{
  if(val=="") return 1;
  int v=(int)StringToInteger(val);
  return (v<=0)?1:v;
}

int ParseParams(string &pstr, string &keys[], string &vals[])
{
  ArrayResize(keys,0);
  ArrayResize(vals,0);
  return 0;
}

int BuildParams(string &pstr, MqlParam &outParams[])
{
  ArrayResize(outParams,0);
  return 0;
}

bool EnsureSymbol(const string sym)
{
  if(SymbolSelect(sym, true)) return true;
  Print("[bridge] SymbolSelect failed for ", sym);
  return false;
}

// -------------------------------------------------------------------
// Handlers (infra)
bool H_Ping(string &p[], string &m, string &d[]) { m="pong "+LISTENER_VERSION; return true; }

bool H_GlobalSet(string &p[], string &m, string &d[])
{
  if(ArraySize(p)<2){ m="params"; return false; }
  string name=p[0]; double val=StringToDouble(p[1]);
  bool ok = GlobalVariableSet(name, val) > 0;
  m = ok?"set":"fail"; return ok;
}
bool H_GlobalGet(string &p[], string &m, string &d[])
{
  if(ArraySize(p)<1){ m="params"; return false; }
  string name=p[0];
  if(!GlobalVariableCheck(name)){ m="not_found"; return false; }
  double v = GlobalVariableGet(name);
  ArrayResize(d,1); d[0]=DoubleToString(v,8);
  m="ok"; return true;
}
bool H_GlobalDel(string &p[], string &m, string &d[])
{
  if(ArraySize(p)<1){ m="params"; return false; }
  m = GlobalVariableDel(p[0]) ? "deleted" : "not_found";
  return (m=="deleted");
}
bool H_GlobalDelPrefix(string &p[], string &m, string &d[])
{
  if(ArraySize(p)<1){ m="params"; return false; }
  string prefix=p[0];
  int total=GlobalVariablesTotal();
  int removed=0;
  for(int i=0;i<total;i++)
  {
    string nm=GlobalVariableName(i);
    if(StringFind(nm, prefix)==0)
    {
      if(GlobalVariableDel(nm)) removed++;
    }
  }
  m=StringFormat("removed=%d", removed); return true;
}
bool H_GlobalList(string &p[], string &m, string &d[])
{
  string prefix = (ArraySize(p)>0)?p[0]:"";
  int limit = (ArraySize(p)>1)?(int)StringToInteger(p[1]):0;
  int total=GlobalVariablesTotal();
  int count=0;
  for(int i=0;i<total;i++)
  {
    string nm=GlobalVariableName(i);
    if(prefix!="" && StringFind(nm,prefix)!=0) continue;
    double v=GlobalVariableGet(nm);
    ArrayResize(d,ArraySize(d)+1); d[ArraySize(d)-1]=nm+"="+DoubleToString(v,8);
    count++;
    if(limit>0 && count>=limit) break;
  }
  m=StringFormat("vars=%d", count); return true;
}

bool H_OpenChart(string &p[], string &m, string &d[])
{
  if(ArraySize(p)<2){ m="params"; return false; }
  string sym=p[0]; ENUM_TIMEFRAMES tf=TfFromString(p[1]);
  if(tf==0){ m="tf"; return false; }
  long cid=ChartOpen(sym, tf);
  if(cid==0){ m="ChartOpen fail"; return false; }
  m="opened"; return true;
}

bool H_ApplyTpl(string &p[], string &m, string &d[])
{
  if(ArraySize(p)<3){ m="params"; return false; }
  string sym=p[0]; ENUM_TIMEFRAMES tf=TfFromString(p[1]); string tpl=p[2];
  long cid=ChartOpen(sym, tf); if(cid==0){ m="ChartOpen"; return false; }
  if(!ChartApplyTemplate(cid, tpl)) { m="apply fail"; return false; }
  m="template applied"; return true;
}

bool H_SaveTpl(string &p[], string &m, string &d[])
{
  if(ArraySize(p)<3){ m="params"; return false; }
  string sym=p[0]; ENUM_TIMEFRAMES tf=TfFromString(p[1]); string tpl=p[2];
  long cid=ChartOpen(sym, tf); if(cid==0){ m="ChartOpen"; return false; }
  if(!ChartSaveTemplate(cid, tpl)) { m="save fail"; return false; }
  m="template saved"; return true;
}

bool H_CloseChart(string &p[], string &m, string &d[])
{
  if(ArraySize(p)<2){ m="params"; return false; }
  string sym=p[0]; ENUM_TIMEFRAMES tf=TfFromString(p[1]);
  long id=ChartFirst(); int closed=0;
  while(id>=0)
  {
    long next=ChartNext(id);
    if(ChartSymbol(id)==sym && ChartPeriod(id)==tf)
    {
      ChartClose(id); closed++;
    }
    id=next;
  }
  m=StringFormat("closed=%d", closed); return true;
}

bool H_CloseAll(string &p[], string &m, string &d[])
{
  long id=ChartFirst(); int closed=0;
  while(id>=0)
  {
    long next=ChartNext(id);
    ChartClose(id); closed++;
    id=next;
  }
  m=StringFormat("closed=%d", closed); return true;
}

bool H_ListCharts(string &p[], string &m, string &d[])
{
  long id=ChartFirst(); int count=0;
  while(id>=0)
  {
    string sym=(string)ChartSymbol(id);
    ENUM_TIMEFRAMES tf=(ENUM_TIMEFRAMES)ChartPeriod(id);
    string line=StringFormat("%I64d|%s|%s", id, sym, EnumToString(tf));
    int n=ChartIndicatorsTotal(id,0);
    for(int i=0;i<n;i++) line+="|"+ChartIndicatorName(id,0,i);
    ArrayResize(d,ArraySize(d)+1); d[ArraySize(d)-1]=line;
    count++;
    id=ChartNext(id);
  }
  m=StringFormat("charts=%d", count); return true;
}

bool H_AttachInd(string &p[], string &m, string &d[])
{
  if(ArraySize(p)<4){ m="params"; return false; }
  string sym=p[0]; string tfstr=p[1]; string name=p[2]; int sub=SubwindowSafe(p[3]);
  ENUM_TIMEFRAMES tf=TfFromString(tfstr); if(tf==0){ m="tf"; return false; }
  long cid=ChartOpen(sym, tf); if(cid==0){ m="ChartOpen"; return false; }
  int handle=iCustom(sym, tf, name);
  if(handle==INVALID_HANDLE){ m="iCustom fail"; return false; }
  if(!ChartIndicatorAdd(cid, sub-1, handle)){ m="ChartIndicatorAdd"; return false; }
  m="indicator attached"; return true;
}

bool H_DetachInd(string &p[], string &m, string &d[])
{
  m="not_implemented"; return false;
}

bool H_IndTotal(string &p[], string &m, string &d[])
{
  if(ArraySize(p)<3){ m="params"; return false; }
  string sym=p[0]; ENUM_TIMEFRAMES tf=TfFromString(p[1]); int sub=SubwindowSafe(p[2]);
  long cid=ChartOpen(sym, tf); if(cid==0){ m="ChartOpen"; return false; }
  int total=ChartIndicatorsTotal(cid, sub-1);
  ArrayResize(d,1); d[0]=IntegerToString(total);
  m="ok"; return true;
}

bool H_IndName(string &p[], string &m, string &d[])
{
  if(ArraySize(p)<4){ m="params"; return false; }
  string sym=p[0]; ENUM_TIMEFRAMES tf=TfFromString(p[1]); int sub=SubwindowSafe(p[2]); int idx=(int)StringToInteger(p[3]);
  long cid=ChartOpen(sym, tf); if(cid==0){ m="ChartOpen"; return false; }
  string nm=ChartIndicatorName(cid, sub-1, idx);
  ArrayResize(d,1); d[0]=nm; m="ok"; return true;
}

bool H_IndHandle(string &p[], string &m, string &d[])
{
  if(ArraySize(p)<4){ m="params"; return false; }
  string sym=p[0]; ENUM_TIMEFRAMES tf=TfFromString(p[1]); int sub=SubwindowSafe(p[2]); string name=p[3];
  long cid=ChartOpen(sym, tf); if(cid==0){ m="ChartOpen"; return false; }
  long h=ChartIndicatorGet(cid, sub-1, name);
  ArrayResize(d,1); d[0]=IntegerToString((long)h);
  m=(h!=INVALID_HANDLE)?"ok":"not_found";
  return true;
}

// EA via template apenas
bool H_AttachEA(string &p[], string &m, string &d[])
{
  if(ArraySize(p)<3){ m="params"; return false; }
  string sym=p[0]; ENUM_TIMEFRAMES tf=TfFromString(p[1]); string tpl=p[2];
  long cid=ChartOpen(sym, tf); if(cid==0){ m="ChartOpen"; return false; }
  if(!ChartApplyTemplate(cid, tpl)) { m="tpl fail"; return false; }
  m="ea via template applied"; return true;
}

// -------------------------------------------------------------------
bool Dispatch(string type, string &params[], string &msg, string &data[])
{
  if(type=="PING") return H_Ping(params,msg,data);
  if(type=="GLOBAL_SET") return H_GlobalSet(params,msg,data);
  if(type=="GLOBAL_GET") return H_GlobalGet(params,msg,data);
  if(type=="GLOBAL_DEL") return H_GlobalDel(params,msg,data);
  if(type=="GLOBAL_DEL_PREFIX") return H_GlobalDelPrefix(params,msg,data);
  if(type=="GLOBAL_LIST") return H_GlobalList(params,msg,data);
  if(type=="OPEN_CHART") return H_OpenChart(params,msg,data);
  if(type=="APPLY_TPL") return H_ApplyTpl(params,msg,data);
  if(type=="SAVE_TPL") return H_SaveTpl(params,msg,data);
  if(type=="CLOSE_CHART") return H_CloseChart(params,msg,data);
  if(type=="CLOSE_ALL") return H_CloseAll(params,msg,data);
  if(type=="LIST_CHARTS") return H_ListCharts(params,msg,data);
  if(type=="ATTACH_IND_FULL") return H_AttachInd(params,msg,data);
  if(type=="DETACH_IND_FULL") return H_DetachInd(params,msg,data);
  if(type=="IND_TOTAL") return H_IndTotal(params,msg,data);
  if(type=="IND_NAME") return H_IndName(params,msg,data);
  if(type=="IND_HANDLE") return H_IndHandle(params,msg,data);
  if(type=="ATTACH_EA_FULL") return H_AttachEA(params,msg,data);
  msg="unknown"; return false;
}

// -------------------------------------------------------------------
void OnStart()
{
  int rc = PipeStart(InpPipeName);
  if(rc!=0)
  {
    Print("CommandBridgeServicePipe falhou PipeStart rc=", rc, " pipe=", InpPipeName);
    return;
  }
  EventSetTimer(InpTimerSec);
  Print("CommandBridgeServicePipe ativo. Pipe=", InpPipeName, " ver=", LISTENER_VERSION);

  while(!IsStopped())
  {
    string id,type; string params[]; string data[]; string msg=""; int pid=0;
    if(ReadCommandPipe(id,type,params,pid))
    {
      bool ok = Dispatch(type, params, msg, data);
      WriteResp(id, ok, msg, data, pid);
    }
    Sleep(20);
  }

  EventKillTimer();
  PipeStop();
}
