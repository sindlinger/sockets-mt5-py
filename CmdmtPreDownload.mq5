//+------------------------------------------------------------------+
//| CmdmtPreDownload.mq5                                             |
//| Script: pre-download history for symbol/period                   |
//+------------------------------------------------------------------+
#property strict
#property script_show_inputs

input int DaysBack        = 30;   // Days to request
input int BarsTarget      = 0;    // If >0, request this many bars
input int SleepMs         = 1000; // Delay between attempts
input int MaxAttempts     = 120;  // Max tries to CopyRates
input int WaitSync        = 1;    // Wait for terminal sync before CopyRates
input int MaxSyncAttempts = 120;  // Max tries for sync

bool WaitTerminalSync()
{
   if(WaitSync==0)
      return true;
   for(int i=0;i<MaxSyncAttempts;i++)
     {
      if(TerminalInfoInteger(TERMINAL_CONNECTED))
        {
         SymbolSelect(_Symbol,true);
         if(SeriesInfoInteger(_Symbol,_Period,SERIES_SYNCHRONIZED))
            return true;
        }
      Sleep(SleepMs);
     }
   return false;
}

void OnStart()
{
   if(!WaitTerminalSync())
      Print("[CmdmtPreDownload] sync_timeout");

   datetime to=TimeCurrent();
   if(to==0) to=TimeLocal();
   datetime from=to - (datetime)(DaysBack*86400);
   MqlRates rates[];
   int copied=0;
   for(int i=0;i<MaxAttempts;i++)
     {
      ResetLastError();
      if(BarsTarget>0)
         copied = CopyRates(_Symbol,_Period,0,BarsTarget,rates);
      else
         copied = CopyRates(_Symbol,_Period,from,to,rates);
      int err=GetLastError();
      PrintFormat("[CmdmtPreDownload] attempt=%d copied=%d err=%d", i+1, copied, err);
      if(copied>0) break;
      Sleep(SleepMs);
     }
}
