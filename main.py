import asyncio
import random
import struct
import urllib.parse
from asyncio import DatagramTransport, Future

from peer.peer_info import PeerInfo
from torrent import Torrent
from torrent.torrent_info import TorrentInfo


class UdpTrackerProtocol(asyncio.DatagramProtocol):
    def __init__(self, finish_future: Future, info_hash: bytes, self_port: int, self_id: bytes, tracker: str):
        self.finish_future = finish_future
        self.transport: DatagramTransport | None = None
        self.sha1 = info_hash
        self.self_port = self_port
        self.self_id = self_id
        self.tracker = tracker
        self.transaction_id = None
        self.peer_data: set[PeerInfo] = set()
        self._handler_of_rxed_data = None

    def _send_initial_data(self):
        print("send_initial_data")
        self.transaction_id = int.from_bytes(random.randbytes(4))
        msg = struct.pack(">QII", 0x41727101980, 0, self.transaction_id)
        self.transport.sendto(msg)
        self._handler_of_rxed_data = self._handle_initial_data_response

    def _handle_initial_data_response(self, rxed_data: bytes):
        print("_handle_initial_data_response")
        action, s_transaction_id, conn_id = struct.unpack_from('>IIQ', rxed_data)
        if action != 0 or self.transaction_id != s_transaction_id:
            raise ValueError(f'Expected (action, transaction_id) = (0, {self.transaction_id})'
                             f' but received ({action}, {self.transaction_id})')

        parsed_url = urllib.parse.urlparse(self.tracker)
        key = int.from_bytes(random.randbytes(2))
        msg = struct.pack('>QII', conn_id, 1, self.transaction_id)
        msg += self.sha1
        msg += self.self_id
        msg += struct.pack('>QQQIIIiHH', 0, 0, 0, 0, 0, key, -1, self.self_port, 2)
        msg += struct.pack('>B', len(parsed_url.hostname))
        msg += parsed_url.hostname.encode()
        self.transport.sendto(msg)
        self._handler_of_rxed_data = self._handle_final_response

    def _handle_final_response(self, rxed_data: bytes):
        print("_handle_final_response")
        action, transaction_id, interval, leechers, seeders = struct.unpack_from('>IIIII', rxed_data)
        data_len = len(rxed_data)

        for offset in range(20, data_len, 6):
            ip, port = struct.unpack_from('>IH', rxed_data, offset)
            ip_str = '.'.join(str(byte) for byte in int(ip).to_bytes(4))
            self.peer_data.add(PeerInfo(ip_str, port))
        self.transport.close()

    def handle_rxed_data(self, rxed_data: bytes):
        print("handle_rxed_data")
        if callable(self._handler_of_rxed_data):
            return self._handler_of_rxed_data(rxed_data)
        return None

    def connection_made(self, transport: DatagramTransport):
        self.transport = transport
        self._send_initial_data()

    def datagram_received(self, data: bytes, addr: tuple[str, int]):
        self.handle_rxed_data(data)

    def error_received(self, exc: Exception):
        print('Error received:', exc)

    def connection_lost(self, exc: Exception | None):
        print(f"Connection closed - Error: {exc}")
        self.finish_future.set_result(True)

    def get_peers(self):
        return self.peer_data


async def torrent1():
    torrent = Torrent(TorrentInfo('test1.torrent', 6881, b'hello i am testing  '))
    await torrent.download()
    await torrent.terminate()


async def torrent2():
    torrent = Torrent(TorrentInfo('test2.torrent', 6881, b'hello i am testing  '))
    await torrent.download()
    await torrent.terminate()


async def test_udp():
    loop = asyncio.get_running_loop()

    finish_future = loop.create_future()
    info = TorrentInfo('test2.torrent', 6881, b'hello i am testing  ')
    tracker = 'udp://tracker.dler.org:6969/announce'
    parsed_url = urllib.parse.urlparse(tracker)
    transport, protocol = await loop.create_datagram_endpoint(
        lambda: UdpTrackerProtocol(
            finish_future=finish_future,
            info_hash=info.info_hash,
            self_port=info.self_port,
            self_id=info.self_id,
            tracker=tracker
        ),
        remote_addr=(parsed_url.hostname, parsed_url.port))

    try:
        await finish_future
        print(protocol.get_peers())
    finally:
        transport.close()


async def main():
    tasks = [asyncio.create_task(test_udp())]
    tasks2 = [asyncio.create_task(asyncio.sleep(10))]
    await asyncio.wait(tasks2)


asyncio.run(main())
