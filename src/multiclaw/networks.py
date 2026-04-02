"""
MultiClaw Networks - Chain configurations and balance fetching

Supports Ethereum, Base, and SKALE networks.
"""

from dataclasses import dataclass
from typing import Optional
from web3 import Web3
from web3.exceptions import Web3Exception

# ============================================
# Network Configurations
# ============================================

@dataclass
class NetworkConfig:
    """Configuration for a blockchain network."""
    chain_id: int
    name: str
    display_name: str
    rpc_url: str
    explorer_url: str
    is_testnet: bool
    native_symbol: str
    native_decimals: int = 18


# Supported networks (ordered by market cap: Ethereum > Base > SKALE)
NETWORKS = {
    # === ETHEREUM ===
    # Ethereum Mainnet
    1: NetworkConfig(
        chain_id=1,
        name="ethereum",
        display_name="Ethereum",
        rpc_url="https://ethereum-rpc.publicnode.com",
        explorer_url="https://etherscan.io",
        is_testnet=False,
        native_symbol="ETH",
    ),
    # Ethereum Sepolia Testnet
    11155111: NetworkConfig(
        chain_id=11155111,
        name="ethereum-sepolia",
        display_name="Ethereum Sepolia",
        rpc_url="https://ethereum-sepolia-rpc.publicnode.com",
        explorer_url="https://sepolia.etherscan.io",
        is_testnet=True,
        native_symbol="ETH",
    ),
    # === BASE ===
    # Base Mainnet
    8453: NetworkConfig(
        chain_id=8453,
        name="base",
        display_name="Base",
        rpc_url="https://base.publicnode.com",
        explorer_url="https://basescan.org",
        is_testnet=False,
        native_symbol="ETH",
    ),
    # Base Sepolia Testnet
    84532: NetworkConfig(
        chain_id=84532,
        name="base-sepolia",
        display_name="Base Sepolia",
        rpc_url="https://sepolia.base.org",
        explorer_url="https://sepolia.basescan.org",
        is_testnet=True,
        native_symbol="ETH",
    ),
    # === SKALE ===
    # SKALE Base Mainnet
    1187947933: NetworkConfig(
        chain_id=1187947933,
        name="skale-base",
        display_name="SKALE Base",
        rpc_url="https://skale-base.skalenodes.com/v1/base",
        explorer_url="https://skale-base-explorer.skalenodes.com",
        is_testnet=False,
        native_symbol="CREDIT",
    ),
    # SKALE Base Sepolia Testnet
    324705682: NetworkConfig(
        chain_id=324705682,
        name="skale-base-sepolia",
        display_name="SKALE Base Sepolia",
        rpc_url="https://base-sepolia-testnet.skalenodes.com/v1/jubilant-horrible-ancha",
        explorer_url="https://base-sepolia-testnet-explorer.skalenodes.com",
        is_testnet=True,
        native_symbol="CREDIT",
    ),
}

# Default network
DEFAULT_NETWORK = 324705682  # SKALE Base Sepolia for development


# ============================================
# Token Configurations
# ============================================

@dataclass
class TokenConfig:
    """Configuration for an ERC-20 token."""
    symbol: str
    name: str
    decimals: int
    addresses: dict[int, str]  # chain_id -> contract address


# Known tokens
TOKENS = {
    "USDC": TokenConfig(
        symbol="USDC",
        name="USD Coin",
        decimals=6,
        addresses={
            # Ethereum
            1: "0xA0b86991c6218b36c1d19D4a2e9Eb0cE3606eB48",           # Ethereum Mainnet
            11155111: "0x1c7D4B196Cb0C7B01d743Fbc6116a902379C7238",    # Ethereum Sepolia
            # Base
            8453: "0x833589fCD6eDb6E08f4c7C32D4f71b54bdA02913",        # Base Mainnet
            84532: "0x036CbD53842c5426634e7929541eC2318f3dCF7e",       # Base Sepolia
            # SKALE
            1187947933: "0x85889c8c714505E0c94b30fcfcF64fE3Ac8FCb20",  # SKALE Base
            324705682: "0x2e08028E3C4c2356572E096d8EF835cD5C6030bD",   # SKALE Base Sepolia
        }
    ),
}

# Minimal ERC-20 ABI for balance checking
ERC20_ABI = [
    {
        "constant": True,
        "inputs": [{"name": "_owner", "type": "address"}],
        "name": "balanceOf",
        "outputs": [{"name": "balance", "type": "uint256"}],
        "type": "function"
    },
    {
        "constant": True,
        "inputs": [],
        "name": "decimals",
        "outputs": [{"name": "", "type": "uint8"}],
        "type": "function"
    },
    {
        "constant": True,
        "inputs": [],
        "name": "symbol",
        "outputs": [{"name": "", "type": "string"}],
        "type": "function"
    },
]


# ============================================
# Balance Fetching
# ============================================

@dataclass
class Balance:
    """A token or native balance."""
    symbol: str
    name: str
    raw: int           # Raw balance in smallest unit
    decimals: int
    formatted: float   # Human-readable balance
    usd_value: Optional[float] = None  # USD value if available
    fetch_failed: bool = False  # True if RPC call failed (vs confirmed zero)


class BalanceFetcher:
    """Fetches balances from blockchain networks."""

    def __init__(self, network: NetworkConfig, rpc_url: Optional[str] = None):
        """
        Initialize balance fetcher.

        Args:
            network: Network configuration
            rpc_url: Custom RPC URL, or None to use network default
        """
        self.network = network
        effective_rpc = rpc_url if rpc_url else network.rpc_url
        self.w3 = Web3(Web3.HTTPProvider(effective_rpc))

    @property
    def is_connected(self) -> bool:
        """Check if connected to the network."""
        try:
            return self.w3.is_connected()
        except Exception:
            return False

    def get_native_balance(self, address: str) -> Balance:
        """Get native token balance (ETH on Base)."""
        try:
            address = Web3.to_checksum_address(address)
            raw_balance = self.w3.eth.get_balance(address)
            formatted = raw_balance / (10 ** self.network.native_decimals)

            return Balance(
                symbol=self.network.native_symbol,
                name=f"{self.network.native_symbol} ({self.network.display_name})",
                raw=raw_balance,
                decimals=self.network.native_decimals,
                formatted=formatted,
                fetch_failed=False,
            )
        except Exception as e:
            # Mark as fetch failed, not confirmed zero
            return Balance(
                symbol=self.network.native_symbol,
                name=f"{self.network.native_symbol} ({self.network.display_name})",
                raw=0,
                decimals=self.network.native_decimals,
                formatted=0.0,
                fetch_failed=True,
            )

    def get_token_balance(self, address: str, token: TokenConfig) -> Optional[Balance]:
        """Get ERC-20 token balance."""
        # Check if token is deployed on this network
        if self.network.chain_id not in token.addresses:
            return None

        try:
            address = Web3.to_checksum_address(address)
            token_address = Web3.to_checksum_address(token.addresses[self.network.chain_id])

            contract = self.w3.eth.contract(address=token_address, abi=ERC20_ABI)
            raw_balance = contract.functions.balanceOf(address).call()
            formatted = raw_balance / (10 ** token.decimals)

            return Balance(
                symbol=token.symbol,
                name=token.name,
                raw=raw_balance,
                decimals=token.decimals,
                formatted=formatted,
                fetch_failed=False,
            )
        except Exception:
            # Mark as fetch failed, not confirmed zero
            return Balance(
                symbol=token.symbol,
                name=token.name,
                raw=0,
                decimals=token.decimals,
                formatted=0.0,
                fetch_failed=True,
            )

    def get_all_balances(self, address: str) -> list[Balance]:
        """Get all balances (native + known tokens)."""
        balances = []

        # Native balance
        balances.append(self.get_native_balance(address))

        # Token balances
        for token in TOKENS.values():
            balance = self.get_token_balance(address, token)
            if balance is not None:
                balances.append(balance)

        return balances


class MultiNetworkBalanceFetcher:
    """Fetches balances across multiple networks."""

    def __init__(
        self,
        networks: Optional[list[int]] = None,
        custom_rpcs: Optional[dict[int, str]] = None
    ):
        """
        Initialize with specific networks or use all.

        Args:
            networks: List of chain IDs to use, or None for all
            custom_rpcs: Dict of chain_id -> custom RPC URL (optional)
        """
        if networks is None:
            networks = list(NETWORKS.keys())

        custom_rpcs = custom_rpcs or {}

        self.fetchers = {
            chain_id: BalanceFetcher(NETWORKS[chain_id], custom_rpcs.get(chain_id))
            for chain_id in networks
            if chain_id in NETWORKS
        }

    def get_all_balances(self, address: str) -> dict[int, list[Balance]]:
        """
        Get balances across all networks.

        Returns: Dict of chain_id -> list of balances
        """
        results = {}
        for chain_id, fetcher in self.fetchers.items():
            results[chain_id] = fetcher.get_all_balances(address)
        return results


# ============================================
# Utility Functions
# ============================================

def get_network(chain_id: int) -> Optional[NetworkConfig]:
    """Get network config by chain ID."""
    return NETWORKS.get(chain_id)


def get_network_by_name(name: str) -> Optional[NetworkConfig]:
    """Get network config by name."""
    for network in NETWORKS.values():
        if network.name == name:
            return network
    return None


def format_address(address: str, chars: int = 4) -> str:
    """Format address as 0x1234...5678"""
    if len(address) <= chars * 2 + 2:
        return address
    return f"{address[:chars+2]}...{address[-chars:]}"
