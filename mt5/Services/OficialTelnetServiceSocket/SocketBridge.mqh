// SocketBridge.mqh - wrapper básico para winsock (TCP)
#ifndef __SOCKET_BRIDGE_MQH__
#define __SOCKET_BRIDGE_MQH__

#import "ws2_32.dll"
int   WSAStartup(ushort wVersionRequested, uchar &lpWSAData[]);
int   WSACleanup();
uint  socket(int af,int type,int protocol);
int   bind(uint s, uchar &name[], int namelen);
int   listen(uint s,int backlog);
uint  accept(uint s, uchar &addr[], int &addrlen);
int   recv(uint s, uchar &buf[], int len, int flags);
int   send(uint s, uchar &buf[], int len, int flags);
int   connect(uint s, uchar &name[], int namelen);
int   closesocket(uint s);
ushort htons(ushort hostshort);
uint  htonl(uint hostlong);
int   ioctlsocket(uint s, long cmd, uint &argp);
#import

#define AF_INET   2
#define SOCK_STREAM 1
#define IPPROTO_TCP 6
#define FIONBIO 0x8004667E

// sockaddr_in é 16 bytes (fam, port, addr, zero)
// ip4 default 0.0.0.0 (INADDR_ANY)
void MakeSockAddr(uchar &sa[], ushort portHostOrder, uint ipHostOrder=0)
{
  ArrayResize(sa,16);
  ArrayInitialize(sa,0);
  sa[0]=(uchar)AF_INET; sa[1]=0;
  ushort p=htons(portHostOrder);
  sa[2]=(uchar)(p & 0xFF);
  sa[3]=(uchar)((p>>8) & 0xFF);
  uint ip=htonl(ipHostOrder);
  sa[4]=(uchar)(ip & 0xFF);
  sa[5]=(uchar)((ip>>8) & 0xFF);
  sa[6]=(uchar)((ip>>16) & 0xFF);
  sa[7]=(uchar)((ip>>24) & 0xFF);
}

bool SetNonBlocking(uint sock)
{
  uint arg=1;
  return ioctlsocket(sock, FIONBIO, arg)==0;
}

#endif
