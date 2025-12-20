//+------------------------------------------------------------------+
//| PyFftFile.mq5                                                    |
//| Indicador: envia array via arquivos (sem DLL)                    |
//| Python lê/FFT e devolve em arquivo binário                       |
//+------------------------------------------------------------------+
#property indicator_separate_window
#property indicator_buffers 1
#property indicator_plots   1
#property indicator_type1   DRAW_LINE
#property indicator_color1  clrMediumSeaGreen
#property indicator_label1  "FFT_FILE"
#property strict

input int    InpN    = 256;
input bool   InpHalf = false;
input bool   InpLog  = false;
input bool   InpNorm = false;
input string InpWindow = "hann"; // hann|hamming|blackman|""
input bool   InpNewBarOnly = true;
input int    InpTimeoutMs = 500;
input string InpBaseName = "pyfft";

static double Buf[];
static datetime last_bar = 0;

string ReqTxt()  { return InpBaseName + "_req.txt"; }
string ReqBin()  { return InpBaseName + "_req.bin"; }
string RespBin() { return InpBaseName + "_resp.bin"; }

bool WriteReq(const double &arr[], int count)
{
  // remove resposta antiga
  if(FileIsExist(RespBin())) FileDelete(RespBin());

  int hb = FileOpen(ReqBin(), FILE_WRITE|FILE_BIN);
  if(hb==INVALID_HANDLE) return false;
  FileWriteArray(hb, arr, 0, count);
  FileClose(hb);

  int ht = FileOpen(ReqTxt(), FILE_WRITE|FILE_TXT|FILE_ANSI);
  if(ht==INVALID_HANDLE) return false;
  string line = "count="+IntegerToString(count);
  line += ";half=" + (InpHalf?"1":"0");
  line += ";log=" + (InpLog?"1":"0");
  line += ";norm=" + (InpNorm?"1":"0");
  if(InpWindow!="") line += ";win=" + InpWindow;
  FileWriteString(ht, line);
  FileClose(ht);
  return true;
}

bool ReadResp(double &out[])
{
  if(!FileIsExist(RespBin())) return false;
  int h = FileOpen(RespBin(), FILE_READ|FILE_BIN);
  if(h==INVALID_HANDLE) return false;
  ulong sz = (ulong)FileSize(h);
  int count = (int)(sz/8);
  if(count<=0) { FileClose(h); return false; }
  ArrayResize(out, count);
  int got = (int)FileReadArray(h, out, 0, count);
  FileClose(h);
  if(got!=count) return false;
  FileDelete(RespBin());
  return true;
}

int OnInit()
{
  SetIndexBuffer(0, Buf, INDICATOR_DATA);
  ArraySetAsSeries(Buf, true);
  return INIT_SUCCEEDED;
}

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
{
  int n = InpN;
  if(n < 8) n = 8;
  if(rates_total < n) return 0;
  if(InpNewBarOnly)
  {
    if(time[0]==last_bar) return rates_total;
    last_bar = time[0];
  }

  double inbuf[];
  ArrayResize(inbuf, n);
  for(int i=0;i<n;i++) inbuf[i]=close[i];

  if(!WriteReq(inbuf, n)) return rates_total;

  uint start = GetTickCount();
  while((uint)(GetTickCount()-start) < (uint)InpTimeoutMs)
  {
    if(FileIsExist(RespBin())) break;
    Sleep(10);
  }

  double outbuf[];
  // clear first n
  int clearN = MathMin(rates_total, n);
  for(int i=0;i<clearN;i++) Buf[i]=0.0;

  if(ReadResp(outbuf))
  {
    int copyN = MathMin(ArraySize(outbuf), rates_total);
    for(int i=0;i<copyN;i++) Buf[i]=outbuf[i];
  }
  return rates_total;
}
