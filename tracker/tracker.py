import asyncio
import os
import ssl
import urllib.parse

from logger.logger import Logger
from peer.peer_info import PeerInfo
from torrent.torrent_info import TorrentInfo
from tracker.tcp_tracker_protocol import TcpTrackerProtocol
from tracker.udp_tracker_protocol import UdpTrackerProtocol


class Tracker:
    """
    Class to handle tracker tcp and udp protocols
    """

    def __init__(self, tracker: str, torrent_info: TorrentInfo):
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

    async def _build_tcp_transport_and_protocol_secure(self):
        return await asyncio.get_event_loop().create_connection(
            lambda: TcpTrackerProtocol(
                info_hash=self.torrent_info.metadata.info_hash,
                self_port=self.torrent_info.self_port,
                self_id=self.torrent_info.self_id,
                tracker=self.tracker,
                logger=self.logger,
            ),
            host=self.parsed_url.hostname,
            port=443,
            ssl=ssl.create_default_context(),
            server_hostname=self.parsed_url.hostname
        )

    async def _build_tcp_transport_and_protocol(self):
        return await asyncio.get_event_loop().create_connection(
            lambda: TcpTrackerProtocol(
                info_hash=self.torrent_info.metadata.info_hash,
                self_port=self.torrent_info.self_port,
                self_id=self.torrent_info.self_id,
                tracker=self.tracker,
                logger=self.logger,
            ),
            host=self.parsed_url.hostname,
            port=80,
        )

    async def request_peers(self) -> tuple[set[PeerInfo], int]:
        scheme = self.parsed_url.scheme.casefold()
        self.logger.info(f"request_peers - {scheme}")
        transport, protocol = None, None
        try:
            async with asyncio.timeout(10):
                match scheme:
                    case 'http':
                        transport, protocol = await self._build_tcp_transport_and_protocol()
                    case 'https':
                        transport, protocol = await self._build_tcp_transport_and_protocol_secure()
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
