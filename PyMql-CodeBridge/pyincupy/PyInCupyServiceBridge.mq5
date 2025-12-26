//+------------------------------------------------------------------+
//| PyInCupyServiceBridge.mq5                                                  |
//| PyInCupyServiceBridge: serviço TCP bridge para PyOut CuPy            |
//| Comandos: PING / SIM / PY_CALL / PY_ARRAY_CALL                                |
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

input int    InpPort    = 9091; // porta do PyInService (MT5) - clientes MQL/Python conectam aqui
input int    InpBacklog = 4;
input int    InpSleepMs = 20;
input bool   InpLocalhostOnly = false; // true = 127.0.0.1, false = INADDR_ANY
input bool   InpReuseAddr = true; // SO_REUSEADDR antes do bind
input string InpPyOutHost  = "host.docker.internal,127.0.0.1"; // hosts do PyOut (Python). Evite IP fixo do WSL.
input int    InpPyOutPort  = 9200; // porta do PyOut (Python server)
input int    InpPyOutConnectMs = 3000; // timeout connect PyOut (ms)
input int    InpPyOutSendMs    = 3000; // timeout send PyOut (ms)
input int    InpPyOutRecvMs    = 30000; // timeout recv PyOut (ms)
input int    InpPyOutStepMs    = 100;   // timeout por leitura (ms)
input int    InpPyPingMs       = 5000;  // ping keepalive (0=desliga)
input bool   InpVerboseLogs = true; // logs ligados por padrão

// ---- Embedded socket library
// *******************************************************************************
// Socket library. NOT FULLY TESTED, to put it mildly.
//
// Features:
// 
//   * Both client and server sockets
//   * Both send and receive
//   * Both MT4 and MT5 (32-bit and 64-bit)
//
// The support for both 32-bit and 64-bit MT5 involves some horrible steps
// because MT4/5 does not have an integer data type whose size varies
// depending on the platform; no equivalent to the Win32 INT_PTR etc.
// As a result, it's necessary to have two versions of most of the Winsock
// DLL imports, involving a couple of horrible tweaks, plus two paths of 
// execution for 32/64-bit. It's also necessary to handle the Winsock hostent
// structure differently.
//
// A ClientSocket() connection to a server can either be to a port on
// localhost, or to a port on a remote hostname/IP address, using different
// constructors. After creating ClientSocket(), and periodially thereafter,
// you should check IsSocketConnected(). If it returns false, then you
// need to destroy that instance of the ClientSocket() class and create a new one.
//
// The ClientSocket() has simple Send() and Receive() members. The latter can
// either deliver any raw data sitting on the socket since the last call
// to Receive(), or you an specify a message terminator (such as \r\n), in which
// case the function will only return you complete messages, once available.
// You'll typically want to call Receive() from OnTimer().
//
// A ServerSocket() which waits for client connections is given a port number
// to listen on, and a boolean parameter indicating whether it should
// accept connections from localhost only, or from any machine. After creating
// the instance of ServerSocket(), you should check the Created() function to
// make sure that the initialisation worked. The main possible reason for
// failure is that something else is already listening on your chosen port.
// Note that if your EA terminates without deleting/releasing an instance
// of ServerSocket(), then the port will not be released until you
// shut down MT4/5. You need to make very sure that destroy instances
// of ServerSocket(), e.g. in OnDeinit().
//
// You accept connections from pending clients by calling Accept(). You will
// usually want to do this in OnTimer(). What you get back is either NULL, if
// there is no pending connection, or an instance of ClientSocket() which you
// can then use to communicate with the client.
// 
// *******************************************************************************

#property strict


// -------------------------------------------------------------
// WinInet constants and structures
// -------------------------------------------------------------

#define SOCKET_HANDLE32       uint
#define SOCKET_HANDLE64       ulong
#define AF_INET               2
#define SOCK_STREAM           1
#define IPPROTO_TCP           6
#define INVALID_SOCKET32      0xFFFFFFFF
#define INVALID_SOCKET64      0xFFFFFFFFFFFFFFFF
#define SOCKET_ERROR          -1
#define INADDR_NONE           0xFFFFFFFF
#define FIONBIO               0x8004667E
#define WSAWOULDBLOCK         10035
#define SOL_SOCKET            0xFFFF
#define SO_REUSEADDR          0x0004

struct sockaddr {
   short family;
   ushort port;
   uint address;
   ulong ignore;
};

// -------------------------------------------------------------
// DLL imports
// -------------------------------------------------------------

#import "ws2_32.dll"
   // Imports for 32-bit environment
   SOCKET_HANDLE32 socket(int, int, int);
   int connect(SOCKET_HANDLE32, sockaddr&, int);
   int closesocket(SOCKET_HANDLE32);
   int send(SOCKET_HANDLE32, uchar&[],int,int);
   int recv(SOCKET_HANDLE32, uchar&[], int, int);
   int ioctlsocket(SOCKET_HANDLE32, uint, uint&);
   int bind(SOCKET_HANDLE32, sockaddr&, int);
   int listen(SOCKET_HANDLE32, int);
   SOCKET_HANDLE32 accept(SOCKET_HANDLE32, int, int);
   int setsockopt(SOCKET_HANDLE32, int, int, uchar&[], int);
   
   // Imports for 64-bit environment
   SOCKET_HANDLE64 socket(int, int, uint);
   int connect(SOCKET_HANDLE64, sockaddr&, int);
   int closesocket(SOCKET_HANDLE64);
   int send(SOCKET_HANDLE64, uchar&[], int, int);
   int recv(SOCKET_HANDLE64, uchar&[], int, int);
   int ioctlsocket(SOCKET_HANDLE64, uint, uint&);
   int bind(SOCKET_HANDLE64, sockaddr&, int);
   int listen(SOCKET_HANDLE64, int);
   SOCKET_HANDLE64 accept(SOCKET_HANDLE64, int, int);
   int setsockopt(SOCKET_HANDLE64, int, int, uchar&[], int);

   // Neutral; no difference between 32-bit and 64-bit
   uint inet_addr(uchar&[]);
   uint gethostbyname(uchar&[]);
   ulong gethostbyname(char&[]);
   int WSAGetLastError();
   uint htonl(uint);
   ushort htons(ushort);
#import

// For navigating the hostent structure, with indescribably horrible variation
// between 32-bit and 64-bit
#import "kernel32.dll"
   void RtlMoveMemory(uint&, uint, int);
   void RtlMoveMemory(ushort&, uint, int);
   void RtlMoveMemory(ulong&, ulong, int);
   void RtlMoveMemory(ushort&, ulong, int);
#import


// -------------------------------------------------------------
// Client socket class
// -------------------------------------------------------------

class ClientSocket
{
   private:
      // Need different socket handles for 32-bit and 64-bit environments
      SOCKET_HANDLE32 mSocket32;
      SOCKET_HANDLE64 mSocket64;
      
      // Other state variables
      bool mConnected;
      int mLastWSAError;
      string mPendingReceiveData;
                    
   public:
      ClientSocket(ushort localport);
      ClientSocket(string HostnameOrIPAddress, ushort localport);

      ClientSocket(SOCKET_HANDLE32 clientsocket32);
      ClientSocket(SOCKET_HANDLE64 clientsocket64);

      ~ClientSocket();
      bool Send(string strMsg);
      bool SendRaw(uchar &buf[], int len);
      int  RecvRaw(uchar &buf[], int maxlen);
      string Receive(string MessageSeparator = "");
      
      bool IsSocketConnected() {return mConnected;}
      int GetLastSocketError() {return mLastWSAError;}
};


// -------------------------------------------------------------
// Constructor for a simple connection to 127.0.0.1
// -------------------------------------------------------------

ClientSocket::ClientSocket(ushort localport)
{
   // Need to create either a 32-bit or 64-bit socket handle
   mConnected = false;
   mLastWSAError = 0;
   if (TerminalInfoInteger(TERMINAL_X64)) {
      uint proto = IPPROTO_TCP;
      mSocket64 = socket(AF_INET, SOCK_STREAM, proto);
      if (mSocket64 == INVALID_SOCKET64) {
         mLastWSAError = WSAGetLastError();
         return;
      }
   } else {
      int proto = IPPROTO_TCP;
      mSocket32 = socket(AF_INET, SOCK_STREAM, proto);
      if (mSocket32 == INVALID_SOCKET32) {
         mLastWSAError = WSAGetLastError();
         return;
      }
   }
   
   // Fixed definition for connecting to 127.0.0.1, with variable port
   sockaddr server;
   server.family = AF_INET;
   server.port = htons(localport);
   server.address = 0x100007f; // 127.0.0.1
   
   // connect() call has to differ between 32-bit and 64-bit
   int res;
   if (TerminalInfoInteger(TERMINAL_X64)) {
      res = connect(mSocket64, server, sizeof(sockaddr));
   } else {
      res = connect(mSocket32, server, sizeof(sockaddr));
   }
   if (res == SOCKET_ERROR) {
      // Oops
      mLastWSAError = WSAGetLastError();
   } else {
      mConnected = true;   
   }
}

// -------------------------------------------------------------
// Constructor for connection to a hostname or IP address
// -------------------------------------------------------------

ClientSocket::ClientSocket(string HostnameOrIPAddress, ushort remoteport)
{
   // Need to create either a 32-bit or 64-bit socket handle
   mConnected = false;
   mLastWSAError = 0;
   if (TerminalInfoInteger(TERMINAL_X64)) {
      uint proto = IPPROTO_TCP;
      mSocket64 = socket(AF_INET, SOCK_STREAM, proto);
      if (mSocket64 == INVALID_SOCKET64) {
         mLastWSAError = WSAGetLastError();
         return;
      }
   } else {
      int proto = IPPROTO_TCP;
      mSocket32 = socket(AF_INET, SOCK_STREAM, proto);
      if (mSocket32 == INVALID_SOCKET32) {
         mLastWSAError = WSAGetLastError();
         return;
      }
   }

   // Is it an IP address?
   uchar arrName[];
   StringToCharArray(HostnameOrIPAddress, arrName);
   ArrayResize(arrName, ArraySize(arrName) + 1);
   uint addr = inet_addr(arrName);
   if (addr == INADDR_NONE) {
      // Not an IP address. Need to look up the name
      // .......................................................................................
      // Unbelievably horrible handling of the hostent structure depending on whether
      // we're in 32-bit or 64-bit, with different-length memory pointers...
      if (TerminalInfoInteger(TERMINAL_X64)) {
         char arrName64[];
         ArrayResize(arrName64, ArraySize(arrName));
         for (int i = 0; i < ArraySize(arrName); i++) arrName64[i] = (char)arrName[i];
         ulong nres = gethostbyname(arrName64);
         if (nres == 0) {
            // Name lookup failed
            return;
         } else {
            // Need to navigate the hostent structure. Very, very ugly...
            ushort addrlen;
            RtlMoveMemory(addrlen, nres + 18, 2);
            if (addrlen == 0) {
               // No addresses associated with name
               return;
            } else {
               ulong ptr1, ptr2, ptr3;
               RtlMoveMemory(ptr1, nres + 24, 8);
               RtlMoveMemory(ptr2, ptr1, 8);
               RtlMoveMemory(ptr3, ptr2, 4);
               addr = (uint)ptr3;
            }
         }
      } else {
         uint nres = gethostbyname(arrName);
         if (nres == 0) {
            // Name lookup failed
            return;
         } else {
            // Need to navigate the hostent structure. Very, very ugly...
            ushort addrlen;
            RtlMoveMemory(addrlen, nres + 10, 2);
            if (addrlen == 0) {
               // No addresses associated with name
               return;
            } else {
               uint ptr1, ptr2;
               RtlMoveMemory(ptr1, nres + 12, 4);
               RtlMoveMemory(ptr2, ptr1, 4);
               RtlMoveMemory(addr, ptr2, 4);
            }
         }
      }
   } else {
      // The HostnameOrIPAddress parameter is an IP address
   }

   // Fill in the address and port into a sockaddr_in structure
   sockaddr server;
   server.family = AF_INET;
   server.port = htons(remoteport);
   server.address = addr;

   // connect() call has to differ between 32-bit and 64-bit
   int res;
   if (TerminalInfoInteger(TERMINAL_X64)) {
      res = connect(mSocket64, server, sizeof(sockaddr));
   } else {
      res = connect(mSocket32, server, sizeof(sockaddr));
   }
   if (res == SOCKET_ERROR) {
      // Oops
      mLastWSAError = WSAGetLastError();
   } else {
      mConnected = true;   
   }
}

// -------------------------------------------------------------
// Constructor for client sockets from server sockets
// -------------------------------------------------------------

ClientSocket::ClientSocket(SOCKET_HANDLE32 clientsocket32)
{
   // Need to create either a 32-bit or 64-bit socket handle
   mConnected = true;
   mSocket32 = clientsocket32;
}

ClientSocket::ClientSocket(SOCKET_HANDLE64 clientsocket64)
{
   // Need to create either a 32-bit or 64-bit socket handle
   mConnected = true;
   mSocket64 = clientsocket64;
}


// -------------------------------------------------------------
// Destructor. Close the socket if created
// -------------------------------------------------------------

ClientSocket::~ClientSocket()
{
   if (TerminalInfoInteger(TERMINAL_X64)) {
      if (mSocket64 != 0)  closesocket(mSocket64);
   } else {
      if (mSocket32 != 0)  closesocket(mSocket32);
   }   
}

// -------------------------------------------------------------
// Simple send function
// -------------------------------------------------------------

bool ClientSocket::Send(string strMsg)
{
   if (!mConnected) return false;
   
   bool bRetval = true;
   uchar arr[];
   StringToCharArray(strMsg, arr);
   int szToSend = StringLen(strMsg);
   
   while (szToSend > 0) {
      int res;
      if (TerminalInfoInteger(TERMINAL_X64)) {
         res = send(mSocket64, arr, szToSend, 0);
      } else {
         res = send(mSocket32, arr, szToSend, 0);
      }
      
      if (res == SOCKET_ERROR || res == 0) {
         szToSend = -1;
         bRetval = false;
         mConnected = false;
      } else {
         szToSend -= res;
         if (szToSend > 0) ArrayCopy(arr, arr, 0, res, szToSend);
      }
   }

   return bRetval;
}

// -------------------------------------------------------------
// Raw send (bytes)
// -------------------------------------------------------------

bool ClientSocket::SendRaw(uchar &buf[], int len)
{
   if (!mConnected) return false;
   if (len <= 0) return true;

   int remaining = len;
   int offset = 0;
   while (remaining > 0) {
      int res;
      if (offset == 0) {
         if (TerminalInfoInteger(TERMINAL_X64)) {
            res = send(mSocket64, buf, remaining, 0);
         } else {
            res = send(mSocket32, buf, remaining, 0);
         }
      } else {
         uchar tmp[];
         ArrayResize(tmp, remaining);
         ArrayCopy(tmp, buf, 0, offset, remaining);
         if (TerminalInfoInteger(TERMINAL_X64)) {
            res = send(mSocket64, tmp, remaining, 0);
         } else {
            res = send(mSocket32, tmp, remaining, 0);
         }
      }

      if (res == SOCKET_ERROR || res == 0) {
         mConnected = false;
         return false;
      }
      remaining -= res;
      offset += res;
   }
   return true;
}

// -------------------------------------------------------------
// Raw receive (bytes) - non-blocking
// Returns: >0 bytes read, 0 = no data, -1 = error/closed
// -------------------------------------------------------------

int ClientSocket::RecvRaw(uchar &buf[], int maxlen)
{
   if (!mConnected) return -1;
   if (maxlen <= 0) { ArrayResize(buf, 0); return 0; }

   ArrayResize(buf, maxlen);
   uint nonblock = 1;

   int res;
   if (TerminalInfoInteger(TERMINAL_X64)) {
      ioctlsocket(mSocket64, FIONBIO, nonblock);
      res = recv(mSocket64, buf, maxlen, 0);
   } else {
      ioctlsocket(mSocket32, FIONBIO, nonblock);
      res = recv(mSocket32, buf, maxlen, 0);
   }

   if (res > 0) {
      ArrayResize(buf, res);
      return res;
   }
   if (res == 0) {
      mConnected = false;
      ArrayResize(buf, 0);
      return -1;
   }

   int err = WSAGetLastError();
   if (err != WSAWOULDBLOCK) {
      mConnected = false;
      ArrayResize(buf, 0);
      return -1;
   }

   ArrayResize(buf, 0);
   return 0;
}

// -------------------------------------------------------------
// Simple receive function. Without a message separator,
// it simply returns all the data sitting on the socket.
// With a separator, it stores up incoming data until
// it sees the separator, and then returns the text minus
// the separator.
// Returns a blank string once no (more) data is waiting
// for collection.
// -------------------------------------------------------------

string ClientSocket::Receive(string MessageSeparator = "")
{
   if (!mConnected) return "";
   
   string strRetval = "";
   
   uchar arrBuffer[];
   int BufferSize = 10000;
   ArrayResize(arrBuffer, BufferSize);

   uint nonblock = 1;
   if (TerminalInfoInteger(TERMINAL_X64)) {
      ioctlsocket(mSocket64, FIONBIO, nonblock);
 
      int res = 1;
      while (res > 0) {
         res = recv(mSocket64, arrBuffer, BufferSize, 0);
         if (res > 0) {
            StringAdd(mPendingReceiveData, CharArrayToString(arrBuffer, 0, res));
         } else {
            if (WSAGetLastError() != WSAWOULDBLOCK) mConnected = false;
         }
      }
   } else {
      ioctlsocket(mSocket32, FIONBIO, nonblock);

      int res = 1;
      while (res > 0) {
         res = recv(mSocket32, arrBuffer, BufferSize, 0);
         if (res > 0) {
            StringAdd(mPendingReceiveData, CharArrayToString(arrBuffer, 0, res));
         } else {
            if (WSAGetLastError() != WSAWOULDBLOCK) mConnected = false;
         }
      }
   }   
   
   if (mPendingReceiveData == "") {
      // No data
      
   } else if (MessageSeparator == "") {
      // No requested message separator to wait for
      strRetval = mPendingReceiveData;
      mPendingReceiveData = "";
   
   } else {
      int idx = StringFind(mPendingReceiveData, MessageSeparator);
      if (idx >= 0) {
         while (idx == 0) {
            mPendingReceiveData = StringSubstr(mPendingReceiveData, idx + StringLen(MessageSeparator));
            idx = StringFind(mPendingReceiveData, MessageSeparator);
         }
         
         strRetval = StringSubstr(mPendingReceiveData, 0, idx);
         mPendingReceiveData = StringSubstr(mPendingReceiveData, idx + StringLen(MessageSeparator));
      }
   }
   
   return strRetval;
}

// -------------------------------------------------------------
// Server socket class
// -------------------------------------------------------------

class ServerSocket
{
   private:
      SOCKET_HANDLE32 mSocket32;
      SOCKET_HANDLE64 mSocket64;

      // Other state variables
      bool mCreated;
      int mLastWSAError;
              
   public:
      ServerSocket(ushort ServerPort, bool ForLocalhostOnly, int Backlog=10, bool ReuseAddr=false);
      ~ServerSocket();
      
      ClientSocket * Accept();

      bool Created() {return mCreated;}
      int GetLastSocketError() {return mLastWSAError;}
};


// -------------------------------------------------------------
// Constructor for server socket
// -------------------------------------------------------------

ServerSocket::ServerSocket(ushort ServerPort, bool ForLocalhostOnly, int Backlog, bool ReuseAddr)
{
   // Create socket and make it non-blocking
   mCreated = false;
   mLastWSAError = 0;
   if (TerminalInfoInteger(TERMINAL_X64)) {
      uint proto = IPPROTO_TCP;
      mSocket64 = socket(AF_INET, SOCK_STREAM, proto);
      if (mSocket64 == INVALID_SOCKET64) {
         mLastWSAError = WSAGetLastError();
         return;
      }
      uint nonblock = 1;
      ioctlsocket(mSocket64, FIONBIO, nonblock);

   } else {
      int proto = IPPROTO_TCP;
      mSocket32 = socket(AF_INET, SOCK_STREAM, proto);
      if (mSocket32 == INVALID_SOCKET32) {
         mLastWSAError = WSAGetLastError();
         return;
      }
      uint nonblock = 1;
      ioctlsocket(mSocket32, FIONBIO, nonblock);
   }

   int backlog = (Backlog > 0 ? Backlog : 1);

   // Try a bind
   sockaddr server;
   server.family = AF_INET;
   server.port = htons(ServerPort);
   server.address = (ForLocalhostOnly ? 0x100007f : 0); // 127.0.0.1 or INADDR_ANY

   if (TerminalInfoInteger(TERMINAL_X64)) {
      if (ReuseAddr) {
         uchar opt[4]; ArrayInitialize(opt, 0); opt[0] = 1;
         setsockopt(mSocket64, SOL_SOCKET, SO_REUSEADDR, opt, ArraySize(opt));
      }
      int bindres = bind(mSocket64, server, sizeof(sockaddr));
      if (bindres != 0) {
         // Bind failed
         mLastWSAError = WSAGetLastError();
      } else {
         int listenres = listen(mSocket64, backlog);
         if (listenres != 0) {
            // Listen failed
            mLastWSAError = WSAGetLastError();
         } else {
            mCreated = true;         
         }
      }
   } else {
      if (ReuseAddr) {
         uchar opt[4]; ArrayInitialize(opt, 0); opt[0] = 1;
         setsockopt(mSocket32, SOL_SOCKET, SO_REUSEADDR, opt, ArraySize(opt));
      }
      int bindres = bind(mSocket32, server, sizeof(sockaddr));
      if (bindres != 0) {
         // Bind failed
         mLastWSAError = WSAGetLastError();
      } else {
         int listenres = listen(mSocket32, backlog);
         if (listenres != 0) {
            // Listen failed
            mLastWSAError = WSAGetLastError();
         } else {
            mCreated = true;         
         }
      }
   }
}


// -------------------------------------------------------------
// Destructor. Close the socket if created
// -------------------------------------------------------------

ServerSocket::~ServerSocket()
{
   if (TerminalInfoInteger(TERMINAL_X64)) {
      if (mSocket64 != 0)  closesocket(mSocket64);
   } else {
      if (mSocket32 != 0)  closesocket(mSocket32);
   }   
}

// -------------------------------------------------------------
// Accepts any incoming connection. Returns either NULL,
// or an instance of ClientSocket
// -------------------------------------------------------------

ClientSocket * ServerSocket::Accept()
{
   if (!mCreated) return NULL;
   
   ClientSocket * pClient = NULL;

   if (TerminalInfoInteger(TERMINAL_X64)) {
      SOCKET_HANDLE64 acc = accept(mSocket64, 0, 0);
      if (acc != INVALID_SOCKET64) {
         pClient = new ClientSocket(acc);
      }
   } else {
      SOCKET_HANDLE32 acc = accept(mSocket32, 0, 0);
      if (acc != INVALID_SOCKET32) {
         pClient = new ClientSocket(acc);
      }
   }

   return pClient;
}

// ---- Embedded PyInSockClient
// PyInSockClient.mqh - helpers para socket cliente (MQL5 API oficial)
#ifndef __PYIN_SOCK_CLIENT_MQH__
#define __PYIN_SOCK_CLIENT_MQH__

#define PYIN_SOCKET_INVALID INVALID_HANDLE
#define PYIN_ERR_IO 5273
#define PYIN_ERR_INVALID_HANDLE 5270

// Conecta (cliente) e aplica timeouts globais
bool PySockConnect(int &sock, const string host, const uint port,
                   const uint timeout_connect_ms,
                   const uint timeout_send_ms,
                   const uint timeout_recv_ms,
                   string &err)
{
  err="";
  if(sock!=PYIN_SOCKET_INVALID)
  {
    if(SocketIsConnected(sock)) return true;
    SocketClose(sock);
    sock=PYIN_SOCKET_INVALID;
  }

  sock=SocketCreate();
  if(sock==PYIN_SOCKET_INVALID) { err="create"; return false; }
  if(!SocketConnect(sock, host, port, timeout_connect_ms))
  {
    err="connect";
    SocketClose(sock);
    sock=PYIN_SOCKET_INVALID;
    return false;
  }
  SocketTimeouts(sock, timeout_send_ms, timeout_recv_ms);
  return true;
}

void PySockClose(int &sock)
{
  if(sock!=PYIN_SOCKET_INVALID)
  {
    SocketClose(sock);
    sock=PYIN_SOCKET_INVALID;
  }
}

bool PySockIsConnected(const int sock)
{
  if(sock==PYIN_SOCKET_INVALID) return false;
  return SocketIsConnected(sock);
}

// Envia todos os bytes do buffer (loop até completar ou erro)
bool PySockSendAll(const int sock, const uchar &buf[], const int len, string &err)
{
  err="";
  if(sock==PYIN_SOCKET_INVALID) { err="invalid"; return false; }
  int sent=0;
  while(sent<len && !IsStopped())
  {
    int r = SocketSend(sock, buf, len-sent);
    if(r<=0)
    {
      if(GetLastError()==PYIN_ERR_IO) err="io";
      else err="send";
      return false;
    }
    if(sent==0 && r==len) return true;
    // SocketSend escreve no início do buffer; copiar fatia manualmente
    sent += r;
    if(sent<len)
    {
      uchar tmp[];
      ArrayResize(tmp, len-sent);
      ArrayCopy(tmp, buf, 0, sent, len-sent);
      return PySockSendAll(sock, tmp, ArraySize(tmp), err);
    }
  }
  return sent==len;
}

// Lê exatamente len bytes, com timeouts
bool PySockRecvExact(const int sock, const int len, uchar &out[],
                     const uint per_read_timeout_ms,
                     const uint overall_timeout_ms,
                     string &err)
{
  err="";
  if(sock==PYIN_SOCKET_INVALID) { err="invalid"; return false; }
  if(len<=0) { ArrayResize(out,0); return true; }
  ArrayResize(out, len);
  int got=0;
  uint start=GetTickCount();

  while(got<len && !IsStopped())
  {
    if(overall_timeout_ms>0 && (GetTickCount()-start)>overall_timeout_ms)
    {
      err="timeout";
      return false;
    }

    ResetLastError();
    uint avail = SocketIsReadable(sock);
    if(avail==0)
    {
      int errcode = GetLastError();
      if(errcode==PYIN_ERR_IO || errcode==PYIN_ERR_INVALID_HANDLE)
      {
        err="io";
        return false;
      }
      Sleep(1);
      continue;
    }

    uint toread = (uint)MathMin(len-got, (int)avail);
    uchar buf[];
    ResetLastError();
    int r = SocketRead(sock, buf, toread, per_read_timeout_ms);
    if(r<=0)
    {
      if(GetLastError()==PYIN_ERR_IO) { err="io"; return false; }
      Sleep(1);
      continue;
    }
    ArrayCopy(out, buf, got, 0, r);
    got += r;
  }
  return got==len;
}

// Envia frame binário (0xFF + len + header + payload)
bool PySockSendFrame(const int sock, const string header, const uchar &payload[], string &err)
{
  err="";
  uchar hb[]; StringToCharArray(header, hb, 0, StringLen(header), CP_UTF8);
  int hlen = ArraySize(hb);
  uchar prefix[5];
  prefix[0]=0xFF;
  prefix[1]=(uchar)((hlen>>24)&0xFF);
  prefix[2]=(uchar)((hlen>>16)&0xFF);
  prefix[3]=(uchar)((hlen>>8)&0xFF);
  prefix[4]=(uchar)(hlen&0xFF);
  if(!PySockSendAll(sock, prefix, 5, err)) return false;
  if(!PySockSendAll(sock, hb, hlen, err)) return false;
  int plen = ArraySize(payload);
  if(plen>0 && !PySockSendAll(sock, payload, plen, err)) return false;
  return true;
}

bool PySockRecvFrame(const int sock, string &header, uchar &payload[],
                     const uint per_read_timeout_ms,
                     const uint overall_timeout_ms,
                     string &err)
{
  err="";
  header=""; ArrayResize(payload,0);
  uchar first[];
  if(!PySockRecvExact(sock, 1, first, per_read_timeout_ms, overall_timeout_ms, err)) return false;
  if(first[0]!=0xFF) { err="bad_prefix"; return false; }
  uchar lenbuf[];
  if(!PySockRecvExact(sock, 4, lenbuf, per_read_timeout_ms, overall_timeout_ms, err)) return false;
  int hlen = (lenbuf[0]<<24)|(lenbuf[1]<<16)|(lenbuf[2]<<8)|lenbuf[3];
  uchar hb[];
  if(!PySockRecvExact(sock, hlen, hb, per_read_timeout_ms, overall_timeout_ms, err)) return false;
  header = CharArrayToString(hb,0,hlen,CP_UTF8);
  string parts[]; int n=StringSplit(header,'|',parts);
  if(n>=6)
  {
    int raw_len = (int)StringToInteger(parts[5]);
    if(raw_len>0)
    {
      if(!PySockRecvExact(sock, raw_len, payload, per_read_timeout_ms, overall_timeout_ms, err)) return false;
    }
  }
  return true;
}

// Envia linha de texto (terminada em \n)
bool PySockSendLine(const int sock, const string line, string &err)
{
  err="";
  uchar b[]; StringToCharArray(line, b, 0, StringLen(line), CP_UTF8);
  return PySockSendAll(sock, b, ArraySize(b), err);
}

// Recebe linha até '\n'
bool PySockRecvLine(const int sock, string &out,
                    const uint per_read_timeout_ms,
                    const uint overall_timeout_ms,
                    string &err)
{
  err="";
  uchar buf[4096]; int idx=0; uchar ch[];
  uint start=GetTickCount();
  while(!IsStopped())
  {
    if(overall_timeout_ms>0 && (GetTickCount()-start)>overall_timeout_ms)
    {
      err="timeout"; return false;
    }
    if(!PySockRecvExact(sock, 1, ch, per_read_timeout_ms, overall_timeout_ms, err)) return false;
    if(ch[0]=='\n') break;
    if(idx<4096) buf[idx++]=ch[0];
  }
  out=CharArrayToString(buf,0,idx,CP_UTF8);
  return true;
}

#endif


string LISTENER_VERSION_SOCKET = "pyincupy-service-bridge-1.0.0";

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
    Print("[PyInCupyServiceBridge] WSAStartup failed err=", res);
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
  if(InpVerboseLogs) Print("[PyInCupyServiceBridge] ", txt);
}

ServerSocket *g_server = NULL;
ClientSocket *g_client = NULL;
// cliente python
int g_pySock = PYIN_SOCKET_INVALID;
bool  g_py_ready=false;
uint g_last_ping = 0;

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
    Print("[PyInCupyServiceBridge] Server socket FAILED err=", err, " port=", InpPort);
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
    if(InpVerboseLogs) Log(StringFormat("ROLE=CLIENT connect_pyout try %s:%d", h, InpPyOutPort));
    string err="";
    if(PySockConnect(g_pySock, h, (uint)InpPyOutPort, InpPyOutConnectMs, InpPyOutSendMs, InpPyOutRecvMs, err))
    {
      if(InpVerboseLogs) Log(StringFormat("ROLE=CLIENT pyout connected %s:%d", h, InpPyOutPort));
      g_last_ping = GetTickCount();
      return true;
    }
    PySockClose(g_pySock);
  }
  return false;
}

void ClosePy()
{
  PySockClose(g_pySock);
  g_py_ready=false;
}

bool PyPing()
{
  if(g_pySock==PYIN_SOCKET_INVALID) return false;
  string err="";
  if(!PySockSendLine(g_pySock, "PING\n", err)) return false;
  string resp;
  if(!PySockRecvLine(g_pySock, resp, InpPyOutStepMs, 2000, err)) return false;
  if(resp=="PONG")
  {
    g_last_ping = GetTickCount();
    g_py_ready = true;
    return true;
  }
  g_py_ready = false;
  return false;
}

bool EnsurePyAlive()
{
  if(g_pySock!=PYIN_SOCKET_INVALID && PySockIsConnected(g_pySock) && g_py_ready)
    return true;
  if(g_pySock!=PYIN_SOCKET_INVALID && PySockIsConnected(g_pySock))
    return PyPing();
  if(ConnectPy())
    return PyPing();
  return false;
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

bool PySendErrFrame(ClientSocket *sock, const string id, const string job_id, const string msg)
{
  if(sock==NULL) return false;
  uchar payload[]; StringToCharArray(msg, payload, 0, StringLen(msg), CP_UTF8);
  string header = id+"|PY_ARRAY_ERROR|"+job_id+"|txt|0|"+IntegerToString(ArraySize(payload));
  return PySendFrame(sock, header, payload);
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
  if(InpVerboseLogs)
  {
    string bind = (InpLocalhostOnly ? "127.0.0.1" : "0.0.0.0");
    Log(StringFormat("ROLE=SERVER listen %s:%d | pyout_hosts=%s pyout_port=%d", bind, InpPort, InpPyOutHost, InpPyOutPort));
  }

  while(!IsStopped())
  {
    // keep PyOut connected and alive
    if(InpPyPingMs > 0 && g_pySock!=PYIN_SOCKET_INVALID && PySockIsConnected(g_pySock))
    {
      uint now = GetTickCount();
      if(now - g_last_ping >= (uint)InpPyPingMs)
      {
        if(!PyPing())
        {
          Log("pyout ping failed");
          ClosePy();
        }
        else
        {
          g_last_ping = now;
        }
      }
    }
    if(g_client==NULL)
    {
      ClientSocket *c = AcceptClient();
      if(c!=NULL)
      {
        g_client = c;
        if(InpVerboseLogs) Log("ROLE=SERVER client connected");
      }
    }
    if(g_client!=NULL)
    {
      string line; bool isFrame=false;
      int rcv = RecvMessage(g_client, isFrame, line);
      if(rcv==0) { Sleep(InpSleepMs); continue; } // sem dados
      if(rcv<0)
      {
        if(InpVerboseLogs) Log("ROLE=SERVER client done (connection closed)");
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
              if(raw_len>0)
              {
                uchar dump[];
                RecvExact(g_client, raw_len, dump);
              }
              PySendErrFrame(g_client, hid, "0", "size");
            }
            else
            {
              uchar raw[];
              if(!RecvExact(g_client, raw_len, raw))
              {
                PySendErrFrame(g_client, hid, "0", "recv_payload");
                continue;
              }

              if(!EnsurePyAlive()) { PySendErrFrame(g_client, hid, "0", "py_conn"); continue; }

              string header = line;
              string errp="";
              if(!PySockSendFrame(g_pySock, header, raw, errp))
              {
                PySendErrFrame(g_client, hid, "0", "py_send_fail"); ClosePy();
                continue;
              }

              string h=""; uchar payload[];
              if(!PySockRecvFrame(g_pySock, h, payload, InpPyOutStepMs, InpPyOutRecvMs, errp))
              {
                PySendErrFrame(g_client, hid, "0", "py_noresp"); ClosePy();
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
            string job_id = hparts[2];
            if(!EnsurePyAlive()) { PySendErrFrame(g_client, hid, job_id, "py_conn"); continue; }

            uchar empty[]; ArrayResize(empty,0);
            string header = line;
            string errp="";
            if(!PySockSendFrame(g_pySock, header, empty, errp))
            {
              PySendErrFrame(g_client, hid, job_id, "py_send_fail"); ClosePy();
              continue;
            }

            string h=""; uchar payload[];
            if(!PySockRecvFrame(g_pySock, h, payload, InpPyOutStepMs, InpPyOutRecvMs, errp))
            {
              PySendErrFrame(g_client, hid, job_id, "py_noresp"); ClosePy();
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

              if(!EnsurePyAlive()) { SendResp(g_client, "ERROR\npy_conn\n"); continue; }

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
else if(type=="SIM")
{
  bool pyok = EnsurePyAlive();
  msg = pyok ? "sim_ok" : "sim_fail";
  ok = pyok;
  ArrayResize(data,1);
  data[0] = pyok ? "pyout=ok" : "pyout=fail";
}
else if(type=="PY_CONNECT")
        {
          if(EnsurePyAlive()) { msg="py_connected"; ok=true; }
          else { msg="py_conn_fail"; ok=false; }
        }
        else if(type=="PY_DISCONNECT")
        {
          ClosePy(); msg="py_disconnected"; ok=true;
        }
        else if(type=="PY_ARRAY_CALL")
        {
          if(!EnsurePyAlive()) { msg="py_conn"; ok=false; }
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
          if(!EnsurePyAlive()) { msg="py_conn"; ok=false; }
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
