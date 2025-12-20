//+------------------------------------------------------------------+
//| OficialTelnetServiceSocket.mq5                                   |
//| Serviço TCP: comandos textuais ou frame binário (winsock)        |
//| Texto:  id|TYPE|p1|p2\n                                          |
//| Frame binário (SEND_ARRAY/GET_ARRAY):                            |
//|   0xFF + 4 bytes (len header, big-endian) + header UTF-8         |
//|   header: id|SEND_ARRAY|name|dtype|count|raw_len                  |
//|   depois do header: raw_len bytes de payload                     |
//| GET_ARRAY: serviço envia frame com header e depois raw bytes     |
//| Tipos dtype: f64,f32,i32,i16,u8                                  |
//| Doc completa: docs/PROTOCOL_ARRAY.md                             |
//+------------------------------------------------------------------+
#property service
#property strict

input int    InpPort    = 9090;
input int    InpBacklog = 4;
input int    InpSleepMs = 20;
input string InpPyHost  = "host.docker.internal,127.0.0.1";
input int    InpPyPort  = 9100;
input string InpDefaultSymbol = "EURUSD";
input string InpDefaultTf     = "H1";
input bool   InpVerboseLogs = true; // logs ligados por padrão

#include "OficialTelnetServiceSocket/SocketBridge.mqh"
#include "OficialTelnetServiceSocket/ServiceHandlers.mqh"

string LISTENER_VERSION_SOCKET = "svc-socket-1.1.0";

void Log(const string txt)
{
  if(InpVerboseLogs) Print("[SvcSocket] ", txt);
}

uint g_listen = 0;
uint g_client = 0;
bool g_wsaInit = false;
// cliente python
uint g_pySock = 0;

// armazenamento simples do último array recebido
string g_arr_name="";
string g_arr_dtype="";
int    g_arr_count=0;
uchar  g_arr_data[];

int DTypeSize(const string dt)
{
  if(dt=="f64") return 8;
  if(dt=="f32") return 4;
  if(dt=="i32") return 4;
  if(dt=="i16") return 2;
  if(dt=="u8")  return 1;
  return 0;
}

bool SendStr(uint sock, const string s)
{
  uchar b[]; StringToCharArray(s, b, 0, StringLen(s), CP_UTF8);
  int r = send(sock, b, ArraySize(b), 0);
  if(InpVerboseLogs && r<0) Print("[SvcSocket] send falhou err=", GetLastError());
  return r >= 0;
}

void SendResp(uint sock, string resp)
{
  SendStr(sock, resp);
}

// recebe linha até '\n' (exclui) ou falha
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

bool RecvExact(uint sock, int len, uchar &out[])
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

// Lê uma mensagem: se começa com 0xFF, trata como frame binário; senão, linha texto até '\n'
bool RecvMessage(uint sock, bool &isFrame, string &out)
{
  isFrame=false; out="";
  uchar first[1];
  int r=recv(sock, first, 1, 0);
  if(r<=0) return false;

  if(first[0]==0xFF)
  {
    isFrame=true;
    uchar lenbuf[4];
    if(!RecvExact(sock,4,lenbuf)) return false;
    int hdrLen = (lenbuf[0]<<24)|(lenbuf[1]<<16)|(lenbuf[2]<<8)|lenbuf[3];
    uchar hdr[];
    if(!RecvExact(sock, hdrLen, hdr)) return false;
    out = CharArrayToString(hdr,0,hdrLen,CP_UTF8);
    if(InpVerboseLogs) Log(StringFormat("Frame header: %s", out));
    return true;
  }

  // texto
  uchar buf[4096]; int idx=0;
  buf[idx++]=first[0];
  while(true)
  {
    if(first[0]=='\n') break;
    r=recv(sock, first, 1, 0);
    if(r<=0) break;
    buf[idx++]=first[0];
    if(idx>=4095) break;
    if(first[0]=='\n') break;
  }
  out = CharArrayToString(buf,0,idx,CP_UTF8);
  if(InpVerboseLogs) Log("Recv text: "+out);
  return true;
}

bool StartServer()
{
  if(!EnsureWSA()) return false;
  g_listen = socket(AF_INET, SOCK_STREAM, IPPROTO_TCP);
  if(g_listen==0) return false;
  uchar sa[]; MakeSockAddr(sa, (ushort)InpPort);
  if(bind(g_listen, sa, ArraySize(sa))!=0) return false;
  if(!SetNonBlocking(g_listen)) return false;
  if(listen(g_listen, InpBacklog)!=0) return false;
  Log("Socket service listening on "+IntegerToString(InpPort));
  return true;
}

bool EnsureWSA()
{
  if(g_wsaInit) return true;
  uchar wsa[400];
  if(WSAStartup(0x202, wsa)!=0) return false;
  g_wsaInit=true;
  return true;
}

bool ConnectPy()
{
  if(g_pySock!=0) return true;
  // suporta fallback em lista "host1,host2"
  string hosts = InpPyHost;
  if(hosts=="") hosts="127.0.0.1";
  string hlist[]; int hn=StringSplit(hosts, ',', hlist);
  if(hn<=0) { ArrayResize(hlist,1); hlist[0]=hosts; hn=1; }

  for(int i=0;i<hn;i++)
  {
    string h = hlist[i]; StringTrimLeft(h); StringTrimRight(h);
    if(h=="") continue;
    g_pySock = socket(AF_INET, SOCK_STREAM, IPPROTO_TCP);
    if(g_pySock==0) return false;
    uint ipHost=0x7F000001; // 127.0.0.1 default
    if(h!="127.0.0.1")
    {
      int a,b,c,d;
      string partsIP[];
      if(StringSplit(h,'.',partsIP)==4)
      {
        a=(int)StringToInteger(partsIP[0]); b=(int)StringToInteger(partsIP[1]);
        c=(int)StringToInteger(partsIP[2]); d=(int)StringToInteger(partsIP[3]);
        ipHost = ((uint)a<<24)|((uint)b<<16)|((uint)c<<8)|(uint)d;
      }
    }
    uchar sa[]; MakeSockAddr(sa, (ushort)InpPyPort, ipHost);
    if(connect(g_pySock, sa, ArraySize(sa))==0) return true;
    closesocket(g_pySock); g_pySock=0;
  }
  return false;
}

void ClosePy()
{
  if(g_pySock) { closesocket(g_pySock); g_pySock=0; }
}

bool ShouldLogCheck(const string type)
{
  if(type=="PING" || type=="DEBUG_MSG" || type=="PY_CALL") return false;
  if(type=="GLOBAL_GET" || type=="GLOBAL_LIST") return false;
  if(type=="LIST_CHARTS" || type=="WINDOW_FIND" || type=="LIST_INPUTS") return false;
  if(type=="IND_TOTAL" || type=="IND_NAME" || type=="IND_HANDLE") return false;
  if(type=="SNAPSHOT_LIST" || type=="DROP_INFO") return false;
  if(type=="TRADE_LIST" || type=="OBJ_LIST") return false;
  return true;
}

bool ShouldReturnLogs(const string type)
{
  return (type=="ATTACH_IND_FULL" || type=="ATTACH_EA_FULL" ||
          type=="APPLY_TPL" || type=="SAVE_TPL" || type=="RUN_SCRIPT" ||
          type=="SNAPSHOT_APPLY" || type=="SNAPSHOT_SAVE");
}

bool LogLineMatches(string line, const string filter)
{
  string l = line; StringToLower(l);
  string f = filter; StringToLower(f);
  if(f!="" && StringFind(l, f)>=0) return true;
  if(StringFind(l, "cannot load")>=0) return true;
  if(StringFind(l, "init failed")>=0) return true;
  if(StringFind(l, "failed")>=0) return true;
  if(StringFind(l, "error")>=0) return true;
  return false;
}

void AppendLogLines(string &lines[], string &data[], int maxLines, const string filter)
{
  int n = ArraySize(lines);
  if(n<=0) return;
  int added = 0;
  for(int i=n-1;i>=0 && added<maxLines;i--)
  {
    if(!LogLineMatches(lines[i], filter)) continue;
    int d = ArraySize(data);
    ArrayResize(data, d+1);
    data[d] = "log: " + lines[i];
    added++;
  }
}

// ---- Python bridge frame helpers (0xFF + len + header + payload) ----
bool PySendFrame(uint sock, const string header, uchar &payload[])
{
  uchar hb[]; StringToCharArray(header, hb, 0, StringLen(header), CP_UTF8);
  int hlen = ArraySize(hb);
  uchar prefix[5];
  prefix[0]=0xFF;
  prefix[1]=(uchar)((hlen>>24)&0xFF);
  prefix[2]=(uchar)((hlen>>16)&0xFF);
  prefix[3]=(uchar)((hlen>>8)&0xFF);
  prefix[4]=(uchar)(hlen&0xFF);
  if(send(sock, prefix,5,0)<0) return false;
  if(send(sock, hb, hlen,0)<0) return false;
  int plen = ArraySize(payload);
  if(plen>0 && send(sock, payload, plen,0)<0) return false;
  return true;
}

bool PyRecvFrame(uint sock, string &header, uchar &payload[])
{
  header=""; ArrayResize(payload,0);
  uchar first[1];
  int r=recv(sock, first, 1, 0);
  if(r<=0) return false;
  if(first[0]!=0xFF) return false;
  uchar lenbuf[4];
  if(!RecvExact(sock, 4, lenbuf)) return false;
  int hlen = (lenbuf[0]<<24)|(lenbuf[1]<<16)|(lenbuf[2]<<8)|lenbuf[3];
  uchar hb[];
  if(!RecvExact(sock, hlen, hb)) return false;
  header = CharArrayToString(hb,0,hlen,CP_UTF8);
  string parts[]; int n=StringSplit(header,'|',parts);
  if(n>=6)
  {
    int raw_len = (int)StringToInteger(parts[5]);
    if(raw_len>0)
    {
      if(!RecvExact(sock, raw_len, payload)) return false;
    }
  }
  return true;
}
string CmdLogFilter(const string type, string &params[])
{
  if(type=="ATTACH_EA_FULL" && ArraySize(params)>=3) return params[2];
  if(type=="ATTACH_IND_FULL" && ArraySize(params)>=3) return params[2];
  if(type=="APPLY_TPL" && ArraySize(params)>=3) return params[2];
  if(type=="SAVE_TPL" && ArraySize(params)>=3) return params[2];
  if(type=="SNAPSHOT_APPLY" && ArraySize(params)>=1) return params[0];
  if(type=="SNAPSHOT_SAVE" && ArraySize(params)>=1) return params[0];
  if(type=="RUN_SCRIPT" && ArraySize(params)>=1) return params[0];
  return "";
}

string BaseNameNoExt(const string s)
{
  string t=s;
  StringReplace(t, "/", "\\");
  int last=-1;
  int pos=StringFind(t, "\\");
  while(pos>=0)
  {
    last=pos;
    pos=StringFind(t, "\\", pos+1);
  }
  if(last>=0) t=StringSubstr(t, last+1);
  if(StringLen(t)>4)
  {
    string tail=StringSubstr(t, StringLen(t)-4);
    if(tail==".ex5" || tail==".mq5" || tail==".tpl") t=StringSubstr(t,0,StringLen(t)-4);
  }
  return t;
}

string FindErrorInLines(string &lines[], const string filter)
{
  string f=filter; StringToLower(f);
  for(int i=ArraySize(lines)-1;i>=0;i--)
  {
    string l=lines[i]; string ll=l; StringToLower(ll);
    if(f!="" && StringFind(ll, f)<0) continue;
    if(StringFind(ll, "cannot load")>=0 || StringFind(ll, "init failed")>=0 || StringFind(ll, "failed")>=0 || StringFind(ll, "error")>=0)
      return lines[i];
  }
  return "";
}

uint AcceptClient()
{
  uchar sa[32]; int len=32;
  uint c = accept(g_listen, sa, len);
  // ignore invalid sockets (accept failure)
  if((int)c==-1 || c==0) return 0;
  // cliente permanece em modo bloqueante para evitar WSAEWOULDBLOCK em leitura imediata
  return c;
}

void CloseSockets()
{
  if(g_client) { closesocket(g_client); g_client=0; }
  if(g_listen) { closesocket(g_listen); g_listen=0; }
  if(g_wsaInit) { WSACleanup(); g_wsaInit=false; }
}

int OnStart()
{
  if(!StartServer())
  {
    Print("Socket service failed on port ", InpPort);
    CloseSockets(); return(INIT_FAILED);
  }

  while(!IsStopped())
  {
    if(g_client==0)
    {
      g_client = AcceptClient();
      if(g_client!=0 && InpVerboseLogs) Log("client connected");
    }
    if(g_client!=0)
    {
      string line; bool isFrame=false;
      if(!RecvMessage(g_client, isFrame, line))
      {
        // loga apenas uma vez por conexão
        if(InpVerboseLogs) Log("client done (connection closed)");
        closesocket(g_client); g_client=0; continue;
      }

      if(isFrame)
      {
        string hparts[]; int hn=StringSplit(line,'|',hparts);
        if(hn>=2)
        {
          string hid=hparts[0]; string htype=hparts[1];

          if(htype=="SEND_ARRAY" && hn>=6)
          {
            string name=hparts[2]; string dtype=hparts[3];
            int count=(int)StringToInteger(hparts[4]);
            int raw_len=(int)StringToInteger(hparts[5]);
            int sz=DTypeSize(dtype);
            if(sz<=0 || raw_len!=count*sz)
            {
              SendResp(g_client, "ERROR\nsize\n");
            }
            else
            {
              uchar raw[];
              if(!RecvExact(g_client, raw_len, raw))
              {
                SendResp(g_client, "ERROR\nrecv_payload\n");
                continue; // mantém conexão viva
              }
              ArrayCopy(g_arr_data, raw);
              g_arr_name=name; g_arr_dtype=dtype; g_arr_count=count;
              SendResp(g_client, "OK\nstored\n");
            }
          }
          else if(htype=="GET_ARRAY")
          {
            int sz=DTypeSize(g_arr_dtype);
            int raw_len = sz*g_arr_count;
            string header = hid+"|GET_ARRAY|"+g_arr_name+"|"+g_arr_dtype+"|"+IntegerToString(g_arr_count)+"|"+IntegerToString(raw_len);
            uchar hb[]; StringToCharArray(header,hb,0,StringLen(header),CP_UTF8);
            int hlen=ArraySize(hb);
            uchar prefix[5];
            prefix[0]=0xFF;
            prefix[1]=(uchar)((hlen>>24)&0xFF);
            prefix[2]=(uchar)((hlen>>16)&0xFF);
            prefix[3]=(uchar)((hlen>>8)&0xFF);
            prefix[4]=(uchar)(hlen&0xFF);
            send(g_client, prefix,5,0);
            send(g_client, hb, hlen,0);
            if(raw_len>0) send(g_client, g_arr_data, raw_len,0);
          }
          else
          {
            SendResp(g_client, "ERROR\nunknown\n");
          }
        }
      }
      else
      {
        StringReplace(line, "\r", ""); StringReplace(line, "\n", "");
        string parts[]; int n=StringSplit(line, '|', parts);
        if(n>=2)
      {
        string id=parts[0]; string type=parts[1];
        string params[]; ArrayResize(params, MathMax(0,n-2));
        for(int i=2;i<n;i++) params[i-2]=parts[i];
        string data[]; string msg=""; bool ok=false;

          if(type=="PY_CALL" || type=="PY_ARRAY_CALL" || type=="PY_CONNECT" || type=="PY_DISCONNECT")
          {
            if(type=="PY_CONNECT")
            {
              if(ConnectPy()) { msg="py_connected"; ok=true; }
              else { msg="py_conn_fail"; ok=false; }
            }
            else if(type=="PY_DISCONNECT")
            {
              ClosePy(); msg="py_disconnected"; ok=true;
            }
            else if(type=="PY_ARRAY_CALL")
            {
              if(!ConnectPy()) { msg="py_conn"; ok=false; }
              else
              {
                string name = (ArraySize(params)>0 && params[0]!="") ? params[0] : g_arr_name;
                string dtype = g_arr_dtype;
                int count = g_arr_count;
                int raw_len = ArraySize(g_arr_data);
                if(raw_len<=0 || count<=0)
                {
                  msg="no_array"; ok=false;
                }
                else
                {
                  string header = id+"|PY_ARRAY_CALL|"+name+"|"+dtype+"|"+IntegerToString(count)+"|"+IntegerToString(raw_len);
                  if(!PySendFrame(g_pySock, header, g_arr_data))
                  {
                    msg="py_send_fail"; ok=false; ClosePy();
                  }
                  else
                  {
                    string h=""; uchar payload[];
                    if(!PyRecvFrame(g_pySock, h, payload))
                    {
                      msg="py_noresp"; ok=false; ClosePy();
                    }
                    else
                    {
                      string hp[]; int hn=StringSplit(h,'|',hp);
                      if(hn>=6 && hp[1]=="PY_ARRAY_RESP")
                      {
                        g_arr_name=hp[2];
                        g_arr_dtype=hp[3];
                        g_arr_count=(int)StringToInteger(hp[4]);
                        ArrayCopy(g_arr_data, payload);
                        msg="py_array_ok";
                        ArrayResize(data,1);
                        data[0]=StringFormat("name=%s dtype=%s count=%d", g_arr_name, g_arr_dtype, g_arr_count);
                        ok=true;
                      }
                      else
                      {
                        msg="py_bad_resp"; ok=false;
                      }
                    }
                  }
                }
              }
            }
            else
            {
              // params[0] = json ou texto a ser enviado ao python server
              if(!ConnectPy()) { msg="py_conn"; ok=false; }
              else
              {
                string payload = (ArraySize(params)>0)?params[0]:"";
                SendStr(g_pySock, payload+"\n");
                string pyresp;
                if(RecvLine(g_pySock, pyresp))
                {
                  ArrayResize(data,1); data[0]=pyresp;
                  msg="py_ok"; ok=true;
                  if(StringFind(pyresp, "\"ok\":false")>=0) { msg="py_error"; ok=false; }
                }
                else
                {
                  msg="py_noresp"; ok=false; ClosePy();
                }
              }
            }
          }
        else
        {
          bool doLog = ShouldLogCheck(type);
          if(doLog) LogCaptureBegin();
          ok=Dispatch(type, params, msg, data);
          if(doLog)
          {
            string lines[];
            ReadLogLines(lines);
            string filter = BaseNameNoExt(CmdLogFilter(type, params));
            string err = FindErrorInLines(lines, filter);
            if(err=="" && (type=="ATTACH_EA_FULL" || type=="ATTACH_IND_FULL" || type=="APPLY_TPL"))
              err = FindErrorInLines(lines, "");
            if(err!="")
            {
              if(ok)
              {
                ok=false;
                msg="mt5_error: "+err;
              }
              else
              {
                int n=ArraySize(data);
                ArrayResize(data, n+1);
                data[n]="mt5_error: "+err;
              }
            }
            if(ShouldReturnLogs(type))
            {
              AppendLogLines(lines, data, 40, filter);
            }
          }
        }

        string resp = (ok?"OK":"ERROR") + "\n" + msg + "\n";
        for(int i=0;i<ArraySize(data);i++) resp += data[i] + "\n";
        SendResp(g_client, resp);
        if(InpVerboseLogs) Log(StringFormat("resp to %s %s msg=%s", id, (ok?"OK":"ERROR"), msg));
      }
    }
  }
    Sleep(InpSleepMs);
  }
  CloseSockets();
  ClosePy();
  return 0;
}
//+------------------------------------------------------------------+
