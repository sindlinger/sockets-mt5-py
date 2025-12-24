// PyInBridge.mqh - mini SDK MQL para serviço Python (9091)
#ifndef __PYIN_BRIDGE_MQH__
#define __PYIN_BRIDGE_MQH__

#include "OficialTelnetServiceSocket/SocketBridge.mqh"

#define PYBR_DEFAULT_HOST "127.0.0.1"
#define PYBR_DEFAULT_PORT 9091

static bool g_pybr_wsa = false;

struct OneD
{
  double v;
};

bool PyBridgeEnsureWSA()
{
  if(g_pybr_wsa) return true;
  uchar wsa[400];
  if(WSAStartup(0x202, wsa)!=0) return false;
  g_pybr_wsa=true;
  return true;
}

uint PyBridgeIpFromHost(string host)
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

bool PyBridgeConnect(const string host, const int port, uint &sock)
{
  if(!PyBridgeEnsureWSA()) return false;
  sock = socket(AF_INET, SOCK_STREAM, IPPROTO_TCP);
  if(sock==0) return false;
  uint ipHost = PyBridgeIpFromHost(host);
  uchar sa[]; MakeSockAddr(sa, (ushort)port, ipHost);
  if(connect(sock, sa, ArraySize(sa))!=0)
  {
    closesocket(sock); sock=0; return false;
  }
  return true;
}

void PyBridgeClose(uint &sock)
{
  if(sock) { closesocket(sock); sock=0; }
}

bool PyBridgeSendStr(uint sock, const string s)
{
  uchar b[]; StringToCharArray(s, b, 0, StringLen(s), CP_UTF8);
  int r = send(sock, b, ArraySize(b), 0);
  return r >= 0;
}

bool PyBridgeRecvLine(uint sock, string &out)
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

bool PyBridgeRecvExact(uint sock, int len, uchar &out[])
{
  ArrayResize(out,len);
  int got=0;
  while(got<len)
  {
    int r = recv(sock, out, len-got, 0);
    if(r<=0) return false;
    got += r;
  }
  return true;
}

bool PyBridgeSendFrame(uint sock, const string header, uchar &payload[])
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

bool PyBridgeRecvFrame(uint sock, string &header, uchar &payload[])
{
  uchar first[1];
  if(recv(sock, first, 1, 0)<=0) return false;
  if(first[0]!=0xFF) return false;
  uchar lenbuf[4];
  if(!PyBridgeRecvExact(sock, 4, lenbuf)) return false;
  int hlen = (lenbuf[0]<<24)|(lenbuf[1]<<16)|(lenbuf[2]<<8)|lenbuf[3];
  if(hlen<=0) return false;
  uchar hb[]; ArrayResize(hb, hlen);
  if(!PyBridgeRecvExact(sock, hlen, hb)) return false;
  header = CharArrayToString(hb,0,hlen,CP_UTF8);
  string parts[]; int n=StringSplit(header,'|',parts);
  int raw_len=0;
  if(n>=6) raw_len=(int)StringToInteger(parts[5]);
  if(raw_len>0)
  {
    if(!PyBridgeRecvExact(sock, raw_len, payload)) return false;
  }
  else ArrayResize(payload,0);
  return true;
}

bool PyBridgeRead2(uint sock, string &status, string &msg)
{
  if(!PyBridgeRecvLine(sock, status)) return false;
  if(!PyBridgeRecvLine(sock, msg)) return false;
  return true;
}

bool PyBridgeRead3(uint sock, string &status, string &msg, string &data)
{
  if(!PyBridgeRead2(sock, status, msg)) return false;
  if(!PyBridgeRecvLine(sock, data)) { data=""; return false; }
  return true;
}

bool PyBridgeDoublesToBytes(const double &arr[], int count, uchar &out[])
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

bool PyBridgeBytesToDoubles(const uchar &in[], int count, double &out[])
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

bool PyBridgeSendArrayF64(const double &arr[], int count, const string name="input",
                          const string host=PYBR_DEFAULT_HOST, const int port=PYBR_DEFAULT_PORT,
                          string &err="")
{
  uint sock=0;
  if(!PyBridgeConnect(host, port, sock)) { err="conn"; return false; }
  uchar raw[];
  if(!PyBridgeDoublesToBytes(arr, count, raw)) { err="pack"; PyBridgeClose(sock); return false; }
  string id = IntegerToString(GetTickCount());
  string header = id+"|SEND_ARRAY|"+name+"|f64|"+IntegerToString(count)+"|"+IntegerToString(ArraySize(raw));
  if(!PyBridgeSendFrame(sock, header, raw)) { err="send"; PyBridgeClose(sock); return false; }
  string status, msg;
  if(!PyBridgeRead2(sock, status, msg)) { err="resp"; PyBridgeClose(sock); return false; }
  PyBridgeClose(sock);
  if(status!="OK") { err=msg; return false; }
  return true;
}

bool PyBridgeCallJson(const string json, string &pyresp,
                      const string host=PYBR_DEFAULT_HOST, const int port=PYBR_DEFAULT_PORT,
                      string &err="")
{
  uint sock=0;
  if(!PyBridgeConnect(host, port, sock)) { err="conn"; return false; }
  string id = IntegerToString(GetTickCount());
  string line = id+"|PY_CALL|"+json+"\n";
  if(!PyBridgeSendStr(sock, line)) { err="send"; PyBridgeClose(sock); return false; }
  string status, msg, data;
  if(!PyBridgeRead3(sock, status, msg, data)) { err="resp"; PyBridgeClose(sock); return false; }
  PyBridgeClose(sock);
  pyresp = data;
  if(status!="OK") { err=msg; return false; }
  return true;
}

bool PyBridgeArrayCall(const string name,
                       const string host=PYBR_DEFAULT_HOST, const int port=PYBR_DEFAULT_PORT,
                       string &err="")
{
  uint sock=0;
  if(!PyBridgeConnect(host, port, sock)) { err="conn"; return false; }
  string id = IntegerToString(GetTickCount());
  string line = id+"|PY_ARRAY_CALL|"+name+"\n";
  if(!PyBridgeSendStr(sock, line)) { err="send"; PyBridgeClose(sock); return false; }
  string status, msg, data;
  if(!PyBridgeRead3(sock, status, msg, data)) { err="resp"; PyBridgeClose(sock); return false; }
  PyBridgeClose(sock);
  if(status!="OK") { err=msg; return false; }
  return true;
}

bool PyBridgeGetArrayF64(double &out[],
                         const string host=PYBR_DEFAULT_HOST, const int port=PYBR_DEFAULT_PORT,
                         string &err="")
{
  uint sock=0;
  if(!PyBridgeConnect(host, port, sock)) { err="conn"; return false; }
  string id = IntegerToString(GetTickCount());
  uchar empty[]; ArrayResize(empty,0);
  string header = id+"|GET_ARRAY";
  if(!PyBridgeSendFrame(sock, header, empty)) { err="send"; PyBridgeClose(sock); return false; }
  string rh; uchar payload[];
  if(!PyBridgeRecvFrame(sock, rh, payload)) { err="resp"; PyBridgeClose(sock); return false; }
  PyBridgeClose(sock);
  string hp[]; int hn=StringSplit(rh,'|',hp);
  if(hn<6) { err="bad_header"; return false; }
  string dtype = hp[3];
  int out_count = (int)StringToInteger(hp[4]);
  if(dtype!="f64") { err="dtype"; return false; }
  if(out_count<=0) { err="count"; return false; }
  if(!PyBridgeBytesToDoubles(payload, out_count, out)) { err="unpack"; return false; }
  return true;
}

// Convenience: envia array, chama Python, busca resultado (3 conexões)
bool PyBridgeCalcF64(const double &arr[], int count, double &out[], const string func,
                     const string host=PYBR_DEFAULT_HOST, const int port=PYBR_DEFAULT_PORT,
                     string &err="")
{
  if(!PyBridgeSendArrayF64(arr, count, "input", host, port, err)) return false;
  if(!PyBridgeArrayCall(func, host, port, err)) return false;
  if(!PyBridgeGetArrayF64(out, host, port, err)) return false;
  return true;
}

#endif
