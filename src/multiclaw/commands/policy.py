"""
Policy command implementations.
"""

from typing import TYPE_CHECKING

from .result import CommandResult

if TYPE_CHECKING:
    from ..core import MultiClaw
    from .handler import CommandHandler


class PolicyCommands:
    """Policy-related commands."""

    def __init__(self, core: "MultiClaw", handler: "CommandHandler"):
        self.core = core
        self.handler = handler

    def execute(self, args: list[str]) -> CommandResult:
        """Route policy subcommands."""
        if not args or args[0] in ("--help", "-h"):
            return self._help()

        subcmd = args[0].lower()

        if subcmd == "list":
            return self._list()
        elif subcmd == "show":
            if "--help" in args or "-h" in args:
                return self._show_help()
            if len(args) < 2:
                return CommandResult.fail("Usage: policy show <name>")
            return self._show(args[1])
        elif subcmd == "create":
            if "--help" in args or "-h" in args:
                return self._create_help()
            if len(args) < 2:
                return CommandResult.fail("Usage: policy create <name> [--day N] [--txn N] [--auto N]")
            return self._create(args[1:])
        elif subcmd == "edit":
            if "--help" in args or "-h" in args:
                return self._edit_help()
            if len(args) < 2:
                return CommandResult.fail("Usage: policy edit <name> [--day N] [--txn N] [--auto N]")
            return self._edit(args[1:])
        elif subcmd == "delete":
            if "--help" in args or "-h" in args:
                return CommandResult.ok("policy delete - Remove a spending policy\n\nUsage: policy delete <name>\n\nAgents using this policy will be decommissioned.\nYou will be asked to confirm.")
            if len(args) < 2:
                return CommandResult.fail("Usage: policy delete <name>")
            return self._delete(args[1])
        else:
            return CommandResult.fail(f"Unknown subcommand: {subcmd}")

    def _help(self) -> CommandResult:
        """Show policy command help."""
        help_text = """policy - Manage spending policies

Subcommands:
  list                              - List all policies
  show <policy>                     - Show policy details
  create <name> [--day N] [--txn N] [--auto N] - Create policy
  edit <policy> [--day N] [--txn N] [--auto N] - Edit policy
  delete <policy>                   - Delete policy

Use 'policy <subcommand> --help' for subcommand options."""
        return CommandResult.ok(help_text)

    def _find_policy(self, identifier: str):
        """Find policy by name."""
        for p in self.core.get_all_policies():
            if p.name.lower() == identifier.lower():
                return p
        return None

    def _list(self) -> CommandResult:
        """List all policies."""
        policies = self.core.get_all_policies()
        if not policies:
            return CommandResult.ok("No policies defined.")

        lines = ["Policies:"]
        for policy in policies:
            daily = policy.daily_limit_micro / 1_000_000
            per_req = policy.per_request_max_micro / 1_000_000
            auto = policy.auto_approve_below_micro / 1_000_000 if policy.auto_approve_below_micro else 0
            lines.append(f"  {policy.name}  daily: ${daily:.2f}  max: ${per_req:.2f}  auto: ${auto:.2f}")

        return CommandResult.ok("\n".join(lines), data={"policies": [
            {
                "id": p.id,
                "name": p.name,
                "daily_limit": p.daily_limit_micro / 1_000_000,
                "per_request_max": p.per_request_max_micro / 1_000_000,
                "auto_approve_below": (p.auto_approve_below_micro / 1_000_000) if p.auto_approve_below_micro else 0,
            }
            for p in policies
        ]})

    def _show_help(self) -> CommandResult:
        """Help for policy show."""
        return CommandResult.ok("""policy show - Display policy details

Usage: policy show <name>

Shows daily limit, per-request max, auto-approve threshold,
allowed/blocked domains, and network restrictions.""")

    def _show(self, identifier: str) -> CommandResult:
        """Show policy details."""
        policy = self._find_policy(identifier)
        if not policy:
            return CommandResult.fail(f"Policy not found: {identifier}")

        daily = policy.daily_limit_micro / 1_000_000
        per_req = policy.per_request_max_micro / 1_000_000
        auto = policy.auto_approve_below_micro / 1_000_000 if policy.auto_approve_below_micro else 0

        lines = [
            f"Policy: {policy.name}",
            f"  Daily Limit:      ${daily:.2f}",
            f"  Per Request Max:  ${per_req:.2f}",
            f"  Auto-approve:     ${auto:.2f}",
            f"  Allowed Domains:  {', '.join(policy.allowed_domains) if policy.allowed_domains else 'All'}",
            f"  Blocked Domains:  {', '.join(policy.blocked_domains) if policy.blocked_domains else 'None'}",
            f"  Networks:         {', '.join(str(n) for n in policy.networks) if policy.networks else 'All'}",
        ]
        return CommandResult.ok("\n".join(lines), data={
            "policy": {
                "id": policy.id,
                "name": policy.name,
                "daily_limit": daily,
                "per_request_max": per_req,
                "auto_approve_below": auto,
                "allowed_domains": policy.allowed_domains,
                "blocked_domains": policy.blocked_domains,
                "networks": policy.networks,
            }
        })

    def _create_help(self) -> CommandResult:
        """Help for policy create."""
        return CommandResult.ok("""policy create - Create a new spending policy

Usage: policy create <name> [--day N] [--txn N] [--auto N] [--networks N,...] [--allow-domains D,...] [--block-domains D,...]

Options:
  --day <amount>           Daily spending limit in USD (default: 100)
  --txn <amount>           Per-transaction maximum in USD (default: 10)
  --auto <amount>          Auto-approve threshold in USD (default: none)
  --networks <ids>         Comma-separated chain IDs (default: all)
  --allow-domains <list>   Comma-separated allowed domains (default: all)
  --block-domains <list>   Comma-separated blocked domains

Examples:
  policy create standard
  policy create premium --day 500 --txn 50 --auto 5
  policy create restricted --allow-domains api.example.com,pay.example.com""")

    def _create(self, args: list[str]) -> CommandResult:
        """Create a new policy."""
        if not args:
            return CommandResult.fail("Usage: policy create <name> [--day N] [--txn N] [--auto N] [--networks N,N,...]")

        name = args[0]
        daily_limit = 100.0
        per_request_max = 10.0
        auto_approve = None
        networks = None
        allow_domains = None
        block_domains = None

        i = 1
        while i < len(args):
            if args[i] == "--day" and i + 1 < len(args):
                try:
                    daily_limit = float(args[i + 1])
                    if daily_limit < 0:
                        return CommandResult.fail(f"Daily limit cannot be negative: {args[i + 1]}")
                except ValueError:
                    return CommandResult.fail(f"Invalid value for --day: {args[i + 1]}")
                i += 2
            elif args[i] == "--txn" and i + 1 < len(args):
                try:
                    per_request_max = float(args[i + 1])
                    if per_request_max < 0:
                        return CommandResult.fail(f"Per-transaction max cannot be negative: {args[i + 1]}")
                except ValueError:
                    return CommandResult.fail(f"Invalid value for --txn: {args[i + 1]}")
                i += 2
            elif args[i] == "--auto" and i + 1 < len(args):
                try:
                    auto_approve = float(args[i + 1])
                    if auto_approve < 0:
                        return CommandResult.fail(f"Auto-approve threshold cannot be negative: {args[i + 1]}")
                except ValueError:
                    return CommandResult.fail(f"Invalid value for --auto: {args[i + 1]}")
                i += 2
            elif args[i] == "--networks" and i + 1 < len(args):
                try:
                    networks = [int(n.strip()) for n in args[i + 1].split(",")]
                except ValueError:
                    return CommandResult.fail(f"Invalid value for --networks: {args[i + 1]}")
                i += 2
            elif args[i] == "--allow-domains" and i + 1 < len(args):
                allow_domains = [d.strip() for d in args[i + 1].split(",") if d.strip()]
                i += 2
            elif args[i] == "--block-domains" and i + 1 < len(args):
                block_domains = [d.strip() for d in args[i + 1].split(",") if d.strip()]
                i += 2
            elif args[i].startswith("--"):
                return CommandResult.fail(
                    f"Unknown option: {args[i]}\n"
                    "Usage: policy create <name> [--day N] [--txn N] [--auto N] [--networks N,...] [--allow-domains D,...] [--block-domains D,...]"
                )
            else:
                i += 1

        try:
            policy = self.core.create_policy(
                name=name,
                daily_limit_micro=int(daily_limit * 1_000_000),
                per_request_max_micro=int(per_request_max * 1_000_000),
                auto_approve_below_micro=int(auto_approve * 1_000_000) if auto_approve else None,
                networks=networks,
                allowed_domains=allow_domains,
                blocked_domains=block_domains,
            )
            return CommandResult.ok(f"Policy '{policy.name}' created.", data={"policy_id": policy.id})
        except ValueError as e:
            return CommandResult.fail(str(e))

    def _edit_help(self) -> CommandResult:
        """Help for policy edit."""
        return CommandResult.ok("""policy edit - Edit an existing policy

Usage: policy edit <name> [--day N] [--txn N] [--auto N] [--networks N,...] [--allow-domains D,...] [--block-domains D,...]

Options:
  --day <amount>           Daily spending limit in USD
  --txn <amount>           Per-transaction maximum in USD
  --auto <amount>          Auto-approve threshold in USD
  --networks <ids>         Comma-separated chain IDs
  --allow-domains <list>   Comma-separated allowed domains (use 'all' to clear)
  --block-domains <list>   Comma-separated blocked domains (use 'none' to clear)

Only specified options will be changed.

Examples:
  policy edit standard --day 200 --auto 10
  policy edit restricted --allow-domains api.example.com""")

    def _edit(self, args: list[str]) -> CommandResult:
        """Edit an existing policy."""
        if not args:
            return CommandResult.fail("Usage: policy edit <name> [--day N] [--txn N] [--auto N] [--networks N,N,...]")

        name = args[0]
        policy = self._find_policy(name)
        if not policy:
            return CommandResult.fail(f"Policy not found: {name}")

        changes = []
        i = 1
        while i < len(args):
            if args[i] == "--day" and i + 1 < len(args):
                try:
                    value = float(args[i + 1])
                    if value < 0:
                        return CommandResult.fail(f"Daily limit cannot be negative: {args[i + 1]}")
                    policy.daily_limit_micro = int(value * 1_000_000)
                    changes.append(f"daily limit: ${value:.2f}")
                except ValueError:
                    return CommandResult.fail(f"Invalid value for --day: {args[i + 1]}")
                i += 2
            elif args[i] == "--txn" and i + 1 < len(args):
                try:
                    value = float(args[i + 1])
                    if value < 0:
                        return CommandResult.fail(f"Per-transaction max cannot be negative: {args[i + 1]}")
                    policy.per_request_max_micro = int(value * 1_000_000)
                    changes.append(f"per-txn max: ${value:.2f}")
                except ValueError:
                    return CommandResult.fail(f"Invalid value for --txn: {args[i + 1]}")
                i += 2
            elif args[i] == "--auto" and i + 1 < len(args):
                try:
                    value = float(args[i + 1])
                    if value < 0:
                        return CommandResult.fail(f"Auto-approve threshold cannot be negative: {args[i + 1]}")
                    policy.auto_approve_below_micro = int(value * 1_000_000)
                    changes.append(f"auto-approve: ${value:.2f}")
                except ValueError:
                    return CommandResult.fail(f"Invalid value for --auto: {args[i + 1]}")
                i += 2
            elif args[i] == "--networks" and i + 1 < len(args):
                try:
                    networks = [int(n.strip()) for n in args[i + 1].split(",")]
                    policy.networks = networks
                    changes.append(f"networks: {args[i + 1]}")
                except ValueError:
                    return CommandResult.fail(f"Invalid value for --networks: {args[i + 1]}")
                i += 2
            elif args[i] == "--allow-domains" and i + 1 < len(args):
                val = args[i + 1].strip().lower()
                policy.allowed_domains = [] if val == "all" else [d.strip() for d in args[i + 1].split(",") if d.strip()]
                changes.append(f"allowed domains: {args[i + 1]}")
                i += 2
            elif args[i] == "--block-domains" and i + 1 < len(args):
                val = args[i + 1].strip().lower()
                policy.blocked_domains = [] if val == "none" else [d.strip() for d in args[i + 1].split(",") if d.strip()]
                changes.append(f"blocked domains: {args[i + 1]}")
                i += 2
            elif args[i].startswith("--"):
                return CommandResult.fail(
                    f"Unknown option: {args[i]}\n"
                    "Usage: policy edit <name> [--day N] [--txn N] [--auto N] [--networks N,...] [--allow-domains D,...] [--block-domains D,...]"
                )
            else:
                i += 1

        if not changes:
            return CommandResult.fail("No changes specified. Use --day, --txn, --auto, or --networks.")

        try:
            self.core.update_policy(policy)
            return CommandResult.ok(f"Policy '{policy.name}' updated: {', '.join(changes)}")
        except Exception as e:
            return CommandResult.fail(str(e))

    def _delete(self, identifier: str, inputs: dict = None) -> CommandResult:
        """Delete a policy with confirmation."""
        policy = self._find_policy(identifier)
        if not policy:
            return CommandResult.fail(f"Policy not found: {identifier}")

        # Check if we have confirmation
        if inputs and inputs.get("confirm") == "YES":
            try:
                decommissioned = self.core.delete_policy(policy.id)
                lines = [f"Policy '{policy.name}' deleted."]
                if decommissioned:
                    lines.append(f"Decommissioned agents: {', '.join(decommissioned)}")
                return CommandResult.ok("\n".join(lines))
            except Exception as e:
                return CommandResult.fail(str(e))

        # Need confirmation
        self.handler._set_pending(
            lambda inp, **ctx: self._delete(ctx["identifier"], inp),
            identifier=identifier
        )
        return CommandResult.need_input(
            "confirm",
            f"Delete policy '{policy.name}'? Agents using it will be decommissioned.\nType YES to confirm:",
        )
