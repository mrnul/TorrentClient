import asyncio
import http.client
import io
import socket
import ssl
import urllib
from asyncio import Transport, Future
from typing import OrderedDict
from urllib import parse

import requests

import bencdec
from peer.peer_info import PeerInfo
from torrent.constants import *
from torrent.torrent_info import TorrentInfo
from tracker.tracker_base import TrackerBase


class TcpTrackerProtocol(asyncio.Protocol):
    def __init__(self, info_hash: bytes, self_port: int, self_id: bytes, tracker: str):
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
        print("connection made")
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
        self.transport = transport
        self.transport.write(full_request.encode())

    def data_received(self, data):
        self.data_rxed += data

    def connection_lost(self, exc):
        r = http.client.HTTPResponse(socket.socket())
        r.fp = io.BytesIO(self.data_rxed)
        r.begin()
        if r.status == 200:
            response = bencdec.decode(r.read())
            self.interval = response.get("interval", 60)
            for p in response[PEERS]:
                if not isinstance(p, OrderedDict):
                    continue
                self.peer_data.add(PeerInfo(p[IP].decode(), p[PORT], p[PEER_ID]))
        self.transport.close()
        self.future.set_result(self.peer_data)

    async def finish(self):
        await self.future

    def result(self):
        return self.future.result(), self.interval


class HttpTracker(TrackerBase):

    async def request_peers(self, torrent_info: TorrentInfo) -> tuple[set[PeerInfo], int]:
        parsed_url = urllib.parse.urlparse(self.tracker)
        transport, protocol = await asyncio.get_event_loop().create_connection(
            lambda: TcpTrackerProtocol(
                info_hash=torrent_info.info_hash,
                self_port=torrent_info.self_port,
                self_id=torrent_info.self_id,
                tracker=self.tracker,
            ),
            host=parsed_url.hostname,
            port=443,
            ssl=ssl.create_default_context(), server_hostname=parsed_url.hostname)

        try:
            await protocol.finish()
        finally:
            transport.close()
        peers, interval = protocol.result()
        return peers, interval
