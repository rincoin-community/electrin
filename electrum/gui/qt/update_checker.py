# Copyright (C) 2019 The Electrum developers
# Distributed under the MIT software license, see the accompanying
# file LICENCE or http://www.opensource.org/licenses/mit-license.php
#
# The latest release is announced at electrin.net, signed with the OpenPGP release key
# (see electrum/version_announcement.py). The automatic check stays off until it is
# enabled in this file (_UPDATE_CHECK_DISABLED) and the announcement is published signed.

import asyncio
from typing import Optional

from PyQt6.QtCore import Qt, QThread, pyqtSignal
from PyQt6.QtWidgets import QVBoxLayout, QLabel, QProgressBar, QHBoxLayout, QPushButton, QDialog

from electrum import version
from electrum import version_announcement
from electrum.i18n import _
from electrum.util import make_aiohttp_session
from electrum.logging import Logger
from electrum.network import Network

# flip to False once electrin.net serves the signed announcement (UPDATE-CHECK in README.md)
_UPDATE_CHECK_DISABLED = True


class UpdateCheck(QDialog, Logger):
    url = version_announcement.ANNOUNCEMENT_URL
    download_url = version_announcement.DOWNLOAD_URL

    def __init__(self, *, latest_version=None):
        QDialog.__init__(self)
        self.setWindowTitle('Electrin - ' + _('Update Check'))
        self.content = QVBoxLayout()
        self.content.setContentsMargins(*[10]*4)

        self.heading_label = QLabel()
        self.content.addWidget(self.heading_label)

        self.detail_label = QLabel()
        self.detail_label.setTextInteractionFlags(Qt.TextInteractionFlag.LinksAccessibleByMouse)
        self.detail_label.setOpenExternalLinks(True)
        self.content.addWidget(self.detail_label)

        self.pb = QProgressBar()
        self.pb.setMaximum(0)
        self.pb.setMinimum(0)
        self.content.addWidget(self.pb)

        versions = QHBoxLayout()
        versions.addWidget(QLabel(_("Current version: {}").format(version.ELECTRIN_VERSION)))
        self.latest_version_label = QLabel(_("Latest version: {}").format(" "))
        versions.addWidget(self.latest_version_label)
        self.content.addLayout(versions)

        self.update_view(latest_version)

        if not _UPDATE_CHECK_DISABLED:
            self.update_check_thread = UpdateCheckThread()
            self.update_check_thread.checked.connect(self.on_version_retrieved)
            self.update_check_thread.failed.connect(self.on_retrieval_failed)
            self.update_check_thread.start()
        else:
            self.pb.hide()
            self.heading_label.setText('<h2>' + _("Update check is disabled") + '</h2>')
            self.detail_label.setText(
                _("Automatic update checking is disabled during the testing phase.") + "<br><br>" +
                _("Please check for updates manually at") + " " +
                "<a href='{u}'>GitHub Releases</a>.".format(u=UpdateCheck.download_url)
            )

        close_button = QPushButton(_("Close"))
        close_button.clicked.connect(self.close)
        self.content.addWidget(close_button)
        self.setLayout(self.content)
        self.show()

    def on_version_retrieved(self, version):
        self.update_view(version)

    def on_retrieval_failed(self):
        self.heading_label.setText('<h2>' + _("Update check failed") + '</h2>')
        self.detail_label.setText(_("Sorry, but we were unable to check for updates. Please try again later."))
        self.pb.hide()

    @staticmethod
    def is_newer(latest_version) -> bool:
        return version_announcement.is_newer(str(latest_version), version.ELECTRIN_VERSION)

    def update_view(self, latest_version=None):
        if latest_version:
            self.pb.hide()
            self.latest_version_label.setText(_("Latest version: {}").format(latest_version))
            if self.is_newer(latest_version):
                self.heading_label.setText('<h2>' + _("There is a new update available") + '</h2>')
                url = "<a href='{u}'>{u}</a>".format(u=UpdateCheck.download_url)
                self.detail_label.setText(_("You can download the new version from {}.").format(url))
            else:
                self.heading_label.setText('<h2>' + _("Already up to date") + '</h2>')
                self.detail_label.setText(_("You are already on the latest version of Electrin."))
        else:
            self.heading_label.setText('<h2>' + _("Checking for updates...") + '</h2>')
            self.detail_label.setText(_("Please wait while Electrin checks for available updates."))


class UpdateCheckThread(QThread, Logger):
    checked = pyqtSignal(object)
    failed = pyqtSignal()

    def __init__(self):
        QThread.__init__(self)
        Logger.__init__(self)
        self.network = Network.get_instance()
        self._fut = None  # type: Optional[asyncio.Future]

    async def get_update_info(self):
        # note: Use long timeout here as it is not critical that we get a response fast,
        #       and it's bad not to get an update notification just because we did not wait enough.
        async with make_aiohttp_session(proxy=self.network.proxy, timeout=120) as session:
            async with session.get(UpdateCheck.url) as result:
                announcement = await result.json(content_type=None)
                version_num = version_announcement.verify_announcement(announcement)
                self.logger.info(f"valid signature for version announcement {version_num!r}")
                return version_num

    def run(self):
        # TODO [SECURITY] — Update checker disabled during testing phase.
        #   Do not contact electrum.org from Electrin. See module docstring.
        if _UPDATE_CHECK_DISABLED:
            self.logger.info("update check is disabled during testing phase")
            self.failed.emit()
            return
        if not self.network:
            self.failed.emit()
            return
        self._fut = asyncio.run_coroutine_threadsafe(self.get_update_info(), self.network.asyncio_loop)
        try:
            update_info = self._fut.result()
        except Exception as e:
            self.logger.info(f"got exception: '{repr(e)}'")
            self.failed.emit()
        else:
            self.checked.emit(update_info)

    def stop(self):
        if self._fut:
            self._fut.cancel()
        self.exit()
        self.wait()
