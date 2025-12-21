//+------------------------------------------------------------------+
//| PipeCommandService.mq5                                          |
//| Serviço: recebe comandos via named pipe e executa ações básicas  |
//| Canal: \\.\pipe\mt5pipe (mt5_pipe_server.dll)                    |
//+------------------------------------------------------------------+
#property service
#property strict

input string InpPipeName = "\\\\.\\pipe\\mt5pipe"; // nome completo do pipe
input int    InpSleepMs  = 50;                           // espera entre polls

#include <PipeBridge.mqh>

uchar g_buf[65536];

// split simples
int Split(const string s, const string sep, string &out[])
{
   int n = StringSplit(s, sep, out);
   return n;
}

// escreve resposta no pipe
void SendResp(int pipe_id, const string payload)
{
   uchar bytes[];
   StringToCharArray(payload, bytes, 0, StringLen(payload), CP_UTF8);
   PipeReply(pipe_id, bytes, ArraySize(bytes));
}

// util: timeframe string -> ENUM_TIMEFRAMES
ENUM_TIMEFRAMES TfFromStr(const string tf_str)
{
   if(StringCompare(tf_str,"M1",true)==0) return PERIOD_M1;
   if(StringCompare(tf_str,"M5",true)==0) return PERIOD_M5;
   if(StringCompare(tf_str,"M15",true)==0) return PERIOD_M15;
   if(StringCompare(tf_str,"M30",true)==0) return PERIOD_M30;
   if(StringCompare(tf_str,"H1",true)==0) return PERIOD_H1;
   if(StringCompare(tf_str,"H4",true)==0) return PERIOD_H4;
   if(StringCompare(tf_str,"D1",true)==0) return PERIOD_D1;
   if(StringCompare(tf_str,"W1",true)==0) return PERIOD_W1;
   if(StringCompare(tf_str,"MN1",true)==0) return PERIOD_MN1;
   return (ENUM_TIMEFRAMES)0;
}

void OnStart()
{
   int rc = PipeStart(InpPipeName);
   if(rc!=0)
   {
      Print("[PipeSvc] PipeStart falhou rc=", rc, " pipe=", InpPipeName);
      return;
   }
   Print("[PipeSvc] ativo em ", InpPipeName);

   while(!IsStopped())
   {
      int pend = PipePending();
      if(pend<=0) { Sleep(InpSleepMs); continue; }

      int pid=0;
      int got = PipeNext(g_buf, ArraySize(g_buf), pid);
      if(got<=0) { Sleep(InpSleepMs); continue; }

      string line = CharArrayToString(g_buf, 0, got, CP_UTF8);
      StringReplace(line, "\r", "");
      StringReplace(line, "\n", "");
      string f[]; int n = Split(line, "|", f);
      if(n < 2) { SendResp(pid, "ERR|bad_format"); continue; }

      string msg_id = f[0];
      string cmd    = f[1];
      string resp   = "";
      bool ok = false;

      if(cmd == "PING")
      {
         resp = "OK|" + msg_id + "|PONG";
         ok = true;
      }
      else if(cmd == "OPEN_CHART" && n>=4)
      {
         string sym = f[2];
         ENUM_TIMEFRAMES tf = TfFromStr(f[3]);
         long ch = ::ChartOpen(sym, tf);
         ok = (ch>0);
         resp = (ok?"OK|":"ERR|") + msg_id + "|chart=" + (string)IntegerToString((int)ch);
      }
      else if(cmd == "APPLY_TPL" && n>=4)
      {
         long ch = (long)StrToInteger(f[2]);
         string tpl = f[3];
         ok = ::ChartApplyTemplate(ch, tpl);
         resp = (ok?"OK|":"ERR|") + msg_id + "|tpl=" + tpl;
      }
      else if(cmd == "CLOSE_CHART" && n>=3)
      {
         long ch = (long)StrToInteger(f[2]);
         ok = ::ChartClose(ch);
         resp = (ok?"OK|":"ERR|") + msg_id + "|chart=" + (string)IntegerToString((int)ch);
      }
      else if(cmd == "CLOSE_ALL")
      {
         int total = 0;
         long ch = ::ChartFirst();
         while(ch>=0)
         {
            ChartClose(ch);
            total++;
            ch = ChartNext(ch);
         }
         ok = true;
         resp = "OK|" + msg_id + "|closed=" + (string)IntegerToString(total);
      }
      else if(cmd == "LIST_CHARTS")
      {
         string items="";
         long ch = ChartFirst();
         int idx=0;
         while(ch>=0)
         {
            string sym = ChartGetString(ch, CHART_SYMBOL);
            long tfv   = ChartGetInteger(ch, CHART_PERIOD);
            ENUM_TIMEFRAMES tf = (ENUM_TIMEFRAMES)tfv;
            if(idx>0) items += ";";
            items += IntegerToString((int)ch) + "," + sym + "," + IntegerToString((int)tf);
            ch = ChartNext(ch);
            idx++;
         }
         ok = true;
         resp = "OK|" + msg_id + "|" + items;
      }
      else if(cmd == "GV_SET" && n>=4)
      {
         string k=f[2]; double v=StrToDouble(f[3]);
         ok = GlobalVariableSet(k,v);
         resp=(ok?"OK|":"ERR|")+msg_id+"|"+k;
      }
      else if(cmd == "GV_GET" && n>=3)
      {
         string k=f[2];
         if(GlobalVariableCheck(k)) { double v=GlobalVariableGet(k); resp="OK|"+msg_id+"|"+DoubleToString(v,8); ok=true; }
         else { resp="ERR|"+msg_id+"|not_found"; }
      }
      else if(cmd == "GV_LIST")
      {
         int total = GlobalVariablesTotal();
         string acc="";
         for(int i=0;i<total;i++)
         {
            string name; datetime t; double v;
            GlobalVariableGet(i, name, t, v);
            if(i>0) acc += ";";
            acc += name + "=" + DoubleToString(v,8);
         }
         ok=true; resp="OK|"+msg_id+"|"+acc;
      }
      else
      {
         resp = "ERR|" + msg_id + "|unknown_cmd";
      }

      SendResp(pid, resp);
   }

   PipeStop();
   Print("[PipeSvc] encerrado");
}
