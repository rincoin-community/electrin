#!/usr/bin/env python
#
# Electrum - lightweight Bitcoin client
# Copyright (C) 2012 thomasv@gitorious
#
# Permission is hereby granted, free of charge, to any person
# obtaining a copy of this software and associated documentation files
# (the "Software"), to deal in the Software without restriction,
# including without limitation the rights to use, copy, modify, merge,
# publish, distribute, sublicense, and/or sell copies of the Software,
# and to permit persons to whom the Software is furnished to do so,
# subject to the following conditions:
#
# The above copyright notice and this permission notice shall be
# included in all copies or substantial portions of the Software.
#
# THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND,
# EXPRESS OR IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF
# MERCHANTABILITY, FITNESS FOR A PARTICULAR PURPOSE AND
# NONINFRINGEMENT. IN NO EVENT SHALL THE AUTHORS OR COPYRIGHT HOLDERS
# BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER LIABILITY, WHETHER IN AN
# ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING FROM, OUT OF OR IN
# CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN THE
# SOFTWARE.

import os
import signal
import sys
import threading
from typing import Optional, TYPE_CHECKING, List, Sequence, Union

try:
    import PyQt6
    import PyQt6.QtGui
except Exception as e:
    from electrum import GuiImportError
    raise GuiImportError(
        "Error: Could not import PyQt6. On Linux systems, "
        "you may try 'sudo apt-get install python3-pyqt6'") from e

from PyQt6.QtGui import QGuiApplication, QCursor, QPalette
from PyQt6.QtWidgets import QApplication, QSystemTrayIcon, QWidget, QMenu, QMessageBox, QDialog, QToolTip
from PyQt6.QtCore import QObject, pyqtSignal, QTimer, Qt

import PyQt6.QtCore as QtCore

from electrum.logging import Logger, get_logger
_logger = get_logger(__name__)

try:
    # Preload QtMultimedia at app start, if available.
    # We use QtMultimedia on some platforms for camera-handling, and
    # lazy-loading it later led to some crashes. Maybe due to bugs in PyQt. (see #7725)
    from PyQt6.QtMultimedia import QMediaDevices; del QMediaDevices
except (ImportError, RuntimeError) as e:
    _logger.debug(f"failed to import optional dependency: PyQt6.QtMultimedia. exc={repr(e)}")
    pass  # failure is ok; it is an optional dependency.
else:
    _logger.debug(f"successfully preloaded optional dependency: PyQt6.QtMultimedia")

if sys.platform == "linux" and os.environ.get("APPIMAGE"):
    # For AppImage, we default to xcb qt backend, for better support of older system.
    # qt6 normally defaults to QT_QPA_PLATFORM=wayland instead of QT_QPA_PLATFORM=xcb.
    # However, the wayland QPA plugin requires libwayland-client0>=1.19, which is too new
    # for debian 11 or ubuntu 20.04. So instead, we default to the X11 integration (and not wayland).
    # see https://bugreports.qt.io/browse/QTBUG-114635
    os.environ.setdefault("QT_QPA_PLATFORM", "xcb")

from electrum.i18n import _, set_language
from electrum.plugin import run_hook
from electrum.util import (UserCancelled, profiler, send_exception_to_crash_reporter,
                           WalletFileException, get_new_wallet_name, InvalidPassword,
                           standardize_path, UserFacingException)
from electrum.wallet import Wallet, Abstract_Wallet
from electrum.wallet_db import WalletRequiresSplit, WalletRequiresUpgrade, WalletUnfinished
from electrum.gui import BaseElectrumGui
from electrum.simple_config import SimpleConfig
from electrum.wizard import WizardViewState
from electrum.keystore import load_keystore
from electrum.bip32 import is_xprv
from electrum import constants

from electrum.gui.common_qt.i18n import ElectrumTranslator
from electrum.gui.messages import TERMS_OF_USE_LATEST_VERSION

from .util import (read_QIcon, ColorScheme, custom_message_box, MessageBoxMixin, WWLabel,
                   set_windows_os_screenshot_protection_drm_flag)
from .main_window import ElectrumWindow
from .network_dialog import NetworkDialog
from .stylesheet_patcher import patch_qt_stylesheet
from .lightning_dialog import LightningDialog
from .exception_window import Exception_Hook
from .wizard.server_connect import QEServerConnectWizard
from .wizard.wallet import QENewWalletWizard

if TYPE_CHECKING:
    from electrum.daemon import Daemon
    from electrum.plugin import Plugins


class OpenFileEventFilter(QObject):
    def __init__(self, windows: Sequence[ElectrumWindow]):
        self.windows = windows
        super(OpenFileEventFilter, self).__init__()

    def eventFilter(self, obj, event):
        if event.type() == QtCore.QEvent.Type.FileOpen:
            if len(self.windows) >= 1:
                self.windows[0].set_payment_identifier(event.url().toString())
                return True
        return False


class ScreenshotProtectionEventFilter(QObject):
    def __init__(self):
        super().__init__()

    def eventFilter(self, obj, event):
        if (
            event.type() == QtCore.QEvent.Type.Show
            and isinstance(obj, QWidget)
            and obj.isWindow()
        ):
            set_windows_os_screenshot_protection_drm_flag(obj)
        return False


class QElectrumApplication(QApplication):
    new_window_signal = pyqtSignal(str, object)
    quit_signal = pyqtSignal()
    refresh_tabs_signal = pyqtSignal()
    refresh_amount_edits_signal = pyqtSignal()
    update_status_signal = pyqtSignal()
    update_fiat_signal = pyqtSignal()
    alias_received_signal = pyqtSignal()


class ElectrumGui(BaseElectrumGui, Logger):

    network_dialog: Optional['NetworkDialog']
    lightning_dialog: Optional['LightningDialog']

    @profiler
    def __init__(self, *, config: 'SimpleConfig', daemon: 'Daemon', plugins: 'Plugins'):
        BaseElectrumGui.__init__(self, config=config, daemon=daemon, plugins=plugins)
        Logger.__init__(self)
        self.logger.info(f"Qt GUI starting up... Qt={QtCore.QT_VERSION_STR}, PyQt={QtCore.PYQT_VERSION_STR}")
        # Uncomment this call to verify objects are being properly
        # GC-ed when windows are closed
        #plugins.add_jobs([DebugMem([Abstract_Wallet, SPV, Synchronizer,
        #                            ElectrumWindow], interval=5)])
        if hasattr(QtCore.Qt, "AA_ShareOpenGLContexts"):
            QtCore.QCoreApplication.setAttribute(QtCore.Qt.AA_ShareOpenGLContexts)
        if hasattr(QGuiApplication, 'setDesktopFileName'):
            QGuiApplication.setDesktopFileName('electrum')
        QGuiApplication.setApplicationName("Electrin")
        self.gui_thread = threading.current_thread()
        self.windows = []  # type: List[ElectrumWindow]
        self.open_file_efilter = OpenFileEventFilter(self.windows)
        self.app = QElectrumApplication(sys.argv)
        self.app.installEventFilter(self.open_file_efilter)
        self.screenshot_protection_efilter = ScreenshotProtectionEventFilter()
        if sys.platform in ['win32', 'windows'] and self.config.GUI_QT_SCREENSHOT_PROTECTION:
            self.app.installEventFilter(self.screenshot_protection_efilter)
        # explicitly set 'AA_DontShowIconsInMenus' False so menu icons are shown on MacOS
        self.app.setAttribute(Qt.ApplicationAttribute.AA_DontShowIconsInMenus, on=False)
        self.app.setWindowIcon(read_QIcon("electrum.png"))
        self.translator = ElectrumTranslator()
        self.app.installTranslator(self.translator)
        self._cleaned_up = False
        self.network_dialog = None
        self.lightning_dialog = None
        self._num_wizards_in_progress = 0
        self._num_wizards_lock = threading.Lock()
        self.dark_icon = self.config.GUI_QT_DARK_TRAY_ICON
        self.tray = None  # type: Optional[QSystemTrayIcon]
        self._init_tray()
        self.app.new_window_signal.connect(self.start_new_window)
        self.app.quit_signal.connect(self.app.quit, Qt.ConnectionType.QueuedConnection)
        # maybe set dark theme
        self.reload_app_stylesheet()

    def _init_tray(self):
        self.tray = QSystemTrayIcon(self.tray_icon(), None)
        self.tray.setToolTip('Electrin')
        self.tray.activated.connect(self.tray_activated)
        self.build_tray_menu()
        self.tray.show()

    @staticmethod
    def _os_prefers_dark() -> bool:
        """Ask the OS whether dark mode is enabled.
        Works reliably on Windows 10+ and macOS.  On Linux it returns
        False unless the DE exposes a colour-scheme through the Qt
        platform theme plugin (e.g. KDE 6+).
        """
        try:
            from PyQt6.QtCore import Qt
            app = QApplication.instance()
            cs = app.styleHints().colorScheme()
            if cs == Qt.ColorScheme.Dark:
                return True
            if cs == Qt.ColorScheme.Light:
                return False
        except Exception:
            pass
        # Fallback: probe the current palette brightness
        brightness = sum(QWidget().palette().color(QPalette.ColorRole.Window).getRgb()[0:3])
        return brightness < (255 * 3 / 2)

    @staticmethod
    def _make_dark_palette() -> 'QPalette':
        """Build a dark QPalette that works with the Fusion style engine.
        No stylesheet is needed — Fusion renders native borders, padding
        and button geometry using these colours directly.
        """
        from PyQt6.QtGui import QColor
        p = QPalette()
        p.setColor(QPalette.ColorRole.Window,          QColor(25, 35, 45))
        p.setColor(QPalette.ColorRole.WindowText,      QColor(208, 208, 208))
        p.setColor(QPalette.ColorRole.Base,            QColor(15, 25, 35))
        p.setColor(QPalette.ColorRole.AlternateBase,   QColor(25, 35, 45))
        p.setColor(QPalette.ColorRole.ToolTipBase,     QColor(25, 35, 45))
        p.setColor(QPalette.ColorRole.ToolTipText,     QColor(208, 208, 208))
        p.setColor(QPalette.ColorRole.Text,            QColor(208, 208, 208))
        p.setColor(QPalette.ColorRole.Button,          QColor(45, 55, 65))
        p.setColor(QPalette.ColorRole.ButtonText,      QColor(208, 208, 208))
        p.setColor(QPalette.ColorRole.BrightText,      QColor(255, 51, 51))
        p.setColor(QPalette.ColorRole.Link,            QColor(42, 130, 218))
        p.setColor(QPalette.ColorRole.Highlight,       QColor(42, 130, 218))
        p.setColor(QPalette.ColorRole.HighlightedText, QColor(0, 0, 0))
        # Disabled-state colours
        p.setColor(QPalette.ColorGroup.Disabled, QPalette.ColorRole.WindowText,  QColor(128, 128, 128))
        p.setColor(QPalette.ColorGroup.Disabled, QPalette.ColorRole.Text,        QColor(128, 128, 128))
        p.setColor(QPalette.ColorGroup.Disabled, QPalette.ColorRole.ButtonText,  QColor(128, 128, 128))
        p.setColor(QPalette.ColorGroup.Disabled, QPalette.ColorRole.Highlight,   QColor(80, 80, 80))
        p.setColor(QPalette.ColorGroup.Disabled, QPalette.ColorRole.HighlightedText, QColor(128, 128, 128))
        return p

    def reload_app_stylesheet(self):
        """Set the Qt style and palette according to the user-selected theme.

        Uses Fusion + dark QPalette instead of qdarkstyle CSS so that
        native widget geometry (padding, borders, min-height) is preserved
        identically in both light and dark modes.
        """
        theme = self.config.GUI_QT_COLOR_THEME  # 'system', 'default' (light), or 'dark'
        if theme == 'system':
            use_dark_theme = self._os_prefers_dark()
        elif theme == 'dark':
            use_dark_theme = True
        else:  # 'default' == light
            use_dark_theme = False

        from PyQt6.QtWidgets import QStyleFactory
        # Always use Fusion so palette-driven theming works in both modes.
        self.app.setStyle(QStyleFactory.create('Fusion'))
        # Clear any leftover stylesheet BEFORE setting the palette so that
        # Qt's style-sheet resolution doesn't cache stale palette colours.
        self.app.setStyleSheet('')

        if use_dark_theme:
            self.app.setPalette(self._make_dark_palette())
        else:
            self.app.setPalette(self.app.style().standardPalette())

        # Apply any necessary stylesheet patches (macOS StatusBarButton, etc.)
        patch_qt_stylesheet(use_dark_theme=use_dark_theme)
        # Even if we ourselves don't set the dark theme,
        # the OS/window manager/etc might set *a dark theme*.
        # Hence, try to choose colors accordingly:
        ColorScheme.update_from_widget(QWidget(), force_dark=use_dark_theme)

    def apply_theme_live(self):
        """Apply theme change immediately to all open windows.

        This re-applies the palette/style (instant), updates ColorScheme,
        then fully redraws every open ElectrumWindow: form-based tabs
        (Send, Receive) are rebuilt from scratch so that all widgets
        pick up the new colour scheme, and list-based tabs are refreshed.
        In-progress form content is lost in exchange for a correct redraw.
        """
        self.reload_app_stylesheet()
        new_palette = self.app.palette()
        style = self.app.style()
        for window in self.windows:
            # Force the new palette onto every existing widget so that
            # already-visible backgrounds, labels, etc. repaint immediately.
            for widget in [window] + window.findChildren(QWidget):
                widget.setPalette(new_palette)
                style.unpolish(widget)
                style.polish(widget)
            window.rebuild_form_tabs()
            window.refresh_tabs()
            # Re-apply overlay stylesheet on all OverlayControlMixin widgets
            for child in window.findChildren(QWidget):
                if hasattr(child, 'update_overlay_stylesheet'):
                    child.update_overlay_stylesheet()
            window.repaint()

    def build_tray_menu(self):
        if not self.tray:
            return
        # Avoid immediate GC of old menu when window closed via its action
        if self.tray.contextMenu() is None:
            m = QMenu()
            self.tray.setContextMenu(m)
        else:
            m = self.tray.contextMenu()
            m.clear()
        network = self.daemon.network
        m.addAction(_("Plugins"), self.show_plugins_dialog)
        if network:
            m.addAction(_("Network"), self.show_network_dialog)
        if network and network.lngossip:
            m.addAction(_("Lightning Network"), self.show_lightning_dialog)
        for window in self.windows:
            name = window.wallet.basename()
            submenu = m.addMenu(name)
            submenu.addAction(_("Show/Hide"), window.show_or_hide)
            submenu.addAction(_("Close"), window.close)
        m.addAction(_("Dark/Light"), self.toggle_tray_icon)
        m.addSeparator()
        m.addAction(_("Exit Electrin"), self.app.quit)

    def tray_icon(self):
        if self.dark_icon:
            return read_QIcon('electrum_dark_icon.png')
        else:
            return read_QIcon('electrum_light_icon.png')

    def toggle_tray_icon(self):
        if not self.tray:
            return
        self.dark_icon = not self.dark_icon
        self.config.GUI_QT_DARK_TRAY_ICON = self.dark_icon
        self.tray.setIcon(self.tray_icon())

    def tray_activated(self, reason):
        if reason == QSystemTrayIcon.ActivationReason.DoubleClick:
            if all([w.is_hidden() for w in self.windows]):
                for w in self.windows:
                    w.bring_to_top()
            else:
                for w in self.windows:
                    w.hide()

    def _cleanup_before_exit(self):
        if self._cleaned_up:
            return
        self._cleaned_up = True
        self.app.new_window_signal.disconnect()
        self.app.removeEventFilter(self.open_file_efilter)
        self.open_file_efilter = None
        # it is save to remove the filter, even if it has not been installed
        self.app.removeEventFilter(self.screenshot_protection_efilter)
        self.screenshot_protection_efilter = None
        # If there are still some open windows, try to clean them up.
        for window in list(self.windows):
            window.close()
            window.clean_up()
        if self.network_dialog:
            self.network_dialog.close()
            self.network_dialog = None
        if self.lightning_dialog:
            self.lightning_dialog.close()
            self.lightning_dialog = None
        # clipboard persistence. see http://www.mail-archive.com/pyqt@riverbankcomputing.com/msg17328.html
        event = QtCore.QEvent(QtCore.QEvent.Type.Clipboard)
        self.app.sendEvent(self.app.clipboard(), event)
        if self.tray:
            self.tray.hide()
            self.tray.deleteLater()
            self.tray = None

    def _maybe_quit_if_no_windows_open(self) -> None:
        """Check if there are any open windows and decide whether we should quit."""
        # keep daemon running after close
        if self.config.get('daemon'):
            return
        # check if a wizard is in progress
        with self._num_wizards_lock:
            if self._num_wizards_in_progress > 0 or len(self.windows) > 0:
                return
        self.app.quit()

    def new_window(self, path, uri=None):
        # Use a signal as can be called from daemon thread
        self.app.new_window_signal.emit(path, uri)

    def show_lightning_dialog(self):
        if not self.daemon.network.has_channel_db():
            return
        if not self.lightning_dialog:
            self.lightning_dialog = LightningDialog(self)
        self.lightning_dialog.bring_to_top()

    def show_plugins_dialog(self):
        from .plugins_dialog import PluginsDialog
        d = PluginsDialog(self.config, self.plugins, gui_object=self)
        d.exec()

    def show_network_dialog(self, proxy_tab=False):
        if self.network_dialog:
            self.network_dialog.show(proxy_tab=proxy_tab)
            self.network_dialog.raise_()
            return
        self.network_dialog = NetworkDialog(network=self.daemon.network)
        self.network_dialog.show(proxy_tab=proxy_tab)

    def _create_window_for_wallet(self, wallet):
        w = ElectrumWindow(self, wallet)
        self.windows.append(w)
        self.build_tray_menu()
        w.warn_if_testnet()
        w.warn_if_hardware_wallet()
        w.warn_if_watching_only()
        return w

    def count_wizards_in_progress(func):
        def wrapper(self: 'ElectrumGui', *args, **kwargs):
            with self._num_wizards_lock:
                self._num_wizards_in_progress += 1
            try:
                return func(self, *args, **kwargs)
            finally:
                with self._num_wizards_lock:
                    self._num_wizards_in_progress -= 1
                self._maybe_quit_if_no_windows_open()
        return wrapper

    def get_window_for_wallet(self, wallet):
        for window in self.windows:
            if window.wallet.storage.path == wallet.storage.path:
                return window

    @count_wizards_in_progress
    def start_new_window(
            self,
            path,
            uri: Optional[str],
            *,
            app_is_starting: bool = False,
            force_wizard: bool = False,
    ) -> Optional[ElectrumWindow]:
        """Raises the window for the wallet if it is open.
        Otherwise, opens the wallet and creates a new window for it.
        Warning: the returned window might be for a completely different wallet
                 than the provided path, as we allow user interaction to change the path.
        """
        if not self.has_accepted_terms_of_use():
            self.logger.warning(f"terms of use not accepted, rejecting to start new window")
            return None

        wallet = None
        # Try to open with daemon first. If this succeeds, there won't be a wizard at all
        # (the wallet main window will appear directly).
        if not force_wizard:
            try:
                wallet = self.daemon.load_wallet(path, None)
            except FileNotFoundError:
                pass  # open with wizard below
            except InvalidPassword:
                pass  # open with wizard below
            except WalletRequiresSplit:
                pass  # open with wizard below
            except WalletRequiresUpgrade:
                pass  # open with wizard below
            except WalletUnfinished:
                pass  # open with wizard below
            except Exception as e:
                self.logger.exception('')
                err_text = str(e) if isinstance(e, WalletFileException) else repr(e)
                custom_message_box(icon=QMessageBox.Icon.Warning,
                                   parent=None,
                                   title=_('Error'),
                                   text=_('Cannot load wallet') + ' (1):\n' + err_text)
                if isinstance(e, WalletFileException) and e.should_report_crash:
                    send_exception_to_crash_reporter(e)
                # if app is starting, still let wizard appear
                if not app_is_starting:
                    return
        # Open a wizard window. This lets the user e.g. enter a password, or select
        # a different wallet.
        try:
            if not wallet:
                wallet = self._start_wizard_to_select_or_create_wallet(path)
            if not wallet:
                return
            window = self.get_window_for_wallet(wallet)
            # create or raise window
            if not window:
                window = self._create_window_for_wallet(wallet)
        except UserCancelled:
            return
        except Exception as e:
            self.logger.exception('')
            if isinstance(e, UserFacingException) \
                    or isinstance(e, WalletFileException) and not e.should_report_crash:
                err_text = str(e) if isinstance(e, WalletFileException) else repr(e)
                custom_message_box(icon=QMessageBox.Icon.Warning,
                                   parent=None,
                                   title=_('Error'),
                                   text=_('Cannot load wallet') + '(2) :\n' + err_text)
            else:
                send_exception_to_crash_reporter(e)
            if app_is_starting:
                # If we raise in this context, there are no more fallbacks, we will shut down.
                # Worst case scenario, we might have gotten here without user interaction,
                # in which case, if we raise now without user interaction, the same sequence of
                # events is likely to repeat when the user restarts the process.
                # So we play it safe: clear path, clear uri, force a wizard to appear.
                try:
                    wallet_dir = os.path.dirname(path)
                    filename = get_new_wallet_name(wallet_dir)
                except OSError:
                    path = self.config.get_fallback_wallet_path()
                else:
                    path = os.path.join(wallet_dir, filename)
                return self.start_new_window(path, uri=None, force_wizard=True)
            return
        window.bring_to_top()
        window.setWindowState(window.windowState() & ~Qt.WindowState.WindowMinimized | Qt.WindowState.WindowActive)
        window.activateWindow()
        if uri:
            window.show_send_tab()
            # Handle URI defensively - local attacker with access to RPC server and config file could get here:
            #   - tell user something happened
            window.notify(_("Updated 'Pay To' field to handle external URI"))
            #   - clear all fields in Send tab:
            #     - perhaps user was just filling out the fields, trying to make another payment.
            #       e.g. if the given URI does not have an amount, we should clear the amount field
            window.send_tab.do_clear()
            #   - update "Pay To" field (and maybe others)
            window.send_tab.set_payment_identifier(uri)
        return window

    def _start_wizard_to_select_or_create_wallet(self, path) -> Optional[Abstract_Wallet]:
        wizard = QENewWalletWizard(self.config, self.app, self.plugins, self.daemon, path)
        result = wizard.exec()
        # TODO: use dialog.open() instead to avoid new event loop spawn?
        self.logger.info(f'wizard dialog exec result={result}')
        if result == QDialog.DialogCode.Rejected:
            self.logger.info('wizard dialog cancelled by user')
            return

        d = wizard.get_wizard_data()

        if d['wallet_is_open']:
            wallet_path = standardize_path(d['wallet_name'])
            for window in self.windows:
                if window.wallet.storage.path == wallet_path:
                    return window.wallet
            raise Exception('found by wizard but not here?!')

        if not d['wallet_exists']:
            self.logger.info('about to create wallet')
            wizard.create_storage()
            if d['wallet_type'] == '2fa' and 'x3' not in d:
                return
            wallet_file = wizard.path
        else:
            wallet_file = d['wallet_name']

        password = d.get('password') or None  # convert '' to None

        try:
            wallet = self.daemon.load_wallet(wallet_file, password, upgrade=True)
            return wallet
        except WalletRequiresSplit as e:
            wizard.run_split(wallet_file, e._split_data)
            return
        except WalletUnfinished as e:
            # wallet creation is not complete, 2fa online phase
            db = e._wallet_db
            action = db.get_action()
            assert action[1] == 'accept_terms_of_use', 'only support for resuming trustedcoin split setup'
            k1 = load_keystore(db, 'x1')
            if password is not None:
                xprv = k1.get_master_private_key(password)
            else:
                xprv = db.get('x1')['xprv']
                if not is_xprv(xprv):
                    xprv = k1
            _wiz_data_updates = {
                'wallet_name': wallet_file,
                'xprv1': xprv,
                'xpub1': db.get('x1')['xpub'],
                'xpub2': db.get('x2')['xpub'],
            }
            data = {**d, **_wiz_data_updates}
            wizard = QENewWalletWizard(self.config, self.app, self.plugins, self.daemon, path,
                                       start_viewstate=WizardViewState('trustedcoin_tos', data, {}))
            result = wizard.exec()
            if result == QDialog.DialogCode.Rejected:
                self.logger.info('wizard dialog cancelled by user')
                return
            db.put('x3', wizard.get_wizard_data()['x3'])
            db.write_and_force_consolidation()  # TODO API for db is a bit weird: there should be a close method

        wallet = self.daemon.load_wallet(wallet_file, password, upgrade=True)
        return wallet

    def close_window(self, window: ElectrumWindow):
        if window in self.windows:
            self.windows.remove(window)
        self.build_tray_menu()
        run_hook('on_close_window', window)
        if window.should_stop_wallet_on_close:
            self.daemon.stop_wallet(window.wallet.storage.path)

    def reload_window(self, window):
        # bump counter so that we do not close the app
        self._num_wizards_in_progress += 1
        wallet = window.wallet
        window.should_stop_wallet_on_close = False
        window.close()
        self._create_window_for_wallet(wallet)
        self._num_wizards_in_progress -= 1

    def reload_windows(self):
        for window in list(self.windows):
            self.reload_window(window)

    def has_accepted_terms_of_use(self) -> bool:
        if self.config.TERMS_OF_USE_ACCEPTED >= TERMS_OF_USE_LATEST_VERSION\
                or constants.net.NET_NAME == "regtest":
            return True
        return False

    def ask_terms_of_use(self):
        """Ask the user to accept the terms of use.
        This is only shown if the user has not accepted them yet.
        """
        if self.has_accepted_terms_of_use():
            return
        from electrum.gui.qt.wizard.terms_of_use import QETermsOfUseWizard
        dialog = QETermsOfUseWizard(self.config, self.app)
        result = dialog.exec()
        if result == QDialog.DialogCode.Rejected:
            self.logger.info('terms of use not accepted by user')
            raise UserCancelled()

    def init_network(self):
        """Start the network, including showing a first-start network dialog if config does not exist."""
        if self.daemon.network:
            # first-start network-setup
            if not self.config.cv.NETWORK_AUTO_CONNECT.is_set():
                dialog = QEServerConnectWizard(self.config, self.app, self.plugins, self.daemon)
                result = dialog.exec()
                if result == QDialog.DialogCode.Rejected:
                    self.logger.info('network wizard dialog cancelled by user')
                    raise UserCancelled()

            # start network
            self.daemon.start_network()

    def main(self):
        # setup Ctrl-C handling and tear-down code first, so that user can easily exit whenever
        self.app.setQuitOnLastWindowClosed(False)  # so _we_ can decide whether to quit
        self.app.lastWindowClosed.connect(self._maybe_quit_if_no_windows_open)
        self.app.aboutToQuit.connect(self._cleanup_before_exit)
        signal.signal(signal.SIGINT, lambda *args: self.app.quit())
        # hook for crash reporter
        Exception_Hook.maybe_setup(config=self.config)
        # start network, and maybe show first-start network-setup
        try:
            self.ask_terms_of_use()
            self.init_network()
        except UserCancelled:
            return
        except Exception as e:
            self.logger.exception('')
            return
        # start wizard to select/create wallet
        path = self.config.get_wallet_path()
        try:
            if not self.start_new_window(path, self.config.get('url'), app_is_starting=True):
                return
        except Exception as e:
            self.logger.error("error loading wallet (or creating window for it)")
            send_exception_to_crash_reporter(e)
            # Let Qt event loop start properly so that crash reporter window can appear.
            # We will shutdown when the user closes that window, via lastWindowClosed signal.
        # main loop
        self.logger.info("starting Qt main loop")
        self.app.exec()
        # on some platforms the exec_ call may not return, so use _cleanup_before_exit

    def stop(self):
        self.logger.info('closing GUI')
        self.app.quit_signal.emit()

    @classmethod
    def version_info(cls):
        ret = {
            "qt.version": QtCore.QT_VERSION_STR,
            "pyqt.version": QtCore.PYQT_VERSION_STR,
        }
        if hasattr(PyQt6, "__path__"):
            ret["pyqt.path"] = ", ".join(PyQt6.__path__ or [])
        return ret

    def do_copy(self, text: str, *, title: str = None) -> None:
        self.app.clipboard().setText(text)
        message = _("Text copied to Clipboard") if title is None else _("{} copied to Clipboard").format(title)
        # tooltip cannot be displayed immediately when called from a menu; wait 200ms
        QTimer.singleShot(200, lambda: QToolTip.showText(QCursor.pos(), message, None))


def standalone_exception_dialog(exception: Union[str, BaseException]) -> None:
    app = QApplication.instance()
    if not app:
        app = QApplication([])

    msg_box = QMessageBox()
    msg_box.setWindowTitle(_("Error starting Electrin"))
    msg_box.setIcon(QMessageBox.Icon.Critical)
    msg_box.setText(_("An error occurred") + ":")
    msg_box.setInformativeText(str(exception))

    # Add detailed traceback if available
    if hasattr(exception, "__traceback__"):
        import traceback
        detailed_text = ''.join(traceback.format_exception(
            type(exception), exception, exception.__traceback__)
        )
        msg_box.setDetailedText(detailed_text)

    msg_box.exec()
