//+------------------------------------------------------------------+
//| PyInService.mq5                                                  |
//| PyInService (pyin): serviço TCP exclusivo para Python            |
//| Comandos: PY_CALL / PY_ARRAY_CALL                                |
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

input int    InpPort    = 9091; // porta do PyIn (cliente Python externo)
input int    InpBacklog = 4;
input int    InpSleepMs = 20;
input bool   InpLocalhostOnly = false; // true = 127.0.0.1, false = INADDR_ANY
input bool   InpReuseAddr = true; // SO_REUSEADDR antes do bind
input string InpPyOutHost  = "192.168.64.35,127.0.0.1,host.docker.internal"; // PyOut (Python externo)
input int    InpPyOutPort  = 9100; // porta do PyOut
input int    InpPyOutConnectMs = 2000; // timeout connect PyOut (ms)
input int    InpPyOutSendMs    = 2000; // timeout send PyOut (ms)
input int    InpPyOutRecvMs    = 5000; // timeout recv PyOut (ms)
input int    InpPyOutStepMs    = 50;   // timeout por leitura (ms)
input bool   InpVerboseLogs = true; // logs ligados por padrão

#include "PyInService/socket-library-mt4-mt5.mqh"
#include "PyInService/PyInSockClient.mqh"

string LISTENER_VERSION_SOCKET = "pyin-service-1.0.0";

#import "ws2_32.dll"
int WSAStartup(ushort wVersionRequested, uchar &lpWSAData[]);
int WSACleanup();
#import

#define PYIN_WSA_VER 0x0202
static bool g_wsa_started = false;

bool EnsureWSA()
{
  if(g_wsa_started) return true;
  uchar wsa[400];
  int res = WSAStartup(PYIN_WSA_VER, wsa);
  if(res!=0)
  {
    Print("[PyIn] WSAStartup failed err=", res);
    return false;
  }
  g_wsa_started = true;
  return true;
}

void CleanupWSA()
{
  if(g_wsa_started)
  {
    WSACleanup();
    g_wsa_started = false;
  }
}

void Log(const string txt)
{
  if(InpVerboseLogs) Print("[PyIn] ", txt);
}

ServerSocket *g_server = NULL;
ClientSocket *g_client = NULL;
// cliente python
int g_pySock = PYIN_SOCKET_INVALID;

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


bool SendStr(ClientSocket *sock, const string s)
{
  if(sock==NULL) return false;
  uchar b[]; StringToCharArray(s, b, 0, StringLen(s), CP_UTF8);
  return sock.SendRaw(b, ArraySize(b));
}

void SendResp(ClientSocket *sock, string resp)
{
  SendStr(sock, resp);
}

bool RecvExact(ClientSocket *sock, int len, uchar &out[])
{
  if(sock==NULL || len<=0) { ArrayResize(out,0); return false; }
  ArrayResize(out, len);
  int got=0;
  while(got<len && !IsStopped())
  {
    uchar chunk[];
    int r = sock.RecvRaw(chunk, len-got);
    if(r==0) { Sleep(1); continue; }
    if(r<0) return false;
    ArrayCopy(out, chunk, got, 0, r);
    got += r;
  }
  return got==len;
}

// Retorna: 1=mensagem lida, 0=sem dados, -1=conexao fechada/erro
int RecvMessage(ClientSocket *sock, bool &isFrame, string &out)
{
  isFrame=false; out="";
  if(sock==NULL) return -1;
  uchar firstBuf[];
  int r = sock.RecvRaw(firstBuf, 1);
  if(r==0) return 0;   // sem dados
  if(r<0) return -1;   // erro/fechou
  uchar first = firstBuf[0];

  if(first==0xFF)
  {
    isFrame=true;
    uchar lenbuf[4];
    if(!RecvExact(sock,4,lenbuf)) return -1;
    int hdrLen = (lenbuf[0]<<24)|(lenbuf[1]<<16)|(lenbuf[2]<<8)|lenbuf[3];
    uchar hdr[];
    if(!RecvExact(sock, hdrLen, hdr)) return -1;
    out = CharArrayToString(hdr,0,hdrLen,CP_UTF8);
    if(InpVerboseLogs) Log(StringFormat("Frame header: %s", out));
    return 1;
  }

  // texto
  uchar buf[4096]; int idx=0;
  buf[idx++]=first;
  while(true)
  {
    if(first=='\n') break;
    uchar chBuf[];
    r = sock.RecvRaw(chBuf, 1);
    if(r==0) { Sleep(1); continue; }
    if(r<0) return -1;
    first = chBuf[0];
    buf[idx++]=first;
    if(idx>=4095) break;
    if(first=='\n') break;
  }
  out = CharArrayToString(buf,0,idx,CP_UTF8);
  if(InpVerboseLogs) Log("Recv text: "+out);
  return 1;
}

bool StartServer()
{
  if(!EnsureWSA()) return false;
  if(g_server!=NULL) { delete g_server; g_server=NULL; }
  g_server = new ServerSocket((ushort)InpPort, InpLocalhostOnly, InpBacklog, InpReuseAddr);
  if(g_server==NULL || !g_server.Created())
  {
    int err = (g_server!=NULL ? g_server.GetLastSocketError() : 0);
    Print("[PyIn] Server socket FAILED err=", err, " port=", InpPort);
    return false;
  }
  Log("Socket service listening on "+IntegerToString(InpPort));
  return true;
}

bool ConnectPy()
{
  if(g_pySock!=PYIN_SOCKET_INVALID && PySockIsConnected(g_pySock)) return true;
  // suporta fallback em lista "host1,host2"
  string hosts = InpPyOutHost;
  if(hosts=="") hosts="127.0.0.1";
  string hlist[]; int hn=StringSplit(hosts, ',', hlist);
  if(hn<=0) { ArrayResize(hlist,1); hlist[0]=hosts; hn=1; }

  for(int i=0;i<hn;i++)
  {
    string h = hlist[i]; StringTrimLeft(h); StringTrimRight(h);
    if(h=="") continue;
    string err="";
    if(PySockConnect(g_pySock, h, (uint)InpPyOutPort, InpPyOutConnectMs, InpPyOutSendMs, InpPyOutRecvMs, err))
      return true;
    PySockClose(g_pySock);
  }
  return false;
}

void ClosePy()
{
  PySockClose(g_pySock);
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

// ---- PyOutService frame helpers (0xFF + len + header + payload) ----
bool PySendFrame(ClientSocket *sock, const string header, uchar &payload[])
{
  if(sock==NULL) return false;
  uchar hb[]; StringToCharArray(header, hb, 0, StringLen(header), CP_UTF8);
  int hlen = ArraySize(hb);
  uchar prefix[5];
  prefix[0]=0xFF;
  prefix[1]=(uchar)((hlen>>24)&0xFF);
  prefix[2]=(uchar)((hlen>>16)&0xFF);
  prefix[3]=(uchar)((hlen>>8)&0xFF);
  prefix[4]=(uchar)(hlen&0xFF);
  if(!sock.SendRaw(prefix,5)) return false;
  if(!sock.SendRaw(hb, hlen)) return false;
  int plen = ArraySize(payload);
  if(plen>0 && !sock.SendRaw(payload, plen)) return false;
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

ClientSocket *AcceptClient()
{
  if(g_server==NULL) return NULL;
  return g_server.Accept();
}

void CloseSockets()
{
  if(g_client!=NULL) { delete g_client; g_client=NULL; }
  if(g_server!=NULL) { delete g_server; g_server=NULL; }
  CleanupWSA();
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
    if(g_client==NULL)
    {
      ClientSocket *c = AcceptClient();
      if(c!=NULL)
      {
        g_client = c;
        if(InpVerboseLogs) Log("client connected");
      }
    }
    if(g_client!=NULL)
    {
      string line; bool isFrame=false;
      int rcv = RecvMessage(g_client, isFrame, line);
      if(rcv==0) { Sleep(InpSleepMs); continue; } // sem dados
      if(rcv<0)
      {
        if(InpVerboseLogs) Log("client done (connection closed)");
        delete g_client; g_client=NULL; continue;
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
          else if(htype=="PY_ARRAY_SUBMIT" && hn>=6)
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
                continue;
              }

              if(!ConnectPy()) { SendResp(g_client, "ERROR\npy_conn\n"); continue; }

              string header = line;
              string errp="";
              if(!PySockSendFrame(g_pySock, header, raw, errp))
              {
                SendResp(g_client, "ERROR\npy_send_fail\n"); ClosePy();
                continue;
              }

              string h=""; uchar payload[];
              if(!PySockRecvFrame(g_pySock, h, payload, InpPyOutStepMs, InpPyOutRecvMs, errp))
              {
                SendResp(g_client, "ERROR\npy_noresp\n"); ClosePy();
                continue;
              }

              if(!PySendFrame(g_client, h, payload))
              {
                ClosePy();
                continue;
              }

              if(InpVerboseLogs) Log(StringFormat("resp to %s OK msg=py_array_ack", hid));
            }
          }
          else if(htype=="PY_ARRAY_POLL" && hn>=6)
          {
            if(!ConnectPy()) { SendResp(g_client, "ERROR\npy_conn\n"); continue; }

            uchar empty[]; ArrayResize(empty,0);
            string header = line;
            string errp="";
            if(!PySockSendFrame(g_pySock, header, empty, errp))
            {
              SendResp(g_client, "ERROR\npy_send_fail\n"); ClosePy();
              continue;
            }

            string h=""; uchar payload[];
            if(!PySockRecvFrame(g_pySock, h, payload, InpPyOutStepMs, InpPyOutRecvMs, errp))
            {
              SendResp(g_client, "ERROR\npy_noresp\n"); ClosePy();
              continue;
            }

            if(!PySendFrame(g_client, h, payload))
            {
              ClosePy();
              continue;
            }

            if(InpVerboseLogs) Log(StringFormat("resp to %s OK msg=py_array_poll", hid));
          }
          else if(htype=="PY_ARRAY_CALL" && hn>=6)
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
                continue;
              }

              if(!ConnectPy()) { SendResp(g_client, "ERROR\npy_conn\n"); continue; }

              string header = hid+"|PY_ARRAY_CALL|"+name+"|"+dtype+"|"+IntegerToString(count)+"|"+IntegerToString(raw_len);
              string errp="";
              if(!PySockSendFrame(g_pySock, header, raw, errp))
              {
                SendResp(g_client, "ERROR\npy_send_fail\n"); ClosePy();
                continue;
              }

              string h=""; uchar payload[];
              if(!PySockRecvFrame(g_pySock, h, payload, InpPyOutStepMs, InpPyOutRecvMs, errp))
              {
                SendResp(g_client, "ERROR\npy_noresp\n"); ClosePy();
                continue;
              }

              if(!PySendFrame(g_client, h, payload))
              {
                ClosePy();
                continue;
              }

              if(InpVerboseLogs) Log(StringFormat("resp to %s OK msg=py_array_ok", hid));
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
            g_client.SendRaw(prefix,5);
            g_client.SendRaw(hb, hlen);
            if(raw_len>0) g_client.SendRaw(g_arr_data, raw_len);
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

        if(type=="PING")
        {
          msg="pong "+LISTENER_VERSION_SOCKET;
          ok=true;
        }
        else if(type=="PY_CONNECT")
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
              string errp="";
              if(!PySockSendFrame(g_pySock, header, g_arr_data, errp))
              {
                msg="py_send_fail"; ok=false; ClosePy();
              }
              else
              {
                string h=""; uchar payload[];
                if(!PySockRecvFrame(g_pySock, h, payload, InpPyOutStepMs, InpPyOutRecvMs, errp))
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
        else if(type=="PY_CALL")
        {
          // params[0] = json ou texto a ser enviado ao python server
          if(!ConnectPy()) { msg="py_conn"; ok=false; }
          else
          {
            string payload = (ArraySize(params)>0)?params[0]:"";
            string errp="";
            if(!PySockSendLine(g_pySock, payload+"\n", errp))
            {
              msg="py_send_fail"; ok=false; ClosePy();
            }
            else
            {
            string pyresp;
            if(PySockRecvLine(g_pySock, pyresp, InpPyOutStepMs, InpPyOutRecvMs, errp))
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
          msg="unsupported";
          ok=false;
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
