// ScriptActions.mqh
// Funções que emulam o "script" a ser disparado pelo serviço.
// Preencha RunScriptAction com a lógica desejada.

#ifndef __SCRIPT_ACTIONS_MQH__
#define __SCRIPT_ACTIONS_MQH__

// Ação padrão: abre um chart e aplica um template.
// params: [0]=symbol, [1]=timeframe (M1,M5,...), [2]=template path
// Retorna msg "applied" ou erro "params"/"tf"/"chart"/"tpl"
bool RunScriptAction(string &params[], string &msg, string &data[])
{
  if(ArraySize(params)<3){ msg="params"; return false; }
  string sym=params[0]; string tfstr=params[1]; string tpl=params[2];
  ENUM_TIMEFRAMES tf;
  tf=PERIOD_CURRENT;
  // converter tf
  string u=tfstr; StringToUpper(u);
  if(u=="M1") tf=PERIOD_M1; else
  if(u=="M5") tf=PERIOD_M5; else
  if(u=="M15") tf=PERIOD_M15; else
  if(u=="M30") tf=PERIOD_M30; else
  if(u=="H1") tf=PERIOD_H1; else
  if(u=="H4") tf=PERIOD_H4; else
  if(u=="D1") tf=PERIOD_D1; else
  if(u=="W1") tf=PERIOD_W1; else
  if(u=="MN1") tf=PERIOD_MN1; else { msg="tf"; return false; }

  long cid=ChartOpen(sym, tf);
  if(cid==0){ msg="chart"; return false; }
  if(!ChartApplyTemplate(cid, tpl)){ msg="tpl"; return false; }
  msg="applied";
  return true;
}

#endif
