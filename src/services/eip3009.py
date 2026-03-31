# EIP-3009 Payment Signing for x402
# Self-contained implementation - no external SDK dependencies
# https://eips.ethereum.org/EIPS/eip-3009

import secrets
import time
from typing import Dict, Any, Optional
from dataclasses import dataclass

from eth_account import Account
from eth_account.messages import encode_typed_data
from web3 import Web3


# x402 protocol version
X402_VERSION = 2


@dataclass
class PaymentRequirements:
    """Parsed payment requirements from a 402 response."""
    scheme: str
    network: str  # CAIP-2 format (e.g., 'eip155:8453')
    chain_id: int
    max_amount_required: str
    asset: str
    pay_to: str
    resource: Optional[str] = None
    token_name: Optional[str] = None
    token_version: Optional[str] = None


def parse_caip_network(network: str) -> int:
    """
    Extract chain ID from CAIP-2 network identifier.

    Args:
        network: CAIP-2 format like 'eip155:8453' or just chain ID like '8453'

    Returns:
        Chain ID as integer
    """
    if network.startswith("eip155:"):
        return int(network.split(":")[1])
    # Assume it's just a chain ID
    return int(network)


def to_caip_network(network: str) -> str:
    """
    Ensure network is in CAIP-2 format.

    Args:
        network: Network identifier (may or may not have eip155: prefix)

    Returns:
        CAIP-2 format string
    """
    if network.startswith("eip155:"):
        return network
    # Legacy name mapping for common networks
    legacy_map = {
        "ethereum": "eip155:1",
        "ethereum-sepolia": "eip155:11155111",
        "sepolia": "eip155:11155111",  # alias
        "base": "eip155:8453",
        "base-sepolia": "eip155:84532",
        "skale-base": "eip155:1187947933",
        "skale-base-sepolia": "eip155:324705682",
    }
    if network.lower() in legacy_map:
        return legacy_map[network.lower()]
    # Assume it's a chain ID
    try:
        chain_id = int(network)
        return f"eip155:{chain_id}"
    except ValueError:
        # Return as-is, let it fail later with a clear error
        return network


def parse_payment_requirements(x402_data: Dict[str, Any]) -> PaymentRequirements:
    """
    Parse x402 v2 payment requirements.

    Args:
        x402_data: The x402 response data with 'accepts' array

    Returns:
        PaymentRequirements object

    Raises:
        ValueError: If data is invalid or unsupported
    """
    version = x402_data.get("x402Version")
    if version != 2:
        raise ValueError(f"Unsupported x402 version: {version}. Expected 2.")

    accepts = x402_data.get("accepts", [])
    if not accepts:
        raise ValueError("No payment options in accepts array")

    # Use first accepted payment option
    req = accepts[0]
    network = req.get("network", "")

    # Normalize to CAIP-2
    caip_network = to_caip_network(network)
    chain_id = parse_caip_network(caip_network)

    # Extract token metadata from 'extra' field if available
    extra = req.get("extra", {})
    token_name = extra.get("name")
    token_version = extra.get("version")

    return PaymentRequirements(
        scheme=req.get("scheme", "exact"),
        network=caip_network,
        chain_id=chain_id,
        max_amount_required=str(req.get("maxAmountRequired", "0")),
        asset=req.get("asset", ""),
        pay_to=req.get("payTo", ""),
        resource=req.get("resource"),
        token_name=token_name,
        token_version=token_version
    )


def sign_transfer_authorization(
    private_key: str,
    chain_id: int,
    token_address: str,
    token_name: str,
    token_version: str,
    from_address: str,
    to_address: str,
    value: int,
    valid_after: int,
    valid_before: int,
    nonce: bytes
) -> str:
    """
    Sign an EIP-3009 TransferWithAuthorization message.

    This creates a signature that authorizes a transfer of tokens
    from one address to another, without requiring gas from the sender.

    Args:
        private_key: Hex-encoded private key (with or without 0x prefix)
        chain_id: EVM chain ID
        token_address: ERC-20 token contract address
        token_name: Token name (for EIP-712 domain)
        token_version: Token version (for EIP-712 domain)
        from_address: Address tokens are transferred from
        to_address: Address tokens are transferred to
        value: Amount in token's smallest unit
        valid_after: Unix timestamp after which the authorization is valid
        valid_before: Unix timestamp before which the authorization is valid
        nonce: 32-byte random nonce

    Returns:
        Hex-encoded signature with 0x prefix
    """
    # Ensure private key has 0x prefix
    if not private_key.startswith("0x"):
        private_key = "0x" + private_key

    account = Account.from_key(private_key)

    # EIP-712 typed data structure for TransferWithAuthorization
    typed_data = {
        "types": {
            "EIP712Domain": [
                {"name": "name", "type": "string"},
                {"name": "version", "type": "string"},
                {"name": "chainId", "type": "uint256"},
                {"name": "verifyingContract", "type": "address"},
            ],
            "TransferWithAuthorization": [
                {"name": "from", "type": "address"},
                {"name": "to", "type": "address"},
                {"name": "value", "type": "uint256"},
                {"name": "validAfter", "type": "uint256"},
                {"name": "validBefore", "type": "uint256"},
                {"name": "nonce", "type": "bytes32"}
            ]
        },
        "primaryType": "TransferWithAuthorization",
        "domain": {
            "name": token_name,
            "version": token_version,
            "chainId": chain_id,
            "verifyingContract": Web3.to_checksum_address(token_address)
        },
        "message": {
            "from": Web3.to_checksum_address(from_address),
            "to": Web3.to_checksum_address(to_address),
            "value": value,
            "validAfter": valid_after,
            "validBefore": valid_before,
            "nonce": nonce
        }
    }

    # Encode and sign
    encoded = encode_typed_data(full_message=typed_data)
    signed = account.sign_message(encoded)

    # Return signature with 0x prefix
    sig_hex = signed.signature.hex()
    if not sig_hex.startswith("0x"):
        sig_hex = "0x" + sig_hex
    return sig_hex


def create_payment(
    private_key: str,
    requirements: PaymentRequirements,
    token_name: Optional[str] = None,
    token_version: Optional[str] = None
) -> Dict[str, Any]:
    """
    Create a signed x402 v2 payment payload.

    Args:
        private_key: Hex-encoded private key
        requirements: Parsed payment requirements
        token_name: Token name (defaults to requirements or 'USD Coin')
        token_version: Token version (defaults to requirements or '2')

    Returns:
        x402 v2 payment payload ready for PAYMENT-SIGNATURE header
    """
    # Ensure private key format
    if not private_key.startswith("0x"):
        private_key = "0x" + private_key

    account = Account.from_key(private_key)
    from_address = account.address

    # Use provided token metadata, fall back to requirements, then defaults
    # USDC uses 'USD Coin' name and version '2'
    name = token_name or requirements.token_name or "USD Coin"
    version = token_version or requirements.token_version or "2"

    # Generate random nonce (32 bytes)
    nonce_bytes = secrets.token_bytes(32)
    nonce_hex = "0x" + nonce_bytes.hex()

    # Time bounds
    now = int(time.time())
    valid_after = now - 60  # Valid 1 minute ago (clock skew tolerance)
    valid_before = now + 3600  # Valid for 1 hour

    # Sign the authorization
    signature = sign_transfer_authorization(
        private_key=private_key,
        chain_id=requirements.chain_id,
        token_address=requirements.asset,
        token_name=name,
        token_version=version,
        from_address=from_address,
        to_address=requirements.pay_to,
        value=int(requirements.max_amount_required),
        valid_after=valid_after,
        valid_before=valid_before,
        nonce=nonce_bytes
    )

    # Build x402 v2 payload
    return {
        "x402Version": X402_VERSION,
        "scheme": "exact",
        "network": requirements.network,  # CAIP-2 format
        "payload": {
            "signature": signature,
            "authorization": {
                "from": from_address,
                "to": requirements.pay_to,
                "value": requirements.max_amount_required,
                "validAfter": valid_after,
                "validBefore": valid_before,
                "nonce": nonce_hex
            }
        }
    }
