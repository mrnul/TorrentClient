import asyncio
import os
import ssl
import time
import urllib.parse
from asyncio import Task, Event

from file_handling.file_handler import FileHandler
from logger.logger import Logger
from messages import Bitfield, Handshake
from misc import utils
from peer import Peer
from peer.peer_info import PeerInfo
from torrent.torrent_info import TorrentInfo
from tracker.tcp_tracker_protocol import TcpTrackerProtocol
from tracker.udp_tracker_protocol import UdpTrackerProtocol


class Tracker:
    """
    Class to handle tracker tcp and udp protocols
    """
    __MIN_INTERVAL__ = 60.0

    def __init__(self, tracker: str, torrent_info: TorrentInfo):
        self.last_run: float = 0.0
        self.wake_up: Event = asyncio.Event()
        self.tracker: str = tracker
        self.torrent_info: TorrentInfo = torrent_info
        self.parsed_url = urllib.parse.urlparse(self.tracker)
        self.tracker_logs_directory = (f'./tracker_logs/{os.path.basename(self.torrent_info.torrent_file)} - '
                                       f'{self.parsed_url.scheme}')
        os.makedirs(self.tracker_logs_directory, exist_ok=True)
        log_file = os.path.join(self.tracker_logs_directory, f'{self.parsed_url.hostname}.log')
        self.logger = Logger().get(log_file, log_file)
        self.logger.info(f"Initialized tracker {self.tracker} - "
                         f"{torrent_info.torrent_file} - "
                         f"{self.torrent_info.metadata.info_hash.hex()} - "
                         f"{self.torrent_info.metadata.torrent_size}")

    async def _build_udp_transport_and_protocol(self):
        return await asyncio.get_running_loop().create_datagram_endpoint(
            lambda: UdpTrackerProtocol(
                info_hash=self.torrent_info.metadata.info_hash,
                self_port=self.torrent_info.self_port,
                self_id=self.torrent_info.self_id,
                tracker=self.tracker,
                logger=self.logger,
            ),
            remote_addr=(self.parsed_url.hostname, self.parsed_url.port)
        )

    async def _build_tcp_transport_and_protocol(self, secure: bool = False):
        return await asyncio.get_event_loop().create_connection(
            lambda: TcpTrackerProtocol(
                info_hash=self.torrent_info.metadata.info_hash,
                self_port=self.torrent_info.self_port,
                self_id=self.torrent_info.self_id,
                tracker=self.tracker,
                logger=self.logger,
            ),
            host=self.parsed_url.hostname,
            port=443 if secure else 80,
            ssl=ssl.create_default_context() if secure else None,
            server_hostname=self.parsed_url.hostname if secure else None
        )

    async def _request_peers(self) -> tuple[set[PeerInfo], int]:
        scheme = self.parsed_url.scheme.casefold()
        self.logger.info(f"request_peers - {scheme}")
        transport, protocol = None, None
        try:
            async with asyncio.timeout(10):
                match scheme:
                    case 'http':
                        transport, protocol = await self._build_tcp_transport_and_protocol()
                    case 'https':
                        transport, protocol = await self._build_tcp_transport_and_protocol(secure=True)
                    case 'udp':
                        transport, protocol = await self._build_udp_transport_and_protocol()
                    case _:
                        raise ValueError(f"Unknown scheme: {scheme}")
                await protocol.finish()
                transport.close()
                peers, interval = protocol.result()
        except (TimeoutError, ValueError, OSError):
            if transport:
                transport.close()
            peers, interval = set(), 0
        self.logger.info(f"result: ({len(peers)}, {interval})")
        return peers, interval

    async def tracker_main_job(
            self,
            peer_set: set[Peer],
            peer_tasks: set[Task],
            peer_readiness_tasks: set[Task],
            torrent_bitfield: Bitfield,
            file_handler: FileHandler,
    ):
        """
        Tracker jobs run in the background to periodically perform requests, get peer lists and create peer tasks
        """
        while True:
            peers, interval = set(), self.__MIN_INTERVAL__
            if time.time() - self.last_run > self.__MIN_INTERVAL__:
                peers, interval = await self._request_peers()
                for p_i in peers:
                    peer = Peer(p_i)
                    if peer in peer_set:
                        continue
                    peer_set.add(peer)
                    reserved = bytearray(int(0).to_bytes(8))
                    reserved[5] = 0x10
                    peer_task = asyncio.create_task(
                        peer.run_till_dead(
                            handshake=Handshake(
                                self.torrent_info.metadata.info_hash,
                                self.torrent_info.self_id,
                                reserved=reserved
                            ),
                            bitfield=torrent_bitfield,
                            file_handler=file_handler
                        ),
                        name=f'Peer {peer.peer_info.ip}'
                    )
                    peer_tasks.add(peer_task)
                    peer_task.add_done_callback(peer_tasks.discard)

                    peer_readiness_task = asyncio.create_task(
                        peer.ready_for_requests()
                    )
                    peer_readiness_tasks.add(peer_readiness_task)

                self.last_run = time.time()
            if interval < self.__MIN_INTERVAL__:
                interval = self.__MIN_INTERVAL__
            await utils.run_with_timeout(self.wake_up.wait(), interval)
            if self.wake_up.is_set():
                self.wake_up.clear()
