//+------------------------------------------------------------------+
//| CommandBridgeServiceSocket.mq5                                   |
//| Serviço: despacha comandos via SOCKET TCP (client -> PHP server) |
//| Mantém os mesmos handlers do pipe/file, mas usa SocketConnect.   |
//+------------------------------------------------------------------+
#property service
#property strict

input string InpHost      = "127.0.0.1"; // host do servidor PHP
input int    InpPort      = 9099;         // porta do servidor PHP
input int    InpTimerSec  = 1;            // timer de polling
input int    InpSockTOms  = 200;          // timeout ms para read

#include <Trade\Trade.mqh>
#include <PipeBridge.mqh> // só para reusar utilitários de params (não usa pipe)

string LISTENER_VERSION = "svc-socket-1.0.0";

int g_sock = INVALID_HANDLE;
uchar g_buf[65536];

// ------------------------------------- utils -------------------------------
string Join(string &arr[], const string sep)
{
  string out=""; int n=ArraySize(arr);
  for(int i=0;i<n;i++){ if(i>0) out+=sep; out+=arr[i]; }
  return out;
}

bool EnsureSymbol(const string sym){ if(SymbolSelect(sym,true)) return true; Print("[bridge] SymbolSelect fail ",sym); return false; }

ENUM_TIMEFRAMES TfFromString(const string tf)
{
  string u=StringUpper(tf);
  if(u=="M1") return PERIOD_M1; if(u=="M5") return PERIOD_M5; if(u=="M15") return PERIOD_M15; if(u=="M30") return PERIOD_M30;
  if(u=="H1") return PERIOD_H1; if(u=="H4") return PERIOD_H4; if(u=="D1") return PERIOD_D1; if(u=="W1") return PERIOD_W1; if(u=="MN1") return PERIOD_MN1;
  return (ENUM_TIMEFRAMES)0;
}

int SubwindowSafe(const string val){ if(val=="") return 1; int v=(int)StrToInteger(val); return (v<=0)?1:v; }

int ParseParams(const string pstr, string &keys[], string &vals[])
{
  if(pstr=="") return 0;
  string pairs[]; int n=StringSplit(pstr, ';', pairs);
  int count=0; ArrayResize(keys, n); ArrayResize(vals, n);
  for(int i=0;i<n;i++)
  {
    string kv[]; int c=StringSplit(pairs[i], '=', kv);
    if(c==2){ keys[count]=kv[0]; vals[count]=kv[1]; count++; }
  }
  ArrayResize(keys, count); ArrayResize(vals, count);
  return count;
}

int BuildParams(const string pstr, MqlParam &outParams[])
{
  string ks[], vs[]; int cnt=ParseParams(pstr, ks, vs);
  ArrayResize(outParams, cnt);
  for(int i=0;i<cnt;i++)
  {
    double num = StrToDouble(vs[i]);
    if((StringLen(vs[i])>0) && (vs[i]=="0" || num!=0.0))
    { outParams[i].type = TYPE_DOUBLE; outParams[i].double_value = num; }
    else { outParams[i].type = TYPE_STRING; outParams[i].string_value = vs[i]; }
  }
  return cnt;
}

// -------------------------- IO socket --------------------------------------
bool EnsureSocket()
{
  if(g_sock!=INVALID_HANDLE && SocketIsConnected(g_sock)) return true;
  if(g_sock!=INVALID_HANDLE) SocketClose(g_sock);
  g_sock = SocketCreate();
  if(g_sock==INVALID_HANDLE) return false;
  if(!SocketConnect(g_sock, InpHost, InpPort, InpSockTOms))
  {
    SocketClose(g_sock); g_sock=INVALID_HANDLE; return false;
  }
  return true;
}

bool ReadCommandSocket(string &id, string &type, string &params[])
{
  if(!EnsureSocket()) return false;
  int got = SocketRead(g_sock, g_buf, ArraySize(g_buf), InpSockTOms);
  if(got<=0) return false;
  string line = CharArrayToString(g_buf, 0, got, CP_UTF8);
  StringReplace(line, "\r", ""); StringReplace(line, "\n", "");
  string parts[]; int n=StringSplit(line, '|', parts);
  if(n<2) return false;
  id   = parts[0];
  type = parts[1];
  ArrayResize(params, MathMax(0,n-2));
  for(int i=2;i<n;i++) params[i-2]=parts[i];
  return true;
}

bool WriteRespSocket(const string id, const bool ok, const string message, string data[])
{
  if(!EnsureSocket()) return false;
  string text = (ok?"OK":"ERROR") + "\n" + message + "\n";
  for(int i=0;i<ArraySize(data);i++) text += data[i] + "\n";
  uchar bytes[]; StringToCharArray(text, bytes, 0, StringLen(text), CP_UTF8);
  int sent = SocketSend(g_sock, bytes, ArraySize(bytes), InpSockTOms);
  return sent>0;
}

// --------------------------- Handlers (infra) -----------------------------
bool H_Ping(string p[], string &m, string &d[]){ m="pong "+LISTENER_VERSION; return true; }

bool H_GlobalSet(string p[], string &m, string &d[])
{ if(ArraySize(p)<2){ m="params"; return false; } string name=p[0]; double val=StrToDouble(p[1]); bool ok = GlobalVariableSet(name,val)>0; m=ok?"set":"fail"; return ok; }

bool H_GlobalGet(string p[], string &m, string &d[])
{ if(ArraySize(p)<1){ m="params"; return false; } string name=p[0]; if(!GlobalVariableCheck(name)){ m="not_found"; return false; } double v=GlobalVariableGet(name); ArrayResize(d,1); d[0]=DoubleToString(v,8); m="ok"; return true; }

bool H_GlobalDel(string p[], string &m, string &d[])
{ if(ArraySize(p)<1){ m="params"; return false; } m = GlobalVariableDel(p[0])?"deleted":"not_found"; return (m=="deleted"); }

bool H_GlobalDelPrefix(string p[], string &m, string &d[])
{ if(ArraySize(p)<1){ m="params"; return false; } string prefix=p[0]; int total=GlobalVariablesTotal(); int removed=0; for(int i=0;i<total;i++){ string nm=GlobalVariableName(i); if(StringFind(nm,prefix)==0){ if(GlobalVariableDel(nm)) removed++; }} m=StringFormat("removed=%d", removed); return true; }

bool H_GlobalList(string p[], string &m, string &d[])
{ string prefix=(ArraySize(p)>0)?p[0]:""; int limit=(ArraySize(p)>1)?(int)StrToInteger(p[1]):0; int total=GlobalVariablesTotal(); int count=0; for(int i=0;i<total;i++){ string nm=GlobalVariableName(i); if(prefix!="" && StringFind(nm,prefix)!=0) continue; double v=GlobalVariableGet(nm); ArrayResize(d,ArraySize(d)+1); d[ArraySize(d)-1]=nm+"="+DoubleToString(v,8); count++; if(limit>0 && count>=limit) break; } m=StringFormat("vars=%d", count); return true; }

// Charts/Indicadores/EA/Objetos/Trade handlers são idênticos ao CommandBridgeServicePipe original.
// Para brevidade, mantemos apenas alguns essenciais; adicione aqui se precisar mais.

bool H_OpenChart(string p[], string &m, string &d[])
{
  if(ArraySize(p)<2){ m="params"; return false; }
  string sym=p[0]; ENUM_TIMEFRAMES tf=TfFromString(p[1]); if(tf==0){ m="tf"; return false; }
  long cid=ChartOpen(sym, tf); if(cid==0){ m="ChartOpen fail"; return false; }
  m="opened"; return true;
}

bool H_ApplyTpl(string p[], string &m, string &d[])
{
  if(ArraySize(p)<3){ m="params"; return false; }
  string sym=p[0]; ENUM_TIMEFRAMES tf=TfFromString(p[1]); string tpl=p[2];
  long cid=ChartOpen(sym, tf); if(cid==0){ m="ChartOpen"; return false; }
  if(!ChartApplyTemplate(cid, tpl)) { m="apply fail"; return false; }
  m="template applied"; return true;
}

bool H_SaveTpl(string p[], string &m, string &d[])
{
  if(ArraySize(p)<3){ m="params"; return false; }
  string sym=p[0]; ENUM_TIMEFRAMES tf=TfFromString(p[1]); string tpl=p[2];
  long cid=ChartOpen(sym, tf); if(cid==0){ m="ChartOpen"; return false; }
  if(!ChartSaveTemplate(cid, tpl)) { m="save fail"; return false; }
  m="template saved"; return true;
}

bool H_CloseChart(string p[], string &m, string &d[])
{
  if(ArraySize(p)<2){ m="params"; return false; }
  string sym=p[0]; ENUM_TIMEFRAMES tf=TfFromString(p[1]);
  long cid=ChartOpen(sym, tf); if(cid==0){ m="ChartOpen"; return false; }
  bool ok=ChartClose(cid); m=ok?"closed":"fail"; return ok;
}

bool H_CloseAll(string p[], string &m, string &d[])
{
  long id=ChartFirst(); int closed=0; while(id>=0){ long next=ChartNext(id); ChartClose(id); closed++; id=next; }
  m=StringFormat("closed=%d", closed); return true;
}

// Snapshot minimal
bool H_Screenshot(string p[], string &m, string &d[])
{
  if(ArraySize(p)<3){ m="params"; return false; }
  string sym=p[0]; ENUM_TIMEFRAMES tf=TfFromString(p[1]); string file=p[2];
  int width = (ArraySize(p)>3)?(int)StrToInteger(p[3]):0;
  int height= (ArraySize(p)>4)?(int)StrToInteger(p[4]):0;
  long cid=ChartOpen(sym, tf); if(cid==0){ m="ChartOpen"; return false; }
  if(!ChartScreenShot(cid, file, width, height)) { m="fail"; return false; }
  m="shot"; return true;
}

// --- EW_ANALYZE via socket Python ---
bool H_EwAnalyze(string p[], string &m, string &d[])
{
  string sym   = (ArraySize(p)>0 && p[0]!="") ? p[0] : _Symbol;
  ENUM_TIMEFRAMES tf = (ArraySize(p)>1 && p[1]!="") ? TfFromString(p[1]) : _Period;
  int bars      = (ArraySize(p)>2 && p[2]!="") ? (int)StrToInteger(p[2]) : 300;
  string mode   = (ArraySize(p)>3 && p[3]!="") ? p[3] : "impulse";
  int max_skip  = (ArraySize(p)>4 && p[4]!="") ? (int)StrToInteger(p[4]) : 8;
  int max_res   = (ArraySize(p)>5 && p[5]!="") ? (int)StrToInteger(p[5]) : 3;
  if(tf==0) tf=_Period; if(bars<10) bars=10; if(!EnsureSymbol(sym)){ m="SymbolSelect"; return false; }
  MqlRates rates[]; int got=CopyRates(sym, tf, 0, bars, rates); if(got<=0){ m="CopyRates=0"; return false; }
  ArraySetAsSeries(rates,true);
  string json="{\"cmd\":\"ew_analyze\",\"bars\":[";
  for(int i=got-1;i>=0;i--){ if(i!=got-1) json+=","; json+=StringFormat("{\"time\":%d,\"open\":%.6f,\"high\":%.6f,\"low\":%.6f,\"close\":%.6f}",(int)rates[i].time,rates[i].open,rates[i].high,rates[i].low,rates[i].close);} 
  json += "],\"params\":"+StringFormat("{\"mode\":\"%s\",\"max_skip\":%d,\"max_results\":%d}", mode, max_skip, max_res)+"}";
  string resp; if(!SendLine(InpHost, InpPort, json, resp, 2000)){ m="socket_fail"; return false; }
  ArrayResize(d,1); d[0]=resp; m="ok"; return true;
}

// Dispatcher
bool Dispatch(const string type, string params[], string &msg, string &data[])
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
  if(type=="SCREENSHOT") return H_Screenshot(params,msg,data);
  if(type=="EW_ANALYZE") return H_EwAnalyze(params,msg,data);
  msg="unknown"; return false;
}

// ------------------------------------------------------------------
int OnInit()
{
  EventSetTimer(InpTimerSec);
  Print("CommandBridgeServiceSocket conectado a ", InpHost, ":", InpPort, " ver=", LISTENER_VERSION);
  return(INIT_SUCCEEDED);
}

void OnDeinit(const int reason)
{
  EventKillTimer();
  if(g_sock!=INVALID_HANDLE) SocketClose(g_sock);
}

void OnTimer()
{
  string id,type; string params[]; string data[]; string msg="";
  if(!ReadCommandSocket(id,type,params)) return;
  bool ok = Dispatch(type, params, msg, data);
  WriteRespSocket(id, ok, msg, data);
}

// End of file
