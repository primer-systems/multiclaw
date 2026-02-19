"""
Wallet package - Secure key management for MultiClaw.

Contains:
- Wallet: HD wallet with BIP-39/44 derivation
- PrivateKeyWallet: Single-key wallet
- WalletManager: Multi-wallet support
- WalletIndex, WalletInfo: Wallet metadata tracking
- Dialogs: UI for wallet setup and management
"""

from .crypto import (
    Wallet,
    PrivateKeyWallet,
    WalletAddress,
    load_wallet,
    is_wallet_encrypted,
    encrypt_seed,
    decrypt_seed,
    NO_PASSWORD_SENTINEL,
    # New multi-seed wallet
    MultiClawWallet,
    SeedEntry,
    AddressEntry,
)
from .manager import (
    WalletManager,
    WalletIndex,
    WalletInfo,
    MAX_WALLETS,
)
from .dialogs import (
    WelcomeDialog,
    PasswordSetupDialog,
    ImportChoiceDialog,
    SeedImportDialog,
    PrivateKeyImportDialog,
    SeedBackupDialog,
    UnlockDialog,
    run_wallet_setup,
    # New multi-seed wallet dialogs
    AddAddressDialog,
    SeedSelectionDialog,
    DerivationBrowserDialog,
    NewSeedDialog,
    ImportSeedToWalletDialog,
    ImportPrivateKeyToWalletDialog,
    MultiClawWalletUnlockDialog,
    CreateWalletWizard,
    # Wallet file management dialogs
    AddWalletChoiceDialog,
    WalletFilenameDialog,
)

__all__ = [
    # Crypto
    "Wallet",
    "PrivateKeyWallet",
    "WalletAddress",
    "load_wallet",
    "is_wallet_encrypted",
    "encrypt_seed",
    "decrypt_seed",
    "NO_PASSWORD_SENTINEL",
    # New multi-seed wallet
    "MultiClawWallet",
    "SeedEntry",
    "AddressEntry",
    # Manager
    "WalletManager",
    "WalletIndex",
    "WalletInfo",
    "MAX_WALLETS",
    # Dialogs
    "WelcomeDialog",
    "PasswordSetupDialog",
    "ImportChoiceDialog",
    "SeedImportDialog",
    "PrivateKeyImportDialog",
    "SeedBackupDialog",
    "UnlockDialog",
    "run_wallet_setup",
    # New multi-seed wallet dialogs
    "AddAddressDialog",
    "SeedSelectionDialog",
    "DerivationBrowserDialog",
    "NewSeedDialog",
    "ImportSeedToWalletDialog",
    "ImportPrivateKeyToWalletDialog",
    "MultiClawWalletUnlockDialog",
    "CreateWalletWizard",
    # Wallet file management dialogs
    "AddWalletChoiceDialog",
    "WalletFilenameDialog",
]
