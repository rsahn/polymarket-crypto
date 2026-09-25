"""Persistent, bounded read-only HTTP client. No redirects or automatic retries.
Callers still enforce their route/parameter allowlists before this boundary.
"""
import json
import logging
import threading
from urllib.parse import urlsplit,urlunsplit
import httpx


class ReadOnlyPool:
    def __init__(self,urls,*,rpc=False,client=None):
        # HTTPX logs full URLs at INFO (RPC URLs can contain a key).
        logging.getLogger('httpx').disabled=True
        for name in tuple(logging.Logger.manager.loggerDict):
            if name.startswith('httpcore'):logging.getLogger(name).disabled=True
        self.urls=frozenset(urls);self.rpc=rpc;self.lock=threading.Lock();self.streams={}
        self.client=client or httpx.Client(follow_redirects=False,trust_env=True,
            limits=httpx.Limits(max_connections=8,max_keepalive_connections=8,keepalive_expiry=30))
    def close(self):self.client.close()
    def read(self,method,url,*,headers,limit,timeout,entry,body=None):
        u=urlsplit(url)
        if u.scheme!='https' or u.username or u.password or u.fragment:raise ValueError('POOL_URL_FORBIDDEN')
        route=urlunsplit((u.scheme,u.netloc,u.path,'',''))
        if self.rpc:
            if method!='POST' or url not in self.urls:raise ValueError('POOL_RPC_ROUTE')
            try:value=json.loads(body)
            except Exception:raise ValueError('POOL_RPC_SCHEMA') from None
            if not isinstance(value,dict):raise ValueError('POOL_RPC_SCHEMA')
            if value.get('method') not in {'eth_chainId','eth_getBlockByNumber','eth_getCode','eth_getLogs','eth_call'}:
                raise ValueError('POOL_RPC_METHOD')
        elif method!='GET' or route not in self.urls or body is not None:raise ValueError('POOL_GET_ONLY')
        entry.update(transport='HTTPX_PERSISTENT_POOL',connect_tcp_started=0,start_tls_started=0,connection_reuse_proven=False)
        def trace(name,info):
            # Never retain trace info: it can contain the URL or request headers.
            if name.endswith('connect_tcp.started'):entry['connect_tcp_started']+=1
            if name.endswith('start_tls.started'):entry['start_tls_started']+=1
        try:
            with self.client.stream(method,url,headers=headers,content=body,timeout=timeout,
                                    follow_redirects=False,extensions={'trace':trace}) as response:
                entry['http_status']=response.status_code
                if response.status_code!=200:raise ValueError('POOL_HTTP_STATUS')
                stream=response.extensions.get('network_stream')
                if stream is not None:
                    with self.lock:
                        entry['connection_reuse_proven']=self.streams.get(id(stream)) is stream
                        if len(self.streams)>=64:self.streams.clear()
                        self.streams[id(stream)]=stream
                data=bytearray()
                for chunk in response.iter_bytes(chunk_size=65536):
                    data.extend(chunk)
                    if len(data)>limit:raise ValueError('POOL_RESPONSE_LIMIT')
                return response.status_code,bytes(data)
        except Exception:raise RuntimeError('POOLED_READ_FAILED') from None
