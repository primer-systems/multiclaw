"""
Spend Policy model.

Defines reusable spending rules that can be attached to agents.
"""

import uuid
from datetime import datetime, timezone
from dataclasses import dataclass, asdict, field
from typing import Optional
from urllib.parse import urlparse


@dataclass
class SpendPolicy:
    """A reusable spending policy that can be attached to agents."""
    id: str
    name: str
    networks: list[int]              # Chain IDs this policy allows
    daily_limit_micro: int           # Micro-USDC (6 decimals: 10_000_000 = $10.00)
    per_request_max_micro: int       # Micro-USDC (6 decimals: 1_000_000 = $1.00)
    auto_approve_below_micro: Optional[int]  # Auto-approve threshold (None = manual only)
    created_at: str
    # Domain restrictions
    allowed_domains: list[str] = field(default_factory=list)  # If non-empty, only these domains allowed
    blocked_domains: list[str] = field(default_factory=list)  # These domains are always blocked

    @classmethod
    def create(
        cls,
        name: str,
        networks: list[int],
        daily_limit_micro: int,
        per_request_max_micro: int,
        auto_approve_below_micro: Optional[int] = None,
        allowed_domains: Optional[list[str]] = None,
        blocked_domains: Optional[list[str]] = None
    ) -> "SpendPolicy":
        """Create a new spend policy."""
        return cls(
            id=str(uuid.uuid4()),
            name=name,
            networks=networks,
            daily_limit_micro=daily_limit_micro,
            per_request_max_micro=per_request_max_micro,
            auto_approve_below_micro=auto_approve_below_micro,
            created_at=datetime.now(timezone.utc).isoformat(),
            allowed_domains=allowed_domains or [],
            blocked_domains=blocked_domains or []
        )

    def to_dict(self) -> dict:
        """Convert to dictionary for JSON storage."""
        return asdict(self)

    @classmethod
    def from_dict(cls, data: dict) -> "SpendPolicy":
        """Create from dictionary with input validation."""
        # Validate numeric fields are non-negative
        daily_limit = data.get("daily_limit_micro", 0)
        if not isinstance(daily_limit, int) or daily_limit < 0:
            raise ValueError(f"daily_limit_micro must be non-negative integer, got {daily_limit}")

        per_request_max = data.get("per_request_max_micro", 0)
        if not isinstance(per_request_max, int) or per_request_max < 0:
            raise ValueError(f"per_request_max_micro must be non-negative integer, got {per_request_max}")

        auto_approve = data.get("auto_approve_below_micro")
        if auto_approve is not None and (not isinstance(auto_approve, int) or auto_approve < 0):
            raise ValueError(f"auto_approve_below_micro must be non-negative integer, got {auto_approve}")

        # Ensure networks is a list (handle None or missing)
        if data.get("networks") is None:
            data["networks"] = []

        return cls(**data)

    def check_domain_allowed(self, resource_url: str) -> tuple[bool, str]:
        """
        Check if a resource URL is allowed by this policy's domain rules.

        Returns (is_allowed, reason) where reason explains why if not allowed.

        Rules:
        - Empty allowlist + empty blocklist = all allowed
        - Empty allowlist + filled blocklist = all except blocklist
        - Filled allowlist + empty blocklist = only allowlist
        - Filled allowlist + filled blocklist = allowlist minus blocklist

        Domain matching includes subdomains automatically:
        - "stripe.com" matches "stripe.com", "api.stripe.com", "foo.bar.stripe.com"
        """
        if not resource_url:
            # No resource URL provided - allow (nothing to check)
            return True, ""

        host = self._extract_host(resource_url)
        if not host:
            # URL has no domain (e.g., just a path like "/api/resource")
            # If no domain restrictions configured, allow it
            if not self.allowed_domains and not self.blocked_domains:
                return True, ""
            # If restrictions exist, we can't verify - reject with clear message
            return False, f"Cannot verify domain (resource URL is path only: {resource_url[:50]})"

        host = host.lower()

        # Check blocklist first (applies in all cases)
        if self.blocked_domains:
            for blocked in self.blocked_domains:
                if self._domain_matches(blocked, host):
                    return False, f"Domain '{host}' is blocked"

        # If allowlist exists, host must match it
        if self.allowed_domains:
            for allowed in self.allowed_domains:
                if self._domain_matches(allowed, host):
                    return True, ""
            return False, f"Domain '{host}' not in allowlist"

        # No allowlist = all allowed (blocklist already checked)
        return True, ""

    def _extract_host(self, url: str) -> Optional[str]:
        """Extract hostname from URL."""
        try:
            parsed = urlparse(url)
            return parsed.hostname
        except Exception:
            return None

    def _domain_matches(self, domain_entry: str, host: str) -> bool:
        """
        Check if host matches a domain entry.

        Includes subdomains: "example.com" matches "example.com" and "api.example.com"
        """
        entry = domain_entry.lower().strip()
        if not entry:
            return False
        return host == entry or host.endswith("." + entry)

    def format_daily_limit(self) -> str:
        """Format daily limit as USDC with 6 decimal precision."""
        return f"{self.daily_limit_micro / 1_000_000:.6f} USDC"

    def format_per_request_max(self) -> str:
        """Format per-request max as USDC with 6 decimal precision."""
        return f"{self.per_request_max_micro / 1_000_000:.6f} USDC"

    def format_auto_approve(self) -> str:
        """Format auto-approve threshold as USDC with 6 decimal precision."""
        if self.auto_approve_below_micro is None:
            return "—"
        return f"{self.auto_approve_below_micro / 1_000_000:.6f} USDC"

    def format_domain_restrictions(self) -> str:
        """Format domain restrictions for display."""
        if not self.allowed_domains and not self.blocked_domains:
            return "—"

        parts = []
        if self.allowed_domains:
            parts.append(f"{len(self.allowed_domains)} allowed")
        if self.blocked_domains:
            parts.append(f"{len(self.blocked_domains)} blocked")
        return ", ".join(parts)

    def has_domain_restrictions(self) -> bool:
        """Check if this policy has any domain restrictions."""
        return bool(self.allowed_domains or self.blocked_domains)
