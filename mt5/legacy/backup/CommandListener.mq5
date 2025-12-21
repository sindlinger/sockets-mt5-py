#property copyright "MTCLI"
#property link      ""
#property version   "1.0"
#property strict

// CommandListener: lê cmd_*.txt em MQL5\Files e grava resp_*.txt
// Versão 1.0.6 — cobre comandos do mtcli (chart/tpl/ind/ea/obj/trade/globals/tests)

#include <Trade\Trade.mqh>
CTrade trade;

string g_files_dir;
int    g_timer_sec = 1;
string LISTENER_VERSION = "1.0.6";

// Armazena último attach para inputs simples
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

int BuildParams(const string pstr, MqlParam &outParams[]);

// Utilidades --------------------------------------------------------------
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

ENUM_OBJECT ObjectTypeFromString(const string t)
{
  string u=StringUpper(t);
  if(u=="OBJ_TREND") return OBJ_TREND;
  if(u=="OBJ_HLINE") return OBJ_HLINE;
  if(u=="OBJ_VLINE") return OBJ_VLINE;
  if(u=="OBJ_RECTANGLE") return OBJ_RECTANGLE;
  if(u=="OBJ_TEXT") return OBJ_TEXT;
  if(u=="OBJ_LABEL") return OBJ_LABEL;
  if(u=="OBJ_ARROW") return OBJ_ARROW;
  if(u=="OBJ_TRIANGLE") return OBJ_TRIANGLE;
  if(u=="OBJ_ELLIPSE") return OBJ_ELLIPSE;
  if(u=="OBJ_CHANNEL") return OBJ_CHANNEL;
  return OBJ_TREND;
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

bool WriteResp(string id, bool ok, string message, string data[])
{
  string fname = g_files_dir + "\\resp_" + id + ".txt";
  int h = FileOpen(fname, FILE_WRITE|FILE_TXT|FILE_ANSI);
  if(h==INVALID_HANDLE) return false;
  FileWriteString(h, ok ? "OK" : "ERROR"); FileWriteString(h, "\n");
  FileWriteString(h, message); FileWriteString(h, "\n");
  for(int i=0;i<ArraySize(data);i++) { FileWriteString(h, data[i]); FileWriteString(h, "\n"); }
  FileClose(h);
  return true;
}

bool ReadCommand(string &filepath, string &id, string &type, string &params[])
{
  string mask = g_files_dir + "\\cmd_*.txt";
  long h=FileFindFirst(mask, filepath);
  if(h==INVALID_HANDLE) return false;
  FileFindClose(h);
  int fh = FileOpen(filepath, FILE_READ|FILE_TXT|FILE_ANSI);
  if(fh==INVALID_HANDLE) return false;
  string line = FileReadString(fh);
  FileClose(fh);
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

// Conversões --------------------------------------------------------------
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

int SubwindowSafe(const string val)
{
  if(val=="") return 1;
  int v=(int)StrToInteger(val);
  return (v<=0)?1:v;
}

int ParseParams(const string pstr, string &keys[], string &vals[])
{
  if(pstr=="") return 0;
  string pairs[]; int n=StringSplit(pstr, ';', pairs);
  int count=0;
  ArrayResize(keys, n); ArrayResize(vals, n);
  for(int i=0;i<n;i++)
  {
    string kv[]; int c=StringSplit(pairs[i], '=', kv);
    if(c==2)
    {
      keys[count]=kv[0]; vals[count]=kv[1];
      count++;
    }
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
    if(StringLen(vs[i])>0 && num!=0 || vs[i]=="0")
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

double ToDoubleSafe(const string v) { return StrToDouble(v); }
int ToIntSafe(const string v) { return (int)StrToInteger(v); }
color ToColorSafe(const string v) { return (v=="") ? clrWhite : (color)StringToInteger(v); }

bool EnsureSymbol(const string sym)
{
  if(SymbolSelect(sym, true)) return true;
  Print("[listener] SymbolSelect failed for ", sym);
  return false;
}

// Handlers ----------------------------------------------------------------
bool H_Ping(string p[], string &m, string &d[]) { m="pong "+LISTENER_VERSION; return true; }

bool H_Debug(string p[], string &m, string &d[]) { if(ArraySize(p)>0) Print(p[0]); m="printed"; return true; }

bool H_GlobalSet(string p[], string &m, string &d[])
{
  if(ArraySize(p)<2){ m="params"; return false; }
  string name=p[0]; double val=StrToDouble(p[1]);
  bool ok = GlobalVariableSet(name, val) > 0;
  m = ok?"set":"fail"; return ok;
}

bool H_GlobalGet(string p[], string &m, string &d[])
{
  if(ArraySize(p)<1){ m="params"; return false; }
  string name=p[0];
  if(!GlobalVariableCheck(name)){ m="not_found"; return false; }
  double v = GlobalVariableGet(name);
  ArrayResize(d,1); d[0]=DoubleToString(v,8);
  m="ok"; return true;
}

bool H_GlobalDel(string p[], string &m, string &d[])
{
  if(ArraySize(p)<1){ m="params"; return false; }
  m = GlobalVariableDel(p[0]) ? "deleted" : "not_found";
  return (m=="deleted");
}

bool H_GlobalDelPrefix(string p[], string &m, string &d[])
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

bool H_GlobalList(string p[], string &m, string &d[])
{
  string prefix = (ArraySize(p)>0)?p[0]:"";
  int limit = (ArraySize(p)>1)?(int)StrToInteger(p[1]):0;
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

bool H_OpenChart(string p[], string &m, string &d[])
{
  if(ArraySize(p)<2){ m="params"; return false; }
  string sym=p[0]; ENUM_TIMEFRAMES tf=TfFromString(p[1]);
  if(tf==0){ m="tf"; return false; }
  long cid=ChartOpen(sym, tf);
  if(cid==0){ m="ChartOpen fail"; return false; }
  m="opened"; return true;
}

bool H_AttachInd(string p[], string &m, string &d[])
{
  if(ArraySize(p)<4){ m="params"; return false; }
  string sym=p[0]; string tfstr=p[1]; string name=p[2]; int sub=SubwindowSafe(p[3]);
  string pstr = (ArraySize(p)>4)?p[4]:"";
  ENUM_TIMEFRAMES tf=TfFromString(tfstr); if(tf==0){ m="tf"; return false; }
  long cid=ChartOpen(sym, tf); if(cid==0){ m="ChartOpen"; return false; }
  MqlParam inputs[]; BuildParams(pstr, inputs);
  int handle=iCustom(sym, tf, name, inputs);
  if(handle==INVALID_HANDLE){ m="iCustom fail"; return false; }
  if(!ChartIndicatorAdd(cid, sub-1, handle)){ m="ChartIndicatorAdd"; return false; }
  g_lastIndName=name; g_lastIndParams=pstr; g_lastIndSymbol=sym; g_lastIndTf=tfstr; g_lastIndSub=sub;
  m="indicator attached"; return true;
}

bool H_DetachInd(string p[], string &m, string &d[])
{
  if(ArraySize(p)<4){ m="params"; return false; }
  string sym=p[0]; string tfstr=p[1]; string name=p[2]; int sub=SubwindowSafe(p[3]);
  ENUM_TIMEFRAMES tf=TfFromString(tfstr); if(tf==0){ m="tf"; return false; }
  long cid=ChartOpen(sym, tf); if(cid==0){ m="ChartOpen"; return false; }
  int total=ChartIndicatorsTotal(cid, sub-1);
  for(int i=total-1;i>=0;i--)
  {
    string iname=ChartIndicatorName(cid, sub-1, i);
    if(StringCompare(iname, name)==0) ChartIndicatorDelete(cid, sub-1, i);
  }
  m="indicator detached"; return true;
}

bool H_IndTotal(string p[], string &m, string &d[])
{
  if(ArraySize(p)<3){ m="params"; return false; }
  string sym=p[0]; ENUM_TIMEFRAMES tf=TfFromString(p[1]); int sub=SubwindowSafe(p[2]);
  long cid=ChartOpen(sym, tf); if(cid==0){ m="ChartOpen"; return false; }
  int total=ChartIndicatorsTotal(cid, sub-1);
  string line=IntegerToString(total); ArrayResize(d,1); d[0]=line; m="ok"; return true;
}

bool H_IndName(string p[], string &m, string &d[])
{
  if(ArraySize(p)<4){ m="params"; return false; }
  string sym=p[0]; ENUM_TIMEFRAMES tf=TfFromString(p[1]); int sub=SubwindowSafe(p[2]); int idx=(int)StrToInteger(p[3]);
  long cid=ChartOpen(sym, tf); if(cid==0){ m="ChartOpen"; return false; }
  string nm=ChartIndicatorName(cid, sub-1, idx);
  ArrayResize(d,1); d[0]=nm; m="ok"; return true;
}

bool H_IndHandle(string p[], string &m, string &d[])
{
  if(ArraySize(p)<4){ m="params"; return false; }
  string sym=p[0]; ENUM_TIMEFRAMES tf=TfFromString(p[1]); int sub=SubwindowSafe(p[2]); string name=p[3];
  long cid=ChartOpen(sym, tf); if(cid==0){ m="ChartOpen"; return false; }
  long h=ChartIndicatorGet(cid, sub-1, name);
  ArrayResize(d,1); d[0]=IntegerToString((long)h);
  m=(h!=INVALID_HANDLE)?"ok":"not_found";
  return true;
}

bool H_DetachAll(string p[], string &m, string &d[])
{
  long cid=ChartID();
  int subs=ChartWindowsTotal();
  for(int s=0;s<subs;s++)
  {
    int total=ChartIndicatorsTotal(cid, s);
    for(int i=total-1;i>=0;i--) ChartIndicatorDelete(cid, s, i);
  }
  m="indicators removed"; return true;
}

bool H_CloseChart(string p[], string &m, string &d[])
{
  if(ArraySize(p)<2){ m="params"; return false; }
  string sym=p[0]; ENUM_TIMEFRAMES tf=TfFromString(p[1]);
  long id=ChartFirst(); int closed=0;
  while(id>=0)
  {
    if(ChartSymbol(id)==sym && ChartPeriod(id)==tf)
    {
      ChartClose(id); closed++;
    }
    id=ChartNext(id);
  }
  m=StringFormat("closed=%d", closed); return true;
}

bool H_CloseAll(string p[], string &m, string &d[])
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

bool H_RedrawChart(string p[], string &m, string &d[])
{
  long cid = (ArraySize(p)>0 && p[0]!="") ? (long)StrToInteger(p[0]) : ChartID();
  ChartRedraw(cid);
  m="redrawn"; return true;
}

bool H_WindowFind(string p[], string &m, string &d[])
{
  if(ArraySize(p)<3){ m="params"; return false; }
  string sym=p[0]; ENUM_TIMEFRAMES tf=TfFromString(p[1]); string name=p[2];
  long cid=ChartOpen(sym, tf); if(cid==0){ m="ChartOpen"; return false; }
  int sub=ChartWindowFind(cid, name);
  ArrayResize(d,1); d[0]=IntegerToString(sub);
  m="ok"; return true;
}

bool H_DropInfo(string p[], string &m, string &d[])
{
  // Sem eventos; devolve info do chart atual
  long cid=ChartID();
  string sym=ChartSymbol(cid);
  ENUM_TIMEFRAMES tf=(ENUM_TIMEFRAMES)ChartPeriod(cid);
  ArrayResize(d,1); d[0]=StringFormat("chart=%s %s", sym, EnumToString(tf));
  m="ok"; return true;
}

bool H_Screenshot(string p[], string &m, string &d[])
{
  if(ArraySize(p)<3){ m="params"; return false; }
  string sym=p[0]; ENUM_TIMEFRAMES tf=TfFromString(p[1]); string file=p[2];
  int width = (ArraySize(p)>3) ? (int)StrToInteger(p[3]) : 0;
  int height= (ArraySize(p)>4) ? (int)StrToInteger(p[4]) : 0;
  long cid=ChartOpen(sym, tf); if(cid==0){ m="ChartOpen"; return false; }
  if(!ChartScreenShot(cid, file, width, height)) { m="fail"; return false; }
  m="shot"; return true;
}

bool H_ScreenshotSweep(string p[], string &m, string &d[])
{
  // params: symbol, period, folder, base, steps, shift, align, width, height, fmt, delay
  if(ArraySize(p)<11){ m="params"; return false; }
  string sym=p[0]; ENUM_TIMEFRAMES tf=TfFromString(p[1]); string folder=p[2]; string base=p[3];
  int steps=(int)StrToInteger(p[4]); int shift=(int)StrToInteger(p[5]); string align=p[6];
  int width=(int)StrToInteger(p[7]); int height=(int)StrToInteger(p[8]); string fmt=p[9]; int delay=(int)StrToInteger(p[10]);
  long cid=ChartOpen(sym, tf); if(cid==0){ m="ChartOpen"; return false; }
  bool left = (StringToLower(align)=="left");
  for(int i=1;i<=steps;i++)
  {
    if(left) ChartNavigate(cid, CHART_POSITION_FIRST, shift);
    else ChartNavigate(cid, CHART_CURRENT_POS, -shift);
    string fname=folder+"\\"+base+"-"+IntegerToString(i,3)+"."+fmt;
    ChartScreenShot(cid, fname, width, height);
    Sleep(delay);
  }
  m="sweep"; return true;
}

bool H_AttachEA(string p[], string &m, string &d[])
{
  if(ArraySize(p)<3){ m="params"; return false; }
  string sym=p[0]; ENUM_TIMEFRAMES tf=TfFromString(p[1]); string expert=p[2];
  string tpl = (ArraySize(p)>3 && p[3]!="") ? p[3] : "";
  string pstr = (ArraySize(p)>4)?p[4]:"";
  long cid=ChartOpen(sym, tf); if(cid==0){ m="ChartOpen"; return false; }
  EnsureSymbol(sym);
  string tplPath="MQL5\\Profiles\\Templates\\"+tpl;
  if(tpl!="" && FileIsExist(tplPath))
  {
    if(!ChartApplyTemplate(cid, tpl)) { m="ChartApplyTemplate"; return false; }
    g_lastEAName=expert; g_lastEAParams=pstr; g_lastEASymbol=sym; g_lastEATf=p[1]; g_lastEATpl=tpl;
    m="template applied (EA)"; return true;
  }
  // Se não houver template, tenta reattach via iCustom de Experts\expert com params simples string
  MqlParam inputs[]; BuildParams(pstr, inputs);
  int handle=iCustom(sym, tf, "Experts\\"+expert, inputs);
  if(handle==INVALID_HANDLE){ m="iCustom EA fail"; return false; }
  if(!ChartIndicatorAdd(cid, 0, handle)) { m="attach fail"; return false; }
  g_lastEAName=expert; g_lastEAParams=pstr; g_lastEASymbol=sym; g_lastEATf=p[1]; g_lastEATpl="";
  m="ea attached"; return true;
}

bool H_DetachEA(string p[], string &m, string &d[])
{
  long cid=ChartID();
  bool removed=false;
  // remove indicadores Experts\
  int total=ChartIndicatorsTotal(cid,0);
  for(int i=total-1;i>=0;i--)
  {
    string nm=ChartIndicatorName(cid,0,i);
    if(StringFind(StringToLower(nm), "experts\\")>=0)
    {
      ChartIndicatorDelete(cid,0,i); removed=true;
    }
  }
  if(removed){ m="ea detached"; return true; }
  // aplica template default se existir
  if(FileIsExist("MQL5\\Profiles\\Templates\\Default.tpl"))
  {
    if(ChartApplyTemplate(cid, "Default.tpl")) { m="template default aplicado"; return true; }
  }
  m="ea detach not supported"; return false;
}

bool H_ListCharts(string p[], string &m, string &d[])
{
  long id=ChartFirst();
  int count=0;
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

bool H_ListInputs(string p[], string &m, string &d[])
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

bool H_SetInput(string p[], string &m, string &d[])
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

bool H_SnapshotSave(string p[], string &m, string &d[])
{
  if(ArraySize(p)<1){ m="params"; return false; }
  string name=p[0];
  string folder=g_files_dir+"\\snapshots";
  if(!FileIsExist(folder)) FileCreateDirectory(folder);
  string tpl=folder+"\\"+name+".tpl";
  long cid=ChartID();
  bool ok=ChartSaveTemplate(cid, tpl);
  m= ok?"saved":"save fail"; return ok;
}
bool H_SnapshotApply(string p[], string &m, string &d[])
{
  if(ArraySize(p)<1){ m="params"; return false; }
  string name=p[0];
  string tpl=g_files_dir+"\\snapshots\\"+name+".tpl";
  if(!FileIsExist(tpl)){ m="not found"; return false; }
  bool ok=ChartApplyTemplate(ChartID(), tpl);
  m= ok?"applied":"apply fail"; return ok;
}
bool H_SnapshotList(string p[], string &m, string &d[])
{
  string folder=g_files_dir+"\\snapshots";
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

bool H_ObjList(string p[], string &m, string &d[])
{
  long cid=ChartID();
  int total=ObjectsTotal(cid, 0, -1);
  for(int i=0;i<total;i++)
  {
    string name=ObjectName(cid, i, 0, -1);
    string type=EnumToString((ENUM_OBJECT)ObjectGetInteger(cid, name, OBJPROP_TYPE));
    ArrayResize(d,ArraySize(d)+1); d[ArraySize(d)-1]=type+"|"+name;
  }
  m=StringFormat("objs=%d", total); return true;
}

bool H_ObjDelete(string p[], string &m, string &d[])
{
  if(ArraySize(p)<1){ m="params"; return false; }
  long cid=ChartID();
  bool ok=ObjectDelete(cid, p[0]);
  m= ok?"deleted":"not_found"; return ok;
}

bool H_ObjDeletePrefix(string p[], string &m, string &d[])
{
  if(ArraySize(p)<1){ m="params"; return false; }
  long cid=ChartID();
  int total=ObjectsTotal(cid,0,-1);
  int removed=0;
  for(int i=total-1;i>=0;i--)
  {
    string name=ObjectName(cid,i,0,-1);
    if(StringFind(name,p[0])==0){ if(ObjectDelete(cid,name)) removed++; }
  }
  m=StringFormat("removed=%d", removed); return true;
}

bool H_ObjMove(string p[], string &m, string &d[])
{
  if(ArraySize(p)<3){ m="params"; return false; }
  long cid=ChartID();
  string name=p[0]; datetime t=StringToTime(p[1]); double price=StrToDouble(p[2]);
  bool ok=ObjectMove(cid,name,0,t,price);
  m= ok?"moved":"fail"; return ok;
}

bool H_ObjCreate(string p[], string &m, string &d[])
{
  if(ArraySize(p)<3){ m="params"; return false; }
  string type=p[0]; string name=p[1]; string payload=p[2];
  datetime t1=StringToTime(PayloadGet(payload,"time"));
  double   p1=StrToDouble(PayloadGet(payload,"price"));
  datetime t2=StringToTime(PayloadGet(payload,"time2"));
  double   p2=StrToDouble(PayloadGet(payload,"price2"));
  string txt=PayloadGet(payload,"text");
  string clrstr=PayloadGet(payload,"color");
  color clr = (clrstr=="") ? clrWhite : (color)StringToInteger(clrstr);
  int style=ToIntSafe(PayloadGet(payload,"style"));
  int width=ToIntSafe(PayloadGet(payload,"width"));
  int anchor=ToIntSafe(PayloadGet(payload,"anchor"));
  int xdist=ToIntSafe(PayloadGet(payload,"x"));
  int ydist=ToIntSafe(PayloadGet(payload,"y"));
  int fontsize=ToIntSafe(PayloadGet(payload,"fontsize"));
  string font=PayloadGet(payload,"font");
  bool back = (PayloadGet(payload,"back")=="1");
  bool selectable = (PayloadGet(payload,"selectable")!="0");
  bool hidden = (PayloadGet(payload,"hidden")=="1");
  long cid=ChartID();
  ENUM_OBJECT ot=(ENUM_OBJECT)ObjectTypeFromString(type);
  bool ok=ObjectCreate(cid, name, ot, 0, t1, p1, t2, p2);
  if(!ok){ m="create fail"; return false; }
  if(txt!="") ObjectSetString(cid,name,OBJPROP_TEXT,txt);
  if(style>0) ObjectSetInteger(cid,name,OBJPROP_STYLE,style);
  if(width>0) ObjectSetInteger(cid,name,OBJPROP_WIDTH,width);
  ObjectSetInteger(cid,name,OBJPROP_COLOR,clr);
  if(fontsize>0) ObjectSetInteger(cid,name,OBJPROP_FONTSIZE,fontsize);
  if(font!="") ObjectSetString(cid,name,OBJPROP_FONT,font);
  if(anchor>0) ObjectSetInteger(cid,name,OBJPROP_ANCHOR,anchor);
  if(xdist>0) ObjectSetInteger(cid,name,OBJPROP_XDISTANCE,xdist);
  if(ydist>0) ObjectSetInteger(cid,name,OBJPROP_YDISTANCE,ydist);
  ObjectSetInteger(cid,name,OBJPROP_BACK,back);
  ObjectSetInteger(cid,name,OBJPROP_SELECTED,false);
  ObjectSetInteger(cid,name,OBJPROP_SELECTABLE,selectable);
  ObjectSetInteger(cid,name,OBJPROP_HIDDEN,hidden);
  m="created"; return true;
}

bool H_TradeBuy(string p[], string &m, string &d[])
{
  if(ArraySize(p)<2){ m="params"; return false; }
  string sym=p[0]; double vol=StrToDouble(p[1]);
  if(!EnsureSymbol(sym)) { m="symbol"; return false; }
  if(vol<=0){ m="volume"; return false; }
  double sl = (ArraySize(p)>2 && p[2]!="") ? StrToDouble(p[2]) : 0;
  double tp = (ArraySize(p)>3 && p[3]!="") ? StrToDouble(p[3]) : 0;
  string comment=(ArraySize(p)>4)?p[4]:"";
  bool ok=trade.Buy(vol, sym, 0, sl, tp, comment);
  m = ok?"buy ok":"buy fail";
  return ok;
}
bool H_TradeSell(string p[], string &m, string &d[])
{
  if(ArraySize(p)<2){ m="params"; return false; }
  string sym=p[0]; double vol=StrToDouble(p[1]);
  if(!EnsureSymbol(sym)) { m="symbol"; return false; }
  if(vol<=0){ m="volume"; return false; }
  double sl = (ArraySize(p)>2 && p[2]!="") ? StrToDouble(p[2]) : 0;
  double tp = (ArraySize(p)>3 && p[3]!="") ? StrToDouble(p[3]) : 0;
  string comment=(ArraySize(p)>4)?p[4]:"";
  bool ok=trade.Sell(vol, sym, 0, sl, tp, comment);
  m = ok?"sell ok":"sell fail";
  return ok;
}
bool H_TradeCloseAll(string p[], string &m, string &d[])
{
  int total=PositionsTotal();
  int closed=0;
  for(int i=total-1;i>=0;i--)
  {
    ulong ticket=PositionGetTicket(i);
    if(trade.PositionClose(ticket)) closed++;
  }
  m=StringFormat("closed=%d", closed);
  return true;
}
bool H_TradeList(string p[], string &m, string &d[])
{
  int total=PositionsTotal();
  for(int i=0;i<total;i++)
  {
    if(!PositionSelectByIndex(i)) continue;
    string line=StringFormat("%s|%s|vol=%.2f|price=%.5f|sl=%.5f|tp=%.5f|ticket=%I64u",
      PositionGetString(POSITION_SYMBOL),
      EnumToString((ENUM_POSITION_TYPE)PositionGetInteger(POSITION_TYPE)),
      PositionGetDouble(POSITION_VOLUME),
      PositionGetDouble(POSITION_PRICE_OPEN),
      PositionGetDouble(POSITION_SL),
      PositionGetDouble(POSITION_TP),
      PositionGetInteger(POSITION_TICKET)
    );
    ArrayResize(d,ArraySize(d)+1); d[ArraySize(d)-1]=line;
  }
  m=StringFormat("positions=%d", total);
  return true;
}

// Dispatcher --------------------------------------------------------------
bool Dispatch(string type, string params[], string &msg, string &data[])
{
  if(type=="PING") return H_Ping(params,msg,data);
  if(type=="DEBUG_MSG") return H_Debug(params,msg,data);
  if(type=="GLOBAL_SET") return H_GlobalSet(params,msg,data);
  if(type=="GLOBAL_GET") return H_GlobalGet(params,msg,data);
  if(type=="GLOBAL_DEL") return H_GlobalDel(params,msg,data);
  if(type=="GLOBAL_DEL_PREFIX") return H_GlobalDelPrefix(params,msg,data);
  if(type=="GLOBAL_LIST") return H_GlobalList(params,msg,data);
  if(type=="DETACH_ALL") return H_DetachAll(params,msg,data);
  if(type=="CLOSE_CHART") return H_CloseChart(params,msg,data);
  if(type=="CLOSE_ALL") return H_CloseAll(params,msg,data);
  if(type=="APPLY_TPL") return H_ApplyTpl(params,msg,data);
  if(type=="SAVE_TPL") return H_SaveTpl(params,msg,data);
  if(type=="REDRAW_CHART") return H_RedrawChart(params,msg,data);
  if(type=="WINDOW_FIND") return H_WindowFind(params,msg,data);
  if(type=="DROP_INFO") return H_DropInfo(params,msg,data);
  if(type=="SCREENSHOT") return H_Screenshot(params,msg,data);
  if(type=="SCREENSHOT_SWEEP") return H_ScreenshotSweep(params,msg,data);
  if(type=="OPEN_CHART") return H_OpenChart(params,msg,data);
  if(type=="ATTACH_IND_FULL") return H_AttachInd(params,msg,data);
  if(type=="DETACH_IND_FULL") return H_DetachInd(params,msg,data);
  if(type=="IND_TOTAL") return H_IndTotal(params,msg,data);
  if(type=="IND_NAME") return H_IndName(params,msg,data);
  if(type=="IND_HANDLE") return H_IndHandle(params,msg,data);
  if(type=="ATTACH_EA_FULL") return H_AttachEA(params,msg,data);
  if(type=="DETACH_EA_FULL") return H_DetachEA(params,msg,data);
  if(type=="LIST_CHARTS") return H_ListCharts(params,msg,data);
  if(type=="LIST_INPUTS") return H_ListInputs(params,msg,data);
  if(type=="SET_INPUT") return H_SetInput(params,msg,data);
  if(type=="SNAPSHOT_SAVE") return H_SnapshotSave(params,msg,data);
  if(type=="SNAPSHOT_APPLY") return H_SnapshotApply(params,msg,data);
  if(type=="SNAPSHOT_LIST") return H_SnapshotList(params,msg,data);
  if(type=="OBJ_LIST") return H_ObjList(params,msg,data);
  if(type=="OBJ_DELETE") return H_ObjDelete(params,msg,data);
  if(type=="OBJ_DELETE_PREFIX") return H_ObjDeletePrefix(params,msg,data);
  if(type=="OBJ_MOVE") return H_ObjMove(params,msg,data);
  if(type=="OBJ_CREATE") return H_ObjCreate(params,msg,data);
  if(type=="TRADE_BUY") return H_TradeBuy(params,msg,data);
  if(type=="TRADE_SELL") return H_TradeSell(params,msg,data);
  if(type=="TRADE_CLOSE_ALL") return H_TradeCloseAll(params,msg,data);
  if(type=="TRADE_LIST") return H_TradeList(params,msg,data);
  msg="unknown"; return false;
}

// Ciclo -------------------------------------------------------------------
int OnInit()
{
  g_files_dir = TerminalInfoString(TERMINAL_DATA_PATH) + "\\MQL5\\Files";
  EventSetTimer(g_timer_sec);
  Print("CommandListener iniciado. Files=", g_files_dir);
  return(INIT_SUCCEEDED);
}

void OnDeinit(const int reason)
{
  EventKillTimer();
}

void OnTimer()
{
  string path,id,type; string params[]; string data[]; string msg="";
  if(!ReadCommand(path,id,type,params)) return;
  bool ok = Dispatch(type, params, msg, data);
  WriteResp(id, ok, msg, data);
  // remove cmd file
  FileDelete(path);
}
