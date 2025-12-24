//+------------------------------------------------------------------+
//| OficialTelnetServiceBootstrap.mq5                                |
//| Servico bootstrap: dispara compilacao + start de servicos        |
//| via arquivo (MQL5/Files/bootstrap_request.txt)                   |
//+------------------------------------------------------------------+
#property service
#property strict

input bool   InpCompile   = true;
input string InpServices  = "OficialTelnetServiceSocket;PyInService";
input int    InpTimeoutSec= 120;
input int    InpSleepMs   = 250;
input bool   InpExitAfter = true; // one-shot

string ReqFile = "bootstrap_request.txt";
string RespFile= "bootstrap_response.txt";

bool WriteRequest()
{
  int h = FileOpen(ReqFile, FILE_WRITE|FILE_TXT|FILE_ANSI);
  if(h==INVALID_HANDLE) return false;
  FileWrite(h, "action=bootstrap");
  FileWrite(h, StringFormat("compile=%d", InpCompile?1:0));
  FileWrite(h, "services="+InpServices);
  FileWrite(h, "time="+TimeToString(TimeCurrent(), TIME_DATE|TIME_SECONDS));
  FileClose(h);
  return true;
}

string ReadAll(const string fname)
{
  int h = FileOpen(fname, FILE_READ|FILE_TXT|FILE_ANSI);
  if(h==INVALID_HANDLE) return "";
  string out="";
  while(!FileIsEnding(h))
  {
    string line = FileReadString(h);
    if(line=="") continue;
    out += line + "\n";
  }
  FileClose(h);
  return out;
}

void OnStart()
{
  // limpa resposta anterior
  if(FileIsExist(RespFile)) FileDelete(RespFile);
  if(FileIsExist(ReqFile)) FileDelete(ReqFile);

  if(!WriteRequest())
  {
    Print("[bootstrap] falha ao escrever request");
    return;
  }

  datetime start = TimeCurrent();
  bool got=false;
  while((int)(TimeCurrent()-start) < InpTimeoutSec)
  {
    if(FileIsExist(RespFile)) { got=true; break; }
    Sleep(InpSleepMs);
  }

  if(got)
  {
    string resp = ReadAll(RespFile);
    Print("[bootstrap] resposta:\n", resp);
  }
  else
  {
    Print("[bootstrap] timeout aguardando resposta");
  }

  if(InpExitAfter) return;
  while(true) Sleep(1000);
}
//+------------------------------------------------------------------+
