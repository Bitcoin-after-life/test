#!/usr/bin/env python3
import json
import os
import sys

from bal_wallet_utils import fix_will_settings_tx_fees, save, uninstall_bal
from electrum.storage import WalletStorage
from PyQt6.QtWidgets import (
    QApplication,
    QFileDialog,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QMainWindow,
    QPushButton,
    QTextEdit,
    QVBoxLayout,
    QWidget,
)


class WalletUtilityGUI(QMainWindow):
    def __init__(self):
        super().__init__()
        self.init_ui()

    def init_ui(self):
        self.setWindowTitle("BAL Wallet Utility")
        self.setFixedSize(500, 400)

        # Central widget
        central_widget = QWidget()
        self.setCentralWidget(central_widget)

        # Main layout
        layout = QVBoxLayout(central_widget)

        # Wallet input group
        wallet_group = QGroupBox("Wallet Settings")
        wallet_layout = QVBoxLayout(wallet_group)

        # Wallet path
        wallet_path_layout = QHBoxLayout()
        wallet_path_layout.addWidget(QLabel("Wallet Path:"))
        self.wallet_path_edit = QLineEdit()
        self.wallet_path_edit.setPlaceholderText("Select wallet path...")
        wallet_path_layout.addWidget(self.wallet_path_edit)

        self.browse_btn = QPushButton("Browse...")
        self.browse_btn.clicked.connect(self.browse_wallet)
        wallet_path_layout.addWidget(self.browse_btn)

        wallet_layout.addLayout(wallet_path_layout)

        # Password
        password_layout = QHBoxLayout()
        password_layout.addWidget(QLabel("Password:"))
        self.password_edit = QLineEdit()
        self.password_edit.setEchoMode(QLineEdit.EchoMode.Password)
        self.password_edit.setPlaceholderText("Enter password (if encrypted)")
        password_layout.addWidget(self.password_edit)

        wallet_layout.addLayout(password_layout)

        layout.addWidget(wallet_group)

        # Output area
        output_group = QGroupBox("Output")
        output_layout = QVBoxLayout(output_group)

        self.output_text = QTextEdit()
        self.output_text.setReadOnly(True)
        output_layout.addWidget(self.output_text)

        layout.addWidget(output_group)

        # Action buttons
        buttons_layout = QHBoxLayout()

        self.fix_btn = QPushButton("Fix")
        self.fix_btn.clicked.connect(self.fix_wallet)
        self.fix_btn.setEnabled(False)
        buttons_layout.addWidget(self.fix_btn)

        self.uninstall_btn = QPushButton("Uninstall")
        self.uninstall_btn.clicked.connect(self.uninstall_wallet)
        self.uninstall_btn.setEnabled(False)
        buttons_layout.addWidget(self.uninstall_btn)

        layout.addLayout(buttons_layout)

        # Connections to enable buttons when path is entered
        self.wallet_path_edit.textChanged.connect(self.check_inputs)

    def browse_wallet(self):
        file_path, _ = QFileDialog.getOpenFileName(
            self, "Select Wallet", "*", "Electrum Wallet (*)"
        )
        if file_path:
            self.wallet_path_edit.setText(file_path)

    def check_inputs(self):
        wallet_path = self.wallet_path_edit.text().strip()
        has_path = bool(wallet_path) and os.path.exists(wallet_path)

        self.fix_btn.setEnabled(has_path)
        self.uninstall_btn.setEnabled(has_path)

    def log_message(self, message):
        self.output_text.append(message)

    def fix_wallet(self):
        self.process_wallet("fix")

    def uninstall_wallet(self):
        self.log_message(
            "WARNING: This will remove all BAL settings. This operation cannot be undone."
        )
        self.process_wallet("uninstall")

    def process_wallet(self, command):
        wallet_path = self.wallet_path_edit.text().strip()
        password = self.password_edit.text()

        if not wallet_path:
            self.log_message("ERROR: Please enter wallet path")
            return

        if not os.path.exists(wallet_path):
            self.log_message("ERROR: Wallet not found")
            return

        try:
            self.log_message(f"Processing wallet: {wallet_path}")

            storage = WalletStorage(wallet_path)

            # Decrypt if necessary
            if storage.is_encrypted():
                if not password:
                    self.log_message(
                        "ERROR: Wallet is encrypted, please enter password"
                    )
                    return

                try:
                    storage.decrypt(password)
                    self.log_message("Wallet decrypted successfully")
                except Exception as e:
                    self.log_message(f"ERROR: Wrong password: {str(e)}")
                    return

            # Read wallet
            data = storage.read()
            json_wallet = json.loads("[" + data + "]")[0]

            have_to_save = False
            message = ""

            if command == "fix":
                have_to_save = fix_will_settings_tx_fees(json_wallet)
                message = (
                    "Fix applied successfully" if have_to_save else "No fix needed"
                )

            elif command == "uninstall":
                have_to_save = uninstall_bal(json_wallet)
                message = (
                    "BAL uninstalled successfully"
                    if have_to_save
                    else "No BAL settings found to uninstall"
                )

            if have_to_save:
                try:
                    save(json_wallet, storage)
                    self.log_message(f"SUCCESS: {message}")
                except Exception as e:
                    self.log_message(f"Save error: {str(e)}")
            else:
                self.log_message(f"INFO: {message}")

        except Exception as e:
            error_msg = f"ERROR: Processing failed: {str(e)}"
            self.log_message(error_msg)


def main():
    app = QApplication(sys.argv)

    window = WalletUtilityGUI()
    window.show()

    return app.exec()


if __name__ == "__main__":
    sys.exit(main())
