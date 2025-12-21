//+------------------------------------------------------------------+
//| PyFft.mq5                                                        |
//| Indicador: envia array via socket p/ serviço, FFT no Python       |
//| Retorna magnitudes e plota no buffer                             |
//+------------------------------------------------------------------+
#property indicator_separate_window
#property indicator_buffers 1
#property indicator_plots   1
#property indicator_type1   DRAW_LINE
#property indicator_color1  clrDodgerBlue
#property indicator_label1  "FFT"
#property strict

#include "..\\..\\Services\\OficialTelnetServiceSocket\\SocketBridge.mqh"

input int    InpN    = 256;
input bool   InpHalf = false;
input bool   InpLog  = false;
input bool   InpNorm = false;
input string InpWindow = "hann"; // hann|hamming|blackman|"" (none)
input bool   InpNewBarOnly = true;
input string InpHost = "127.0.0.1";
input int    InpPort = 9091;

static double Buf[];
static datetime last_bar = 0;
static bool g_wsaInit = false;

struct OneD
{
  double v;
};

bool EnsureWSA()
{
  if(g_wsaInit) return true;
  uchar wsa[400];
  if(WSAStartup(0x202, wsa)!=0) return false;
  g_wsaInit=true;
  return true;
}

uint IpFromHost(string host)
{
  if(host=="" || host=="127.0.0.1") return 0x7F000001;
  int a,b,c,d;
  string parts[];
  if(StringSplit(host,'.',parts)==4)
  {
    a=(int)StringToInteger(parts[0]); b=(int)StringToInteger(parts[1]);
    c=(int)StringToInteger(parts[2]); d=(int)StringToInteger(parts[3]);
    return ((uint)a<<24)|((uint)b<<16)|((uint)c<<8)|(uint)d;
  }
  return 0x7F000001;
}

bool ConnectService(uint &sock)
{
  if(!EnsureWSA()) return false;
  sock = socket(AF_INET, SOCK_STREAM, IPPROTO_TCP);
  if(sock==0) return false;
  uint ipHost = IpFromHost(InpHost);
  uchar sa[]; MakeSockAddr(sa, (ushort)InpPort, ipHost);
  if(connect(sock, sa, ArraySize(sa))!=0)
  {
    closesocket(sock); sock=0; return false;
  }
  return true;
}

bool SendStr(uint sock, const string s)
{
  uchar b[]; StringToCharArray(s, b, 0, StringLen(s), CP_UTF8);
  int r = send(sock, b, ArraySize(b), 0);
  return r >= 0;
}

bool RecvLine(uint sock, string &out)
{
  uchar buf[4096]; int idx=0; uchar ch[1];
  while(true)
  {
    int r=recv(sock, ch, 1, 0);
    if(r<=0) return false;
    if(ch[0]=='\n') break;
    if(idx<4096) buf[idx++]=ch[0];
  }
  out=CharArrayToString(buf,0,idx,CP_UTF8);
  return true;
}

bool SendFrame(uint sock, const string header, uchar &payload[])
{
  uchar hb[]; StringToCharArray(header, hb, 0, StringLen(header), CP_UTF8);
  int hlen = ArraySize(hb);
  uchar prefix[5];
  prefix[0]=0xFF;
  prefix[1]=(uchar)((hlen>>24)&0xFF);
  prefix[2]=(uchar)((hlen>>16)&0xFF);
  prefix[3]=(uchar)((hlen>>8)&0xFF);
  prefix[4]=(uchar)(hlen&0xFF);
  if(send(sock, prefix, 5, 0)<=0) return false;
  if(send(sock, hb, hlen, 0)<=0) return false;
  if(ArraySize(payload)>0)
  {
    if(send(sock, payload, ArraySize(payload), 0)<=0) return false;
  }
  return true;
}

bool RecvFrame(uint sock, string &header, uchar &payload[])
{
  uchar first[1];
  if(recv(sock, first, 1, 0)<=0) return false;
  if(first[0]!=0xFF) return false;
  uchar lenbuf[4];
  if(recv(sock, lenbuf, 4, 0)<=0) return false;
  int hlen = (lenbuf[0]<<24)|(lenbuf[1]<<16)|(lenbuf[2]<<8)|lenbuf[3];
  if(hlen<=0) return false;
  uchar hb[]; ArrayResize(hb, hlen);
  int got=0;
  while(got<hlen)
  {
    int r=recv(sock, hb, hlen-got, 0);
    if(r<=0) return false;
    got += r;
  }
  header = CharArrayToString(hb,0,hlen,CP_UTF8);
  // parse raw_len
  string parts[]; int n=StringSplit(header,'|',parts);
  int raw_len=0;
  if(n>=6) raw_len=(int)StringToInteger(parts[5]);
  if(raw_len>0)
  {
    ArrayResize(payload, raw_len);
    int got2=0;
    while(got2<raw_len)
    {
      int r=recv(sock, payload, raw_len-got2, 0);
      if(r<=0) return false;
      got2 += r;
    }
  }
  else ArrayResize(payload,0);
  return true;
}

bool DoublesToBytes(const double &arr[], int count, uchar &out[])
{
  if(count<=0) { ArrayResize(out,0); return false; }
  ArrayResize(out, count*8);
  OneD tmp; uchar b[]; ArrayResize(b,8);
  for(int i=0;i<count;i++)
  {
    tmp.v = arr[i];
    StructToCharArray(tmp, b);
    int off=i*8;
    for(int j=0;j<8;j++) out[off+j]=b[j];
  }
  return true;
}

bool BytesToDoubles(const uchar &in[], int count, double &out[])
{
  if(count<=0) return false;
  if(ArraySize(in) < count*8) return false;
  ArrayResize(out, count);
  OneD tmp; uchar b[]; ArrayResize(b,8);
  for(int i=0;i<count;i++)
  {
    int off=i*8;
    for(int j=0;j<8;j++) b[j]=in[off+j];
    CharArrayToStruct(tmp, b);
    out[i]=tmp.v;
  }
  return true;
}

string BuildFftName()
{
  string name = "fft";
  name += "?half=" + (InpHalf?"1":"0");
  name += "&log=" + (InpLog?"1":"0");
  name += "&norm=" + (InpNorm?"1":"0");
  if(InpWindow!="") name += "&win=" + InpWindow;
  return name;
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

  uchar raw[];
  if(!DoublesToBytes(inbuf, n, raw)) return rates_total;
  int raw_len = ArraySize(raw);
  if(raw_len<=0) return rates_total;

  uint sock=0;
  if(!ConnectService(sock)) return rates_total;

  string id = IntegerToString(GetTickCount());
  string name = BuildFftName();
  string h1 = id+"|SEND_ARRAY|"+name+"|f64|"+IntegerToString(n)+"|"+IntegerToString(raw_len);
  if(!SendFrame(sock, h1, raw)) { closesocket(sock); return rates_total; }
  string resp;
  if(!RecvLine(sock, resp)) { closesocket(sock); return rates_total; }

  string line = id+"|PY_ARRAY_CALL|"+name+"\n";
  SendStr(sock, line);
  if(!RecvLine(sock, resp)) { closesocket(sock); return rates_total; }

  uchar empty[]; ArrayResize(empty,0);
  string h2 = id+"|GET_ARRAY";
  if(!SendFrame(sock, h2, empty)) { closesocket(sock); return rates_total; }

  string rh; uchar payload[];
  if(!RecvFrame(sock, rh, payload)) { closesocket(sock); return rates_total; }

  // parse count from header
  string hp[]; int hn=StringSplit(rh,'|',hp);
  int out_count = 0;
  if(hn>=6) out_count = (int)StringToInteger(hp[4]);
  if(out_count<=0) out_count = ArraySize(payload)/8;

  double outbuf[];
  // clear first n to avoid stale values
  int clearN = MathMin(rates_total, n);
  for(int i=0;i<clearN;i++) Buf[i]=0.0;

  if(out_count>0 && BytesToDoubles(payload, out_count, outbuf))
  {
    int copyN = MathMin(out_count, rates_total);
    for(int i=0;i<copyN;i++) Buf[i]=outbuf[i];
  }

  closesocket(sock);
  return rates_total;
}

void OnDeinit(const int reason)
{
  if(g_wsaInit) { WSACleanup(); g_wsaInit=false; }
}
