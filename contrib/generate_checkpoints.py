#!/usr/bin/env python3
"""Generate Electrin/Electrum-format checkpoints from a running Rincoin Core node.

Usage:
    python3 contrib/generate_checkpoints.py [--rpc-url URL] [--output FILE]

This script connects to a Rincoin Core RPC endpoint and produces the
checkpoints.json file used by Electrin for SPV chain validation.

== Checkpoint format ==

The file is a JSON array of [hash, target] pairs, one per 2016-block chunk:

    [
        ["<hash of block 2015>",  <target as int>],
        ["<hash of block 4031>",  <target as int>],
        ...
    ]

Because Rincoin uses DGW v3 (difficulty adjusts every block from height 30000)
and Electrin sets SPV_SKIP_DA_BITS_CHECK = True, the `target` field is not
used for validation. We store zero for all entries.

== Rincoin difficulty algorithm: Dark Gravity Wave v3 ==

DGW v3 (activated at height 30000 on Rincoin mainnet) re-calculates the
difficulty target for every single block, using the timestamps and targets of
the most recent 24 blocks. Before height 30000, Rincoin uses a classic
Bitcoin-style 2016-block retarget. The relevant parameters from
rincoin/src/chainparams.cpp are:

    consensus.nPowTargetTimespan = 33 * 60 * 60   # 33 hours
    consensus.nPowTargetSpacing  = 60              # 1 minute blocks
    consensus.DGWHeight          = 30000           # DGW activation height
    consensus.powLimit = uint256S("0000ffffffffffffffffffffffffffffffffffffffffffffffffffffffffffff")

An SPV wallet cannot independently recompute the DGW target without downloading
all 24 ancestor headers for every block. Electrin therefore trusts the `bits`
field declared in each header and only verifies that
`RinHash(header) <= bits_to_target(bits)`. Checkpoints provide a second layer
of assurance: the hash of the last block in each 2016-block segment is pinned,
preventing header-chain replacement within the checkpointed range.

== Usage ==

Only the Python standard library is needed, so the script can run as the user of the node.
Through rincoin-cli (cookie authentication):

    sudo -u <node user> python3 contrib/generate_checkpoints.py \
        --cli "rincoin-cli -conf=/etc/rincoin/rincoin.conf -datadir=/var/lib/rincoind" \
        --chainparams src/chainparams.cpp --output /tmp/checkpoints.json \
        --dump-last-chunk /tmp/checkpoints-last-chunk.hex

or through JSON-RPC: --rpc-url http://user:password@127.0.0.1:9556

Checkpoints end with the last complete 2016-block chunk at or below --max-height (default
750,000, the assumevalid block of Rincoin Community Core 1.2.0); the script refuses heights at
or above 840,000. The target stored with each checkpoint is the target of the chunk's last
block (Electrin uses it only to estimate chain work; with SPV_SKIP_DA_BITS_CHECK every header
is checked against its own bits). Before writing, the result is checked against the genesis
block and, with --chainparams, against every mainnet checkpoint of Rincoin Core's chainparams.cpp.

--dump-last-chunk writes the raw headers of the last checkpointed chunk, one hex line per
header, so that the checkpoints can be verified with Electrin's own header verification:

    python3 contrib/verify_checkpoints.py --headers /tmp/checkpoints-last-chunk.hex \
        electrum/chains/rincoin/checkpoints.json
"""

import argparse
import json
import base64
import re
import shlex
import subprocess
import sys
import urllib.request

CHUNK_SIZE = 2016
TRANSITION_HEIGHT = 840_000
MAINNET_GENESIS = "000096bdd6e4613ca89b074ebd6f609aba6fe3f868b34ee79380aa3bc7a8c9db"


class Rpc:
    def __init__(self, *, rpc_url=None, cli=None):
        self.rpc_url, self.cli = rpc_url, shlex.split(cli) if cli else None

    def __call__(self, method, *params):
        if self.cli:
            args = [json.dumps(p) if not isinstance(p, str) else p for p in params]
            out = subprocess.run(self.cli + [method] + args, check=True, capture_output=True, text=True).stdout
            try:
                return json.loads(out)
            except ValueError:
                return out.strip()
        url = urllib.request.urlparse(self.rpc_url)
        req = urllib.request.Request(
            f"{url.scheme}://{url.hostname}:{url.port}{url.path or '/'}",
            data=json.dumps({"jsonrpc": "1.0", "id": "electrin-checkpoints",
                             "method": method, "params": list(params)}).encode(),
            headers={"Content-Type": "application/json"})
        if url.username:
            token = base64.b64encode(f"{url.username}:{url.password}".encode()).decode()
            req.add_header("Authorization", "Basic " + token)
        with urllib.request.urlopen(req, timeout=60) as r:
            result = json.loads(r.read())
        if result.get("error"):
            raise RuntimeError(f"RPC error: {result['error']}")
        return result["result"]


def bits_to_target(bits: int) -> int:
    size, word = bits >> 24, bits & 0x007fffff
    return word >> (8 * (3 - size)) if size <= 3 else word << (8 * (size - 3))


def chainparams_checkpoints(path: str) -> dict:
    """{height: hash} of the mainnet checkpointData in Rincoin Core's chainparams.cpp."""
    text = open(path).read()
    main = text[text.index("class CMainParams"):text.index("class CTestNetParams")]
    pairs = re.findall(r'\{\s*(\d+)\s*,\s*uint256S\("0x([0-9a-f]{64})"\)\s*\}', main)
    return {int(h): v for h, v in pairs}


def main():
    parser = argparse.ArgumentParser(description=__doc__,
                                     formatter_class=argparse.RawDescriptionHelpFormatter)
    source = parser.add_mutually_exclusive_group(required=True)
    source.add_argument("--rpc-url", help="Rincoin Core JSON-RPC URL, e.g. http://user:password@127.0.0.1:9556")
    source.add_argument("--cli", help='rincoin-cli command line, e.g. "rincoin-cli -conf=/etc/rincoin/rincoin.conf"')
    parser.add_argument("--output", default="electrum/chains/rincoin/checkpoints.json",
                        help="Output file path (default: electrum/chains/rincoin/checkpoints.json)")
    parser.add_argument("--max-height", type=int, default=750_000,
                        help="Highest block a checkpoint may name (default: 750000)")
    parser.add_argument("--chainparams", help="Rincoin Core src/chainparams.cpp to cross-check against")
    parser.add_argument("--dump-last-chunk", help="Write the raw headers of the last checkpointed chunk here")
    args = parser.parse_args()

    rpc = Rpc(rpc_url=args.rpc_url, cli=args.cli)
    info = rpc("getblockchaininfo")
    if info["chain"] != "main":
        sys.exit(f"Error: node is on chain {info['chain']!r}, not mainnet")
    if info.get("initialblockdownload"):
        sys.exit("Error: node is still in initial block download")
    tip_height = info["blocks"]
    max_height = min(args.max_height, tip_height - 1000)
    if max_height >= TRANSITION_HEIGHT:
        sys.exit(f"Error: checkpoints must stay below the height-{TRANSITION_HEIGHT} transition")
    if rpc("getblockhash", 0) != MAINNET_GENESIS:
        sys.exit("Error: unexpected genesis block")
    if args.chainparams:
        for height, expected in sorted(chainparams_checkpoints(args.chainparams).items()):
            if height <= tip_height and rpc("getblockhash", height) != expected:
                sys.exit(f"Error: block {height} differs from the checkpoint in {args.chainparams}")
            print(f"  chainparams checkpoint {height} matches")

    num_chunks = (max_height + 1) // CHUNK_SIZE  # complete chunks only
    print(f"Chain tip {tip_height}; {num_chunks} checkpoints up to block {num_chunks * CHUNK_SIZE - 1}")

    checkpoints = []
    for i in range(num_chunks):
        height = (i + 1) * CHUNK_SIZE - 1  # last block in chunk
        block_hash = rpc("getblockhash", height)
        header = rpc("getblockheader", block_hash)
        checkpoints.append([block_hash, bits_to_target(int(header["bits"], 16))])
        if (i + 1) % 50 == 0 or i == num_chunks - 1:
            print(f"  ... {i + 1}/{num_chunks} (height {height})")

    with open(args.output, "w") as f:
        json.dump(checkpoints, f, indent=2)
        f.write("\n")
    print(f"Wrote {len(checkpoints)} checkpoints to {args.output}")

    if args.dump_last_chunk:
        start = (num_chunks - 1) * CHUNK_SIZE
        with open(args.dump_last_chunk, "w") as f:
            for height in range(start, start + CHUNK_SIZE):
                f.write(rpc("getblockheader", rpc("getblockhash", height), False) + "\n")
        print(f"Wrote the headers of blocks {start}..{start + CHUNK_SIZE - 1} to {args.dump_last_chunk}")


if __name__ == "__main__":
    main()
