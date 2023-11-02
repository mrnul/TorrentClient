import json

import requests

import bencdec
from misc.utils import get_info_sha1_hash
from peer import Peer

with open(f"test1.torrent", mode="rb") as f:
    data = f.read()

result = bencdec.decode(data)

h = get_info_sha1_hash(result['info'])
r = requests.get(result['announce-list'][0][0], params={
    'info_hash': h,
    'peer_id': 'hello i am testing  ',
    'port': 6881
})

response = bencdec.decode(r.content)
with open("response.json", mode="w") as f:
    json.dump(response, f, indent=2)

for p in response['peers']:
    peer = Peer(ip=p.get('ip'), port=p.get('port'), torrent_data=result)
    peer.start_communication(b'hello i am testing  ')
