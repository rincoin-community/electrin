#!/usr/bin/env python3
"""Verify generated mainnet checkpoints with Electrin's own header verification.

    python3 contrib/verify_checkpoints.py --headers /tmp/checkpoints-last-chunk.hex \
        electrum/chains/rincoin/checkpoints.json

--headers is the file written by contrib/generate_checkpoints.py --dump-last-chunk: the raw
headers of the last checkpointed chunk, one hex line per header. Each header must pass the
proof-of-work check against its own bits (RinHash), each must link to the previous one, the
first must link to the second-to-last checkpoint and the last must be the last checkpoint.
"""

import argparse
import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from electrum import constants  # noqa: E402
from electrum.blockchain import Blockchain, deserialize_header, hash_header, CHUNK_SIZE  # noqa: E402


def main():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("checkpoints")
    parser.add_argument("--headers", required=True)
    args = parser.parse_args()

    constants.RincoinMainnet.set_as_network()
    checkpoints = json.load(open(args.checkpoints))
    if not checkpoints or not all(isinstance(c, list) and len(c) == 2 for c in checkpoints):
        sys.exit("Error: unexpected checkpoint format")
    lines = [line.strip() for line in open(args.headers) if line.strip()]
    if len(lines) != CHUNK_SIZE:
        sys.exit(f"Error: expected {CHUNK_SIZE} headers, got {len(lines)}")
    index = len(checkpoints) - 1
    start = index * CHUNK_SIZE
    # the chunk links to the previous checkpoint (the first chunk starts with the genesis block)
    prev_hash = checkpoints[index - 1][0] if index > 0 else "0" * 64
    for i, line in enumerate(lines):
        header = deserialize_header(bytes.fromhex(line), start + i)
        target = Blockchain.bits_to_target(header["bits"])
        Blockchain.verify_header(header, prev_hash, target)
        prev_hash = hash_header(header)
    if prev_hash != checkpoints[-1][0]:
        sys.exit("Error: the last header is not the last checkpoint")
    print(f"OK: {len(checkpoints)} checkpoints, max checkpoint {len(checkpoints) * CHUNK_SIZE - 1}; "
          f"blocks {start}..{start + CHUNK_SIZE - 1} verified (proof of work, links, both ends)")


if __name__ == "__main__":
    main()
