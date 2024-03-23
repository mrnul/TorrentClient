import asyncio
import http.client
import io
import ipaddress
import logging
import socket
import urllib
from asyncio import Transport, Future
from typing import OrderedDict
from urllib import parse

import requests

import bencdec
from peer.peer_info import PeerInfo
from torrent.constants import *


class TcpTrackerProtocol(asyncio.Protocol):
    """
    Protocol that performs request to a TCP tracker in order to get info about a torrent
    """
    def __init__(self, info_hash: bytes, self_port: int, self_id: bytes, tracker: str, logger: logging.Logger):
        self.logger = logger
        self.future: Future = asyncio.get_event_loop().create_future()
        self.transport: Transport | None = None
        self.sha1 = info_hash
        self.self_port = self_port
        self.self_id = self_id
        self.tracker = tracker
        self.peer_data: set[PeerInfo] = set()
        self.data_rxed: bytearray = bytearray()
        self.interval: int = 0

    def connection_made(self, transport: Transport):
        self.logger.info("connection made")
        params = {
            'info_hash': self.sha1,
            'peer_id': self.self_id,
            'port': self.self_port
        }
        r = requests.Request('GET', self.tracker, params=params)
        r_prepared = r.prepare()
        parsed_url = urllib.parse.urlparse(self.tracker)

        full_request = f"GET {r_prepared.url} HTTP/1.1\r\n"
        full_request += f"Host: {parsed_url.hostname}\r\n"
        full_request += f"Connection: close\r\n\r\n"
        self.logger.info(f'request: {full_request}')
        self.transport = transport
        self.transport.write(full_request.encode())

    def data_received(self, data):
        self.logger.info('Data rxed')
        self.data_rxed += data

    def connection_lost(self, exc):
        self.logger.info('connection_lost')
        r = http.client.HTTPResponse(socket.socket())
        r.fp = io.BytesIO(self.data_rxed)
        r.begin()
        self.logger.info(f'status: {r.status}')
        if r.status == 200:
            raw = r.read()
            response = bencdec.decode(raw)
            self.interval = response.get(INTERVAL, 60)
            raw_peers = response[PEERS]
            if isinstance(raw_peers, bytes) and len(raw_peers) % 6 == 0:
                for i in range(0, len(raw_peers), 6):
                    peer_ip = ipaddress.IPv4Address(raw_peers[i: i + 4])
                    peer_port = int.from_bytes(raw_peers[i + 4: i + 6])
                    self.peer_data.add(PeerInfo(str(peer_ip), peer_port))
            elif isinstance(raw_peers, OrderedDict):
                for p in raw_peers:
                    self.peer_data.add(PeerInfo(p[IP].decode(), p[PORT], p[PEER_ID]))
        self.transport.close()
        self.future.set_result(self.peer_data)

    async def finish(self):
        await self.future

    def result(self) -> tuple[list[PeerInfo], int]:
        return self.future.result(), self.interval
