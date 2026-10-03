# Electrin - lightweight Rincoin client
# Distributed under the MIT software license, see the accompanying
# file LICENCE or http://www.opensource.org/licenses/mit-license.php
"""Scheduled chain milestones that affect signing.

A milestone is a consensus change scheduled at a block height of a network. While the next
block is within a few blocks of such a height, a transaction signed now may not confirm before
the rules change, and nodes would then drop it. The wallet asks the user to confirm before
signing in that window and recommends waiting until the milestone block has been mined.

To announce a future scheduled change, add a ChainMilestone to MILESTONES.
"""

from dataclasses import dataclass
from typing import Callable, List, Optional, Tuple, Type, TYPE_CHECKING

from . import constants
from .i18n import _
from .transaction import forkid_height_bounds, synced_tip_height

if TYPE_CHECKING:
    from .constants import AbstractNet


# target block interval of all Rincoin networks, used only for the "about N minutes" estimate
TARGET_BLOCK_SECONDS = 60


@dataclass(frozen=True)
class ChainMilestone:
    key: str
    # activation height on the given network, or None if the milestone does not apply there
    height_for_net: Callable[[Type['AbstractNet']], Optional[int]]
    # the window starts when the next block is this many blocks before the activation height
    warn_blocks_before: int
    # ... and ends this many blocks after it (0: it ends with the activation block)
    warn_blocks_after: int
    # callables, so that the texts are translated when shown; they take the notice
    title: Callable[['MilestoneNotice'], str]
    message: Callable[['MilestoneNotice'], str]

    def height(self, net: Type['AbstractNet'] = None) -> Optional[int]:
        return self.height_for_net(net or constants.net)


@dataclass(frozen=True)
class MilestoneNotice:
    milestone: ChainMilestone
    activation_height: int
    next_height: Optional[int]  # None if only bounds on the height are known

    @property
    def blocks_left(self) -> Optional[int]:
        if self.next_height is None:
            return None
        return max(0, self.activation_height - self.next_height)

    def title(self) -> str:
        return self.milestone.title(self)

    def message(self) -> str:
        return self.milestone.message(self)


def _fmt_height(height: int) -> str:
    return f"{height:,}"


def _forkid_title(notice: MilestoneNotice) -> str:
    return _("Rincoin network upgrade at block {}").format(_fmt_height(notice.activation_height))


def _forkid_message(notice: MilestoneNotice) -> str:
    height = _fmt_height(notice.activation_height)
    if notice.blocks_left is None:
        distance = _("The current height is not known exactly, but it is close to that block.")
    elif notice.blocks_left == 0:
        distance = _("The next block is that block.")
    else:
        distance = _("That block is {} block(s) away, about {} minute(s).").format(
            notice.blocks_left, notice.blocks_left * TARGET_BLOCK_SECONDS // 60)
    return '\n\n'.join([
        ' '.join([
            _("The Rincoin network changes its transaction signature rules at block {}.").format(height),
            distance,
        ]),
        _("A transaction signed now can be dropped by the network if it is not confirmed in time for "
          "the signature rules of the block it ends up in. You would then have to sign and send it again."),
        _("We recommend waiting a few minutes until block {} has been mined, and sending the transaction then.").format(height),
    ])


MILESTONES = (
    # Rincoin Community Core 1.2.0: replay-protected signatures (SIGHASH_FORKID, fork ID 840)
    # from height 840,000 on mainnet (8,400 testnet, 840 regtest and preview).
    ChainMilestone(
        key='sighash-forkid-840',
        height_for_net=lambda net: net.SIGHASH_FORK_HEIGHT,
        warn_blocks_before=10,
        warn_blocks_after=0,
        title=_forkid_title,
        message=_forkid_message,
    ),
)


def _window(milestone: ChainMilestone, activation_height: int) -> Tuple[int, int]:
    """Next-block heights [start, end) for which the milestone asks for confirmation."""
    return (activation_height - milestone.warn_blocks_before,
            activation_height + milestone.warn_blocks_after)


def signing_notices(
    *,
    tip_height: Optional[int] = None,
    psbt_hint: Optional[Tuple[int, int]] = None,
    stored_height: Optional[int] = None,
    now: Optional[int] = None,
    milestones=None,
) -> List[MilestoneNotice]:
    """Milestones whose confirmation window contains the next block (tip height + 1).

    tip_height: height of the synced header tip; when None, the registered network source is
    asked, and without an answer every milestone is reported whose window the bounds on the
    height (see transaction.forkid_height_bounds) do not rule out.
    """
    if milestones is None:
        milestones = MILESTONES
    if tip_height is None:
        tip_height = synced_tip_height()
    if tip_height is not None:
        next_lo = next_hi = tip_height + 1
        exact = True
    else:
        lower, upper = forkid_height_bounds(psbt_hint=psbt_hint, stored_height=stored_height, now=now)
        next_lo = lower + 1
        next_hi = upper + 1 if upper is not None else next_lo
        exact = False
    notices = []
    for milestone in milestones:
        activation_height = milestone.height()
        if activation_height is None:
            continue
        start, end = _window(milestone, activation_height)
        if next_lo < end and next_hi >= start:
            notices.append(MilestoneNotice(
                milestone=milestone,
                activation_height=activation_height,
                next_height=next_lo if exact else None,
            ))
    return notices


def notices_text(notices: List[MilestoneNotice]) -> str:
    return '\n\n'.join(notice.message() for notice in notices)


def notices_title(notices: List[MilestoneNotice]) -> str:
    return notices[0].title() if notices else ''
