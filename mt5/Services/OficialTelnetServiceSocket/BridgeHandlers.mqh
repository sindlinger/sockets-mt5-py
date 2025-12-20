// BridgeHandlers.mqh
// Utilidades + handlers + Dispatch, sem OnStart (para ser usado por pipe e socket)
#ifndef __BRIDGE_HANDLERS_MQH__
#define __BRIDGE_HANDLERS_MQH__

string LISTENER_VERSION = "bridge-1.0.4-true-resp";

#include <Trade\\Trade.mqh>
#include <Trade\\PositionInfo.mqh>
#include <Files\\File.mqh>
#include "ScriptActions.mqh"

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

// Armazena ultimo attach para inputs simples (compat com listener)
string g_lastIndName = "";
string g_lastIndParams = ""; // k=v;k2=v2
string g_lastIndSymbol = "";
string g_lastIndTf = "";
int    g_lastIndSub = 1;

string g_lastEAName = "";
string g_lastEAParams = "";
string g_lastEASymbol = "";
string g_lastEATf = "";
string g_lastEATpl = "";

// log tracking
string g_log_date = "";
long   g_log_pos  = 0;

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

string TfToString(const ENUM_TIMEFRAMES tf)
{
  if(tf==PERIOD_M1) return "M1";
  if(tf==PERIOD_M5) return "M5";
  if(tf==PERIOD_M15) return "M15";
  if(tf==PERIOD_M30) return "M30";
  if(tf==PERIOD_H1) return "H1";
  if(tf==PERIOD_H4) return "H4";
  if(tf==PERIOD_D1) return "D1";
  if(tf==PERIOD_W1) return "W1";
  if(tf==PERIOD_MN1) return "MN1";
  return "";
}

int SubwindowSafe(string &val)
{
  if(val=="") return 1;
  int v=(int)StringToInteger(val);
  return (v<=0)?1:v;
}

int ParseParams(string &pstr, string &keys[], string &vals[])
{
  if(pstr=="") { ArrayResize(keys,0); ArrayResize(vals,0); return 0; }
  string pairs[]; int n=StringSplit(pstr, ';', pairs);
  int count=0;
  ArrayResize(keys, n); ArrayResize(vals, n);
  for(int i=0;i<n;i++)
  {
    if(pairs[i]=="") continue;
    string kv[]; int c=StringSplit(pairs[i], '=', kv);
    if(c==2)
    {
      keys[count]=kv[0]; vals[count]=kv[1];
      count++;
    }
    else
    {
      // permite lista simples (sem chave)
      keys[count]=""; vals[count]=pairs[i];
      count++;
    }
  }
  ArrayResize(keys, count); ArrayResize(vals, count);
  return count;
}

int BuildParams(string &pstr, MqlParam &outParams[])
{
  string ks[], vs[]; int cnt=ParseParams(pstr, ks, vs);
  ArrayResize(outParams, cnt);
  for(int i=0;i<cnt;i++)
  {
    double num = StringToDouble(vs[i]);
    if((StringLen(vs[i])>0 && num!=0) || vs[i]=="0")
    {
      outParams[i].type = TYPE_DOUBLE;
      outParams[i].double_value = num;
    }
    else
    {
      outParams[i].type = TYPE_STRING;
      outParams[i].string_value = vs[i];
    }
  }
  return cnt;
}

bool EnsureSymbol(const string sym)
{
  if(SymbolSelect(sym, true)) return true;
  Print("[bridge] SymbolSelect failed for ", sym);
  return false;
}

bool ResolveSymbolTf(string &sym, string &tfstr, ENUM_TIMEFRAMES &tf)
{
  if(sym=="") sym = ChartSymbol(0);
  tf = TfFromString(tfstr);
  if(tf==0) tf = (ENUM_TIMEFRAMES)ChartPeriod(0);
  if(sym=="" || tf==0) return false;
  if(!EnsureSymbol(sym))
  {
    string cur = ChartSymbol(0);
    if(cur!="" && cur!=sym)
    {
      sym = cur;
      if(!EnsureSymbol(sym)) return false;
    }
    else return false;
  }
  tfstr = TfToString(tf);
  return (tf!=0 && sym!="");
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

string FilesDir()
{
  static string dir="";
  if(dir=="")
    dir = TerminalInfoString(TERMINAL_DATA_PATH) + "\\MQL5\\Files";
  return dir;
}

string SnapshotFolderRel()
{
  return "MQL5\\Profiles\\Templates\\snapshots";
}

bool EnsureSnapshotFolder()
{
  string folder = SnapshotFolderRel();
  if(FolderCreate(folder)) return true;
  if(FileIsExist(folder)) return true;
  return false;
}

string TemplatesRel()
{
  return "MQL5\\Profiles\\Templates";
}

bool ReadFileText(const string path, string &out, bool &is_unicode)
{
  out=""; is_unicode=false;
  int h=FileOpen(path, FILE_READ|FILE_TXT|FILE_UNICODE);
  if(h!=INVALID_HANDLE)
  {
    while(!FileIsEnding(h))
    {
      string line=FileReadString(h);
      out += line;
      if(!FileIsEnding(h)) out += "\n";
    }
    FileClose(h);
    is_unicode=true;
    if(out!="") return true;
  }
  h=FileOpen(path, FILE_READ|FILE_TXT|FILE_ANSI);
  if(h==INVALID_HANDLE) return false;
  while(!FileIsEnding(h))
  {
    string line=FileReadString(h);
    out += line;
    if(!FileIsEnding(h)) out += "\n";
  }
  FileClose(h);
  is_unicode=false;
  return out!="";
}

bool WriteFileText(const string path, const string txt, const bool unicode)
{
  int flags = FILE_WRITE|FILE_TXT|(unicode?FILE_UNICODE:FILE_ANSI);
  int h=FileOpen(path, flags);
  if(h==INVALID_HANDLE) return false;
  FileWriteString(h, txt);
  FileClose(h);
  return true;
}

string StripExpertBlock(const string tpl)
{
  int s=StringFind(tpl, "<expert>");
  if(s<0) return tpl;
  int e=StringFind(tpl, "</expert>", s);
  if(e<0) return tpl;
  e += StringLen("</expert>");
  return StringSubstr(tpl, 0, s) + StringSubstr(tpl, e);
}

string NormalizeExpertPath(string expert)
{
  string e=expert;
  StringReplace(e, "/", "\\");
  if(StringFind(e, "Experts\\")==0) e=StringSubstr(e, StringLen("Experts\\"));
  if(StringLen(e)>4)
  {
    string tail=StringSubstr(e, StringLen(e)-4);
    if(tail==".ex5" || tail==".mq5") e=StringSubstr(e,0,StringLen(e)-4);
  }
  return e;
}

string ResolveExpertPath(const string expert)
{
  string e=NormalizeExpertPath(expert);
  string base="MQL5\\Experts\\";
  if(FileIsExist(base+e+".ex5") || FileIsExist(base+e+".mq5")) return e;
  string alt="Examples\\"+e+"\\"+e;
  if(FileIsExist(base+alt+".ex5") || FileIsExist(base+alt+".mq5")) return alt;
  return e;
}

string BuildExpertBlock(const string name, const string pstr)
{
  string block="<expert>\n";
  block+="name="+name+"\n";
  block+="flags=343\n";
  block+="window_num=0\n";
  block+="<inputs>\n";
  if(pstr!="")
  {
    string tmp=pstr;
    string keys[], vals[]; int cnt=ParseParams(tmp, keys, vals);
    for(int i=0;i<cnt;i++)
    {
      if(keys[i]=="") continue;
      block+=keys[i]+"="+vals[i]+"\n";
    }
  }
  block+="</inputs>\n";
  block+="</expert>\n";
  return block;
}

bool TemplateHasExpert(const string txt, const string expected)
{
  string lower=txt; StringToLower(lower);
  string exp=expected; StringToLower(exp);
  int s=StringFind(lower, "<expert>");
  if(s<0) return false;
  int e=StringFind(lower, "</expert>", s);
  if(e<0) return false;
  string block=StringSubstr(lower, s, e-s);
  if(StringFind(block, "name="+exp)>=0) return true;
  return false;
}

bool ChartHasExpert(const long cid, const string expected)
{
  string tmpName="__cmdmt_check.tpl";
  if(!ChartSaveTemplate(cid, tmpName)) return false;
  string path=TemplatesRel()+"\\"+tmpName;
  string txt=""; bool is_unicode=false;
  if(!ReadFileText(path, txt, is_unicode)) { FileDelete(path); return false; }
  bool ok=TemplateHasExpert(txt, expected);
  FileDelete(path);
  return ok;
}

string CurrentLogDate()
{
  MqlDateTime dt; TimeToStruct(TimeCurrent(), dt);
  return StringFormat("%04d%02d%02d", dt.year, dt.mon, dt.day);
}

string LogPath()
{
  return "MQL5\\Logs\\"+CurrentLogDate()+".log";
}

void LogCaptureBegin()
{
  string curDate=CurrentLogDate();
  g_log_date=curDate;
  string path=LogPath();
  int h=FileOpen(path, FILE_READ|FILE_TXT|FILE_UNICODE);
  if(h==INVALID_HANDLE) h=FileOpen(path, FILE_READ|FILE_TXT|FILE_ANSI);
  if(h==INVALID_HANDLE) { g_log_pos=0; return; }
  g_log_pos=(long)FileSize(h);
  FileClose(h);
}

bool ReadLogLines(string &out[])
{
  ArrayResize(out,0);
  string curDate=CurrentLogDate();
  if(g_log_date!=curDate) { g_log_date=curDate; g_log_pos=0; }
  string path=LogPath();
  int h=FileOpen(path, FILE_READ|FILE_TXT|FILE_UNICODE);
  bool unicode=true;
  if(h==INVALID_HANDLE)
  {
    h=FileOpen(path, FILE_READ|FILE_TXT|FILE_ANSI);
    unicode=false;
  }
  if(h==INVALID_HANDLE) return false;
  long size=(long)FileSize(h);
  if(g_log_pos<0 || g_log_pos>size) g_log_pos=0;
  FileSeek(h, (int)g_log_pos, SEEK_SET);
  while(!FileIsEnding(h))
  {
    string line=FileReadString(h);
    if(line!="")
    {
      int n=ArraySize(out);
      ArrayResize(out, n+1); out[n]=line;
    }
  }
  g_log_pos=(long)FileTell(h);
  FileClose(h);
  return true;
}

string FindLogError(const string filter)
{
  string lines[];
  if(!ReadLogLines(lines)) return "";
  string f=filter; StringToLower(f);
  for(int i=ArraySize(lines)-1;i>=0;i--)
  {
    string l=lines[i]; StringToLower(l);
    if(f!="" && StringFind(l, f)<0) continue;
    if(StringFind(l, "cannot load")>=0 || StringFind(l, "init failed")>=0 || StringFind(l, "failed")>=0 || StringFind(l, "error")>=0)
      return lines[i];
  }
  return "";
}

ENUM_OBJECT ObjectTypeFromString(string t)
{
  StringToUpper(t);
  if(t=="OBJ_TREND") return OBJ_TREND;
  if(t=="OBJ_HLINE") return OBJ_HLINE;
  if(t=="OBJ_VLINE") return OBJ_VLINE;
  if(t=="OBJ_RECTANGLE") return OBJ_RECTANGLE;
  if(t=="OBJ_TEXT") return OBJ_TEXT;
  if(t=="OBJ_LABEL") return OBJ_LABEL;
  if(t=="OBJ_ARROW") return OBJ_ARROW;
  if(t=="OBJ_TRIANGLE") return OBJ_TRIANGLE;
  if(t=="OBJ_ELLIPSE") return OBJ_ELLIPSE;
  if(t=="OBJ_CHANNEL") return OBJ_CHANNEL;
  return OBJ_TREND;
}

// ---------------- Handlers ----------------------
bool H_Ping(string &p[], string &m, string &d[]) { m="pong "+LISTENER_VERSION; return true; }
bool H_Debug(string &p[], string &m, string &d[]) { if(ArraySize(p)>0) Print(p[0]); m="printed"; return true; }

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
  string sym=p[0]; string tfstr=p[1]; ENUM_TIMEFRAMES tf;
  if(!ResolveSymbolTf(sym, tfstr, tf)) { m="symbol"; return false; }
  long cid=ChartOpen(sym, tf);
  if(cid==0){ m="ChartOpen fail"; return false; }
  ChartSetInteger(cid, CHART_BRING_TO_TOP, 0, true);
  ArrayResize(d,1); d[0]=IntegerToString((long)cid);
  m="opened"; return true;
}

bool H_ApplyTpl(string &p[], string &m, string &d[])
{
  if(ArraySize(p)<3){ m="params"; return false; }
  string sym=p[0]; string tfstr=p[1]; ENUM_TIMEFRAMES tf; string tpl=p[2];
  if(!ResolveSymbolTf(sym, tfstr, tf)) { m="symbol"; return false; }
  long cid=ChartOpen(sym, tf); if(cid==0){ m="ChartOpen"; return false; }
  if(!ChartApplyTemplate(cid, tpl)) { m="apply fail"; return false; }
  Sleep(200);
  m="template applied"; return true;
}

bool H_SaveTpl(string &p[], string &m, string &d[])
{
  if(ArraySize(p)<3){ m="params"; return false; }
  string sym=p[0]; string tfstr=p[1]; ENUM_TIMEFRAMES tf; string tpl=p[2];
  if(!ResolveSymbolTf(sym, tfstr, tf)) { m="symbol"; return false; }
  long cid=ChartOpen(sym, tf); if(cid==0){ m="ChartOpen"; return false; }
  if(!ChartSaveTemplate(cid, tpl)) { m="save fail"; return false; }
  m="template saved"; return true;
}

bool H_CloseChart(string &p[], string &m, string &d[])
{
  if(ArraySize(p)<2){ m="params"; return false; }
  string sym=p[0]; string tfstr=p[1]; ENUM_TIMEFRAMES tf;
  if(!ResolveSymbolTf(sym, tfstr, tf)) { m="symbol"; return false; }
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
  string pstr="";
  if(ArraySize(p)>4)
  {
    if(ArraySize(p)==5) pstr=p[4];
    else
    {
      string extra[]; ArrayResize(extra, ArraySize(p)-4);
      for(int i=4;i<ArraySize(p);i++) extra[i-4]=p[i];
      pstr=Join(extra, ";");
    }
  }
  ENUM_TIMEFRAMES tf; if(!ResolveSymbolTf(sym, tfstr, tf)) { m="symbol"; return false; }
  long cid=ChartOpen(sym, tf); if(cid==0){ m="ChartOpen"; return false; }
  int handle=INVALID_HANDLE;
  if(pstr=="")
  {
    ResetLastError();
    handle=iCustom(sym, tf, name);
    if(handle==INVALID_HANDLE && StringFind(name,"\\")<0 && StringFind(name,"/")<0)
    {
      ResetLastError();
      handle=iCustom(sym, tf, "Examples\\"+name);
    }
  }
  else
  {
    MqlParam inputs[]; BuildParams(pstr, inputs);
    int n=ArraySize(inputs);
    MqlParam all[];
    ArrayResize(all, n+1);
    all[0].type=TYPE_STRING; all[0].string_value=name;
    for(int i=0;i<n;i++) all[i+1]=inputs[i];
    ResetLastError();
    handle=IndicatorCreate(sym, tf, IND_CUSTOM, ArraySize(all), all);
    if(handle==INVALID_HANDLE && StringFind(name,"\\")<0 && StringFind(name,"/")<0)
    {
      all[0].string_value="Examples\\"+name;
      ResetLastError();
      handle=IndicatorCreate(sym, tf, IND_CUSTOM, ArraySize(all), all);
    }
  }
  if(handle==INVALID_HANDLE){ m="iCustom fail err="+IntegerToString(GetLastError()); return false; }
  ResetLastError();
  if(!ChartIndicatorAdd(cid, sub-1, handle)){ m="ChartIndicatorAdd err="+IntegerToString(GetLastError()); return false; }
  g_lastIndName=name; g_lastIndParams=pstr; g_lastIndSymbol=sym; g_lastIndTf=tfstr; g_lastIndSub=sub;
  m="indicator attached"; return true;
}

bool H_DetachInd(string &p[], string &m, string &d[])
{
  if(ArraySize(p)<4){ m="params"; return false; }
  string sym=p[0]; string tfstr=p[1]; string name=p[2]; int sub=SubwindowSafe(p[3]);
  ENUM_TIMEFRAMES tf; if(!ResolveSymbolTf(sym, tfstr, tf)) { m="symbol"; return false; }
  long cid=ChartOpen(sym, tf); if(cid==0){ m="ChartOpen"; return false; }
  int total=ChartIndicatorsTotal(cid, sub-1);
  int deleted=0;
  for(int i=total-1;i>=0;i--)
  {
    string iname=ChartIndicatorName(cid, sub-1, i);
    if(StringCompare(iname, name)==0 || StringFind(iname, name)==0)
    {
      if(ChartIndicatorDelete(cid, sub-1, iname)) deleted++;
    }
  }
  m="detached="+IntegerToString((long)deleted);
  return (deleted>0);
}

bool H_IndTotal(string &p[], string &m, string &d[])
{
  if(ArraySize(p)<3){ m="params"; return false; }
  string sym=p[0]; string tfstr=p[1]; ENUM_TIMEFRAMES tf; int sub=SubwindowSafe(p[2]);
  if(!ResolveSymbolTf(sym, tfstr, tf)) { m="symbol"; return false; }
  long cid=ChartOpen(sym, tf); if(cid==0){ m="ChartOpen"; return false; }
  int total=ChartIndicatorsTotal(cid, sub-1);
  ArrayResize(d,1); d[0]=IntegerToString(total);
  m="ok"; return true;
}

bool H_IndName(string &p[], string &m, string &d[])
{
  if(ArraySize(p)<4){ m="params"; return false; }
  string sym=p[0]; string tfstr=p[1]; ENUM_TIMEFRAMES tf; int sub=SubwindowSafe(p[2]); int idx=(int)StringToInteger(p[3]);
  if(!ResolveSymbolTf(sym, tfstr, tf)) { m="symbol"; return false; }
  long cid=ChartOpen(sym, tf); if(cid==0){ m="ChartOpen"; return false; }
  string nm=ChartIndicatorName(cid, sub-1, idx);
  ArrayResize(d,1); d[0]=nm; m="ok"; return true;
}

bool H_IndHandle(string &p[], string &m, string &d[])
{
  if(ArraySize(p)<4){ m="params"; return false; }
  string sym=p[0]; string tfstr=p[1]; ENUM_TIMEFRAMES tf; int sub=SubwindowSafe(p[2]); string name=p[3];
  if(!ResolveSymbolTf(sym, tfstr, tf)) { m="symbol"; return false; }
  long cid=ChartOpen(sym, tf); if(cid==0){ m="ChartOpen"; return false; }
  long h=ChartIndicatorGet(cid, sub-1, name);
  ArrayResize(d,1); d[0]=IntegerToString((long)h);
  m=(h!=INVALID_HANDLE)?"ok":"not_found";
  return true;
}

bool H_AttachEA(string &p[], string &m, string &d[])
{
  if(ArraySize(p)<3){ m="params"; return false; }
  string sym=p[0]; string tfstr=p[1]; ENUM_TIMEFRAMES tf; string expert=p[2];
  string tpl = (ArraySize(p)>3 && p[3]!="") ? p[3] : "";
  string pstr = (ArraySize(p)>4)?p[4]:"";
  if(!ResolveSymbolTf(sym, tfstr, tf)) { m="symbol"; return false; }
  long cid=ChartOpen(sym, tf); if(cid==0){ m="ChartOpen"; return false; }
  EnsureSymbol(sym);

  // aplica template direto somente se o usuário passar um .tpl explícito
  if(tpl=="" && pstr=="" && StringFind(expert, ".tpl")>0)
  {
    string tplPath="MQL5\\Profiles\\Templates\\"+expert;
    if(FileIsExist(tplPath))
    {
      if(!ChartApplyTemplate(cid, expert)) { m="ChartApplyTemplate"; return false; }
      if(!ChartHasExpert(cid, expert)) { m="ea not attached (init failed?)"; return false; }
      g_lastEAName=expert; g_lastEAParams=pstr; g_lastEASymbol=sym; g_lastEATf=p[1]; g_lastEATpl=expert;
      m="ea attached"; return true;
    }
  }

  // fallback: cria template com <expert> e aplica
  string epath=ResolveExpertPath(expert);
  string safe=expert;
  StringReplace(safe,"\\","_"); StringReplace(safe,"/","_"); StringReplace(safe," ","_");
  string tplName = "cmdmt_"+safe+".tpl";
  string baseTpl = tpl;
  if(baseTpl=="")
  {
    string prefer="Moving Average.tpl";
    if(FileIsExist(TemplatesRel()+"\\"+prefer)) baseTpl=prefer;
    else baseTpl=expert+".tpl";
  }
  string basePath = TemplatesRel()+"\\"+baseTpl;
  string txt=""; bool is_unicode=false;
  if(FileIsExist(basePath))
  {
    if(!ReadFileText(basePath, txt, is_unicode)){ m="tpl_read_fail"; return false; }
  }
  else
  {
    if(!ChartSaveTemplate(cid, tplName)) { m="tpl_save_fail"; return false; }
    string tplRel=TemplatesRel()+"\\"+tplName;
    if(!ReadFileText(tplRel, txt, is_unicode)){ m="tpl_read_fail"; return false; }
  }
  txt=StripExpertBlock(txt);
  string block=BuildExpertBlock(epath, pstr);
  int pos=StringFind(txt, "</chart>");
  if(pos>=0) txt = StringSubstr(txt,0,pos) + block + StringSubstr(txt,pos);
  else       txt = txt + "\n" + block;
  string outPath = TemplatesRel()+"\\"+tplName;
  if(!WriteFileText(outPath, txt, is_unicode)) { m="tpl_write_fail"; return false; }
  if(!ChartApplyTemplate(cid, tplName)) { m="ChartApplyTemplate"; return false; }
  Sleep(200);
  g_lastEAName=epath; g_lastEAParams=pstr; g_lastEASymbol=sym; g_lastEATf=tfstr; g_lastEATpl=tplName;
  m="ea attached"; return true;
}

// --- Extras herdados do listener ---
bool H_DetachAll(string &p[], string &m, string &d[])
{
  long cid=0;
  if(ArraySize(p)>=2)
  {
    string sym=p[0]; string tfstr=p[1]; ENUM_TIMEFRAMES tf;
    if(!ResolveSymbolTf(sym, tfstr, tf)) { m="symbol"; return false; }
    cid=ChartOpen(sym, tf); if(cid==0){ m="ChartOpen"; return false; }
  }
  else
  {
    cid=ChartID();
  }
  int totalWin = (int)ChartGetInteger(cid, CHART_WINDOWS_TOTAL);
  int removed=0;
  for(int sub=0; sub<totalWin; sub++)
  {
    int tot=ChartIndicatorsTotal(cid, sub);
    for(int i=tot-1;i>=0;i--)
    {
      string iname=ChartIndicatorName(cid, sub, i);
      if(iname!="" && ChartIndicatorDelete(cid, sub, iname)) removed++;
    }
  }
  m="detached_all="+IntegerToString((long)removed);
  return true;
}

bool H_RedrawChart(string &p[], string &m, string &d[])
{
  long cid=0;
  if(ArraySize(p)>=2)
  {
    string sym=p[0]; string tfstr=p[1]; ENUM_TIMEFRAMES tf;
    if(!ResolveSymbolTf(sym, tfstr, tf)) { m="symbol"; return false; }
    cid=ChartOpen(sym, tf); if(cid==0){ m="ChartOpen"; return false; }
  }
  else if(ArraySize(p)==1 && p[0]!="")
  {
    cid=(long)StringToInteger(p[0]);
  }
  else
  {
    cid=ChartID();
  }
  ChartRedraw(cid);
  m="redrawn"; return true;
}

bool H_WindowFind(string &p[], string &m, string &d[])
{
  if(ArraySize(p)<2){ m="params"; return false; }
  if(ArraySize(p)<3){ m="noop"; return true; }
  string sym=p[0]; string tfstr=p[1]; ENUM_TIMEFRAMES tf; string name=p[2];
  if(!ResolveSymbolTf(sym, tfstr, tf)) { m="symbol"; return false; }
  long cid=ChartOpen(sym, tf); if(cid==0){ m="ChartOpen"; return false; }
  int sub=ChartWindowFind(cid, name);
  ArrayResize(d,1); d[0]=IntegerToString(sub);
  m="ok"; return true;
}

bool H_ListInputs(string &p[], string &m, string &d[])
{
  string srcParams = (g_lastIndParams!="") ? g_lastIndParams : g_lastEAParams;
  if(srcParams=="") { m="none"; return true; }
  string kvs[]; int n=StringSplit(srcParams, ';', kvs);
  for(int i=0;i<n;i++)
  {
    if(kvs[i]=="") continue;
    ArrayResize(d,ArraySize(d)+1); d[ArraySize(d)-1]=kvs[i];
  }
  m=StringFormat("inputs=%d", ArraySize(d));
  return true;
}

bool H_SetInput(string &p[], string &m, string &d[])
{
  if(ArraySize(p)<2){ m="params"; return false; }
  string key=p[0]; string val=p[1];
  bool isInd = (g_lastIndParams!="");
  string paramsStr = isInd ? g_lastIndParams : g_lastEAParams;
  if(paramsStr==""){ m="no_context"; return false; }
  string out[]; int n=StringSplit(paramsStr,';',out);
  bool found=false;
  for(int i=0;i<n;i++)
  {
    if(out[i]=="") continue;
    string kv[]; int c=StringSplit(out[i],'=',kv);
    if(c==2 && kv[0]==key){ out[i]=key+"="+val; found=true; break; }
  }
  if(!found)
  {
    ArrayResize(out,n+1); out[n]=key+"="+val; n++;
  }
  paramsStr = Join(out, ";");
  if(isInd)
  {
    g_lastIndParams=paramsStr;
    string paramsNew[]; ArrayResize(paramsNew,5); // sym tf name sub params
    paramsNew[0]=g_lastIndSymbol; paramsNew[1]=g_lastIndTf; paramsNew[2]=g_lastIndName; paramsNew[3]=IntegerToString(g_lastIndSub); paramsNew[4]=paramsStr;
    return H_AttachInd(paramsNew, m, d);
  }
  else
  {
    g_lastEAParams=paramsStr;
    string paramsNew[]; ArrayResize(paramsNew,5);
    paramsNew[0]=g_lastEASymbol; paramsNew[1]=g_lastEATf; paramsNew[2]=g_lastEAName; paramsNew[3]=""; paramsNew[4]=paramsStr;
    return H_AttachEA(paramsNew, m, d);
  }
}

bool H_SnapshotSave(string &p[], string &m, string &d[])
{
  if(ArraySize(p)<1){ m="params"; return false; }
  string name=p[0];
  if(!EnsureSnapshotFolder()){ m="folder_fail"; return false; }
  string rel="snapshots\\"+name+".tpl";
  string tpl=SnapshotFolderRel()+"\\"+name+".tpl";
  long cid=ChartID();
  bool ok=ChartSaveTemplate(cid, rel);
  if(!ok) ok=ChartSaveTemplate(cid, tpl);
  m= ok?"saved":"save fail"; return ok;
}

bool H_SnapshotApply(string &p[], string &m, string &d[])
{
  if(ArraySize(p)<1){ m="params"; return false; }
  string name=p[0];
  string rel="snapshots\\"+name+".tpl";
  string tpl=SnapshotFolderRel()+"\\"+name+".tpl";
  if(!FileIsExist(tpl)){ m="not found"; return false; }
  bool ok=ChartApplyTemplate(ChartID(), rel);
  if(!ok) ok=ChartApplyTemplate(ChartID(), tpl);
  m= ok?"applied":"apply fail"; return ok;
}

bool H_SnapshotList(string &p[], string &m, string &d[])
{
  string folder=SnapshotFolderRel();
  if(!FileIsExist(folder)){ m="empty"; return true; }
  string path; long h=FileFindFirst(folder+"\\*.tpl", path);
  if(h==INVALID_HANDLE){ m="empty"; return true; }
  int c=0;
  while(true)
  {
    string base=StringSubstr(path, StringLen(folder)+2);
    ArrayResize(d,ArraySize(d)+1); d[ArraySize(d)-1]=base;
    c++;
    if(!FileFindNext(h, path)) break;
  }
  FileFindClose(h);
  m=StringFormat("snapshots=%d", c); return true;
}

bool H_ObjList(string &p[], string &m, string &d[])
{
  string prefix = (ArraySize(p)>0)?p[0]:"";
  int total=ObjectsTotal(0,0,-1);
  for(int i=0;i<total;i++)
  {
    string nm=ObjectName(0,i,0,-1);
    if(prefix!="" && StringFind(nm,prefix)!=0) continue;
    ArrayResize(d,ArraySize(d)+1); d[ArraySize(d)-1]=nm;
  }
  m=StringFormat("objs=%d", ArraySize(d)); return true;
}

bool H_ObjDelete(string &p[], string &m, string &d[])
{
  if(ArraySize(p)<1){ m="params"; return false; }
  string name=p[0];
  bool ok=ObjectDelete(0,name);
  m= ok? "deleted":"not_found"; return ok;
}

bool H_ObjDeletePrefix(string &p[], string &m, string &d[])
{
  if(ArraySize(p)<1){ m="params"; return false; }
  string prefix=p[0]; int total=ObjectsTotal(0,0,-1); int del=0;
  for(int i=total-1;i>=0;i--)
  {
    string nm=ObjectName(0,i,0,-1);
    if(StringFind(nm,prefix)==0) if(ObjectDelete(0,nm)) del++;
  }
  m=StringFormat("deleted=%d", del); return (del>0);
}

bool H_ObjMove(string &p[], string &m, string &d[])
{
  if(ArraySize(p)<3){ m="params"; return false; }
  string name=p[0]; datetime t1=(datetime)StringToTime(p[1]); double p1=StringToDouble(p[2]);
  int idx = (ArraySize(p)>=4)? (int)StringToInteger(p[3]) : 0;
  bool ok=ObjectMove(0, name, idx, t1, p1);
  m = ok? "moved":"move_fail"; return ok;
}

bool H_ObjCreate(string &p[], string &m, string &d[])
{
  // Minimal create: type,name,time,price,time2,price2
  if(ArraySize(p)<6){ m="params"; return false; }
  string type=p[0]; string name=p[1];
  datetime t1=(datetime)StringToTime(p[2]); double p1=StringToDouble(p[3]);
  datetime t2=(datetime)StringToTime(p[4]); double p2=StringToDouble(p[5]);
  ENUM_OBJECT ot = (ENUM_OBJECT)ObjectTypeFromString(type);
  bool ok=ObjectCreate(0, name, ot, 0, t1, p1, t2, p2);
  m = ok? "created":"create_fail"; return ok;
}

bool H_Screenshot(string &p[], string &m, string &d[])
{
  if(ArraySize(p)<3){ m="params"; return false; }
  string sym=p[0]; string tfstr=p[1]; ENUM_TIMEFRAMES tf; string file=p[2];
  if(!ResolveSymbolTf(sym, tfstr, tf)) { m="symbol"; return false; }
  int w=(ArraySize(p)>=4)?(int)StringToInteger(p[3]):0;
  int h=(ArraySize(p)>=5)?(int)StringToInteger(p[4]):0;
  long cid=ChartOpen(sym, tf); if(cid==0){ m="ChartOpen"; return false; }
  if(!ChartScreenShot(cid, file, w, h)) { m="screenshot fail"; return false; }
  m="screenshot saved"; return true;
}

bool H_DropInfo(string &p[], string &m, string &d[])
{
  long cid=ChartID();
  string sym=ChartSymbol(cid);
  ENUM_TIMEFRAMES tf=(ENUM_TIMEFRAMES)ChartPeriod(cid);
  ArrayResize(d,1); d[0]=StringFormat("chart=%s %s", sym, EnumToString(tf));
  m="ok"; return true;
}

bool H_ScreenshotSweep(string &p[], string &m, string &d[])
{
  // params: symbol, period, folder, base, steps, shift, align, width, height, fmt, delay
  if(ArraySize(p)<11){ m="params"; return false; }
  string sym=p[0]; string tfstr=p[1]; ENUM_TIMEFRAMES tf; string folder=p[2]; string base=p[3];
  if(!ResolveSymbolTf(sym, tfstr, tf)) { m="symbol"; return false; }
  int steps=(int)StringToInteger(p[4]); int shift=(int)StringToInteger(p[5]); string align=p[6];
  int width=(int)StringToInteger(p[7]); int height=(int)StringToInteger(p[8]); string fmt=p[9]; int delay=(int)StringToInteger(p[10]);
  long cid=ChartOpen(sym, tf); if(cid==0){ m="ChartOpen"; return false; }
  string align_l=align; StringToLower(align_l);
  bool left = (align_l=="left");
  for(int i=1;i<=steps;i++)
  {
    if(left) ChartNavigate(cid, CHART_BEGIN, shift);
    else     ChartNavigate(cid, CHART_CURRENT_POS, -shift);
    string fname=folder+"\\"+base+"-"+IntegerToString(i,3)+"."+fmt;
    ChartScreenShot(cid, fname, width, height);
    Sleep(delay);
  }
  m="sweep"; return true;
}

bool H_DetachEA(string &p[], string &m, string &d[])
{
  long cid=ChartID();
  bool removed=false;
  int total=ChartIndicatorsTotal(cid,0);
  for(int i=total-1;i>=0;i--)
  {
    string nm=ChartIndicatorName(cid,0,i);
    string nml=nm; StringToLower(nml);
    if(StringFind(nml, "experts\\")>=0)
    {
      if(ChartIndicatorDelete(cid,0,nm)) removed=true;
    }
  }
  if(removed){ m="ea detached"; return true; }
  if(FileIsExist("MQL5\\Profiles\\Templates\\Default.tpl"))
  {
    if(ChartApplyTemplate(cid, "Default.tpl")) { m="template default aplicado"; return true; }
  }
  m="ea detach not supported"; return false;
}

// Trade helpers
CTrade _trade;

bool H_TradeBuy(string &p[], string &m, string &d[])
{
  if(ArraySize(p)<2){ m="params"; return false; }
  string sym=p[0]; double lots=StringToDouble(p[1]);
  double sl=0,tp=0;
  if(ArraySize(p)>=3) sl=StringToDouble(p[2]);
  if(ArraySize(p)>=4) tp=StringToDouble(p[3]);
  _trade.SetAsyncMode(false);
  bool ok=_trade.Buy(lots, sym, 0, sl, tp);
  m= ok ? "buy sent" : "buy fail "+(string)_trade.ResultRetcode();
  if(_trade.ResultRetcode()!=0) m+=" "+_trade.ResultRetcodeDescription();
  return ok;
}

bool H_TradeSell(string &p[], string &m, string &d[])
{
  if(ArraySize(p)<2){ m="params"; return false; }
  string sym=p[0]; double lots=StringToDouble(p[1]);
  double sl=0,tp=0;
  if(ArraySize(p)>=3) sl=StringToDouble(p[2]);
  if(ArraySize(p)>=4) tp=StringToDouble(p[3]);
  _trade.SetAsyncMode(false);
  bool ok=_trade.Sell(lots, sym, 0, sl, tp);
  m= ok ? "sell sent" : "sell fail "+(string)_trade.ResultRetcode();
  if(_trade.ResultRetcode()!=0) m+=" "+_trade.ResultRetcodeDescription();
  return ok;
}

bool H_TradeCloseAll(string &p[], string &m, string &d[])
{
  int total=PositionsTotal(); int closed=0;
  for(int i=total-1;i>=0;i--)
  {
    ulong ticket=PositionGetTicket(i);
    if(ticket!=0)
    {
      string sym=PositionGetString(POSITION_SYMBOL);
      ENUM_POSITION_TYPE pt=(ENUM_POSITION_TYPE)PositionGetInteger(POSITION_TYPE);
      double lots=PositionGetDouble(POSITION_VOLUME);
      bool ok=false;
      if(pt==POSITION_TYPE_BUY) ok=_trade.PositionClose(ticket);
      else if(pt==POSITION_TYPE_SELL) ok=_trade.PositionClose(ticket);
      if(ok) closed++;
    }
  }
  m=StringFormat("closed=%d", closed); return (closed>0);
}

bool H_TradeList(string &p[], string &m, string &d[])
{
  int total=PositionsTotal();
  ArrayResize(d,0);
  for(int i=0;i<total;i++)
  {
    ulong ticket=PositionGetTicket(i);
    if(ticket==0) continue;
    // após PositionGetTicket, a posição fica selecionada
    string sym   = PositionGetString(POSITION_SYMBOL);
    ENUM_POSITION_TYPE pt = (ENUM_POSITION_TYPE)PositionGetInteger(POSITION_TYPE);
    double vol    = PositionGetDouble(POSITION_VOLUME);
    double price  = PositionGetDouble(POSITION_PRICE_OPEN);
    double sl     = PositionGetDouble(POSITION_SL);
    double tp     = PositionGetDouble(POSITION_TP);
    int idx = ArraySize(d);
    ArrayResize(d, idx+1);
    d[idx]=StringFormat("%I64u|%s|%d|%g|%g|%g|%g", ticket, sym, pt, vol, price, sl, tp);
  }
  m=StringFormat("positions=%d", ArraySize(d)); return true;
}

// Dispara ação de "script" (encapsulada em ScriptActions.mqh)
bool H_RunScript(string &p[], string &m, string &d[])
{
  return RunScriptAction(p, m, d);
}

bool Dispatch(string type, string &params[], string &msg, string &data[])
{
  if(type=="PING") return H_Ping(params,msg,data);
  if(type=="DEBUG_MSG") return H_Debug(params,msg,data);
  if(type=="GLOBAL_SET") return H_GlobalSet(params,msg,data);
  if(type=="GLOBAL_GET") return H_GlobalGet(params,msg,data);
  if(type=="GLOBAL_DEL") return H_GlobalDel(params,msg,data);
  if(type=="GLOBAL_DEL_PREFIX") return H_GlobalDelPrefix(params,msg,data);
  if(type=="GLOBAL_LIST") return H_GlobalList(params,msg,data);
  if(type=="DETACH_ALL") return H_DetachAll(params,msg,data);
  if(type=="OPEN_CHART") return H_OpenChart(params,msg,data);
  if(type=="REDRAW_CHART") return H_RedrawChart(params,msg,data);
  if(type=="SCREENSHOT") return H_Screenshot(params,msg,data);
  if(type=="SCREENSHOT_SWEEP") return H_ScreenshotSweep(params,msg,data);
  if(type=="DROP_INFO") return H_DropInfo(params,msg,data);
  if(type=="APPLY_TPL") return H_ApplyTpl(params,msg,data);
  if(type=="SAVE_TPL") return H_SaveTpl(params,msg,data);
  if(type=="CLOSE_CHART") return H_CloseChart(params,msg,data);
  if(type=="CLOSE_ALL") return H_CloseAll(params,msg,data);
  if(type=="LIST_CHARTS") return H_ListCharts(params,msg,data);
  if(type=="WINDOW_FIND") return H_WindowFind(params,msg,data);
  if(type=="LIST_INPUTS") return H_ListInputs(params,msg,data);
  if(type=="SET_INPUT") return H_SetInput(params,msg,data);
  if(type=="SNAPSHOT_SAVE") return H_SnapshotSave(params,msg,data);
  if(type=="SNAPSHOT_APPLY") return H_SnapshotApply(params,msg,data);
  if(type=="SNAPSHOT_LIST") return H_SnapshotList(params,msg,data);
  if(type=="ATTACH_IND_FULL") return H_AttachInd(params,msg,data);
  if(type=="DETACH_IND_FULL") return H_DetachInd(params,msg,data);
  if(type=="IND_TOTAL") return H_IndTotal(params,msg,data);
  if(type=="IND_NAME") return H_IndName(params,msg,data);
  if(type=="IND_HANDLE") return H_IndHandle(params,msg,data);
  if(type=="ATTACH_EA_FULL") return H_AttachEA(params,msg,data);
  if(type=="DETACH_EA_FULL") return H_DetachEA(params,msg,data);
  if(type=="RUN_SCRIPT") return H_RunScript(params,msg,data);
  if(type=="TRADE_BUY") return H_TradeBuy(params,msg,data);
  if(type=="TRADE_SELL") return H_TradeSell(params,msg,data);
  if(type=="TRADE_CLOSE_ALL") return H_TradeCloseAll(params,msg,data);
  if(type=="TRADE_LIST") return H_TradeList(params,msg,data);
  if(type=="OBJ_LIST") return H_ObjList(params,msg,data);
  if(type=="OBJ_DELETE") return H_ObjDelete(params,msg,data);
  if(type=="OBJ_DELETE_PREFIX") return H_ObjDeletePrefix(params,msg,data);
  if(type=="OBJ_MOVE") return H_ObjMove(params,msg,data);
  if(type=="OBJ_CREATE") return H_ObjCreate(params,msg,data);
  msg="unknown"; return false;
}

#endif
