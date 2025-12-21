#property copyright "MTCLI"
#property link      ""
#property version   "1.1"
#property strict

// ListenerTelnet (versão socket): processa comandos via TCP (texto ou JSON).
// Remove o fluxo cmd_*.txt/resp_*.txt e usa SocketCreate/SocketConnect.
// Comando especial: EW_ANALYZE envia barras ao servidor Python (porta 9090) e devolve JSON.

#include <Trade\Trade.mqh>
CTrade trade;

input string InpHost = "127.0.0.1";
input int    InpPort = 9090;
input int    InpTimerSec = 1;
input int    InpBars = 300;
input string InpMode = "impulse"; // impulse|correction|both
input int    InpMaxSkip = 8;
input int    InpMaxResults = 3;

string LISTENER_VERSION = "1.1-socket";

// ------------------------------------------------------------------
// Utilidades
int BuildParams(const string pstr, MqlParam &outParams[])
{
  string pairs[]; int n=StringSplit(pstr, ';', pairs);
  ArrayResize(outParams, n);
  int count=0;
  for(int i=0;i<n;i++)
  {
    string kv[]; int c=StringSplit(pairs[i], '=', kv);
    if(c!=2) continue;
    double num = StrToDouble(kv[1]);
    outParams[count].type = TYPE_STRING;
    outParams[count].string_value = kv[1];
    if(StringLen(kv[1])>0 && (kv[1]=="0" || num!=0.0))
    {
      outParams[count].type = TYPE_DOUBLE;
      outParams[count].double_value = num;
    }
    count++;
  }
  ArrayResize(outParams, count);
  return count;
}

ENUM_TIMEFRAMES TfFromString(const string tf)
{
  string u=StringUpper(tf);
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

bool EnsureSymbol(const string sym)
{
  if(SymbolSelect(sym,true)) return true;
  Print("[listener] SymbolSelect failed for ", sym);
  return false;
}

bool SendLine(const string host, const int port, const string line, string &resp, int timeout_ms=2000)
{
  int sock = SocketCreate();
  if(sock==INVALID_HANDLE) return false;
  if(!SocketConnect(sock, host, port, timeout_ms))
  {
    SocketClose(sock); return false;
  }
  uchar buf[]; StringToCharArray(line+"\n", buf, 0, WHOLE_ARRAY, CP_UTF8);
  if(SocketSend(sock, buf, ArraySize(buf), timeout_ms)<=0)
  { SocketClose(sock); return false; }

  uchar rbuf[8192]; int total=0; ulong start=GetMicrosecondCount();
  while(GetMicrosecondCount()-start < (ulong)timeout_ms*1000)
  {
    int got = SocketRead(sock, rbuf+total, 8192-total, 200);
    if(got>0)
    {
      total += got;
      if(rbuf[total-1]==10) break; // LF
    }
  }
  SocketClose(sock);
  if(total<=0) return false;
  resp = CharArrayToString(rbuf, 0, total, CP_UTF8);
  StringReplace(resp, "\r", "");
  StringReplace(resp, "\n", "");
  return true;
}

// ------------------------------------------------------------------
// Handlers principais
bool H_Ping(string p[], string &m, string &d[]){ m="pong "+LISTENER_VERSION; return true; }

bool H_EwAnalyze(string p[], string &m, string &d[])
{
  string sym   = (ArraySize(p)>0 && p[0]!="") ? p[0] : _Symbol;
  ENUM_TIMEFRAMES tf = (ArraySize(p)>1 && p[1]!="") ? TfFromString(p[1]) : _Period;
  int bars      = (ArraySize(p)>2 && p[2]!="") ? (int)StrToInteger(p[2]) : InpBars;
  string mode   = (ArraySize(p)>3 && p[3]!="") ? p[3] : InpMode;
  int max_skip  = (ArraySize(p)>4 && p[4]!="") ? (int)StrToInteger(p[4]) : InpMaxSkip;
  int max_res   = (ArraySize(p)>5 && p[5]!="") ? (int)StrToInteger(p[5]) : InpMaxResults;

  if(tf==0) tf=_Period;
  if(bars<10) bars=10;
  if(!EnsureSymbol(sym)){ m="SymbolSelect"; return false; }

  MqlRates rates[]; int got=CopyRates(sym, tf, 0, bars, rates);
  if(got<=0){ m="CopyRates=0"; return false; }
  ArraySetAsSeries(rates,true);

  string json = "{\"cmd\":\"ew_analyze\",\"bars\":[";
  for(int i=got-1;i>=0;i--)
  {
    if(i!=got-1) json+=",";
    json += StringFormat("{\"time\":%d,\"open\":%.6f,\"high\":%.6f,\"low\":%.6f,\"close\":%.6f}",
                         (int)rates[i].time, rates[i].open, rates[i].high, rates[i].low, rates[i].close);
  }
  json += "],\"params\":";
  json += StringFormat("{\"mode\":\"%s\",\"max_skip\":%d,\"max_results\":%d}", mode, max_skip, max_res);
  json += "}";

  string resp;
  if(!SendLine(InpHost, InpPort, json, resp, 2000))
  { m="socket_fail"; return false; }
  ArrayResize(d,1); d[0]=resp; m="ok"; Print("EW_ANALYZE resp=", resp);
  return true;
}

// Dispatcher simples
bool Dispatch(const string type, string params[], string &msg, string &data[])
{
  if(type=="PING") return H_Ping(params,msg,data);
  if(type=="EW_ANALYZE") return H_EwAnalyze(params,msg,data);
  msg="unknown"; return false;
}

// ------------------------------------------------------------------
int OnInit()
{
  EventSetTimer(InpTimerSec);
  Print("ListenerTelnet socket iniciado host=", InpHost, " port=", InpPort, " ver=", LISTENER_VERSION);
  return(INIT_SUCCEEDED);
}
void OnDeinit(const int reason){ EventKillTimer(); }

// Para compatibilidade, ainda processa um comando por tick via ChartEvent (opcional)
void OnTimer() { /* o comando virá de fora via socket externo, se necessário */ }

// End of file
