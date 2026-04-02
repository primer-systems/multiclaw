"""
History command implementations.
"""

from typing import TYPE_CHECKING

from .result import CommandResult

if TYPE_CHECKING:
    from ..core import MultiClaw
    from .handler import CommandHandler


class HistoryCommands:
    """History-related commands."""

    def __init__(self, core: "MultiClaw", handler: "CommandHandler"):
        self.core = core
        self.handler = handler

    def execute(self, args: list[str]) -> CommandResult:
        """Route history subcommands."""
        if not args:
            return self._list(20)

        if args[0] in ("--help", "-h"):
            return self._help()

        subcmd = args[0].lower()

        if subcmd in ("clear", "list"):
            if subcmd == "list":
                limit = 20
                if len(args) > 1:
                    try:
                        limit = int(args[1])
                    except ValueError:
                        return CommandResult.fail("Usage: history list [limit]")
                return self._list(limit)
            return self._clear(force=("--yes" in args or "-y" in args))
        elif subcmd == "show":
            if "--help" in args or "-h" in args:
                return CommandResult.ok("""history show - Display transaction details

Usage: history show <tx_id>

The tx_id can be a prefix (e.g., first 8 characters).""")
            if len(args) < 2:
                return CommandResult.fail("Usage: history show <tx_id>")
            return self._show(args[1])
        elif subcmd == "export":
            if "--help" in args or "-h" in args:
                return self._export_help()
            filename = args[1] if len(args) > 1 else None
            return self._export(filename)
        elif subcmd == "verify":
            if "--help" in args or "-h" in args:
                return CommandResult.ok("""history verify - Verify a transaction on-chain

Usage: history verify <tx_id>

Verifies the transaction exists on the blockchain.""")
            if len(args) < 2:
                return CommandResult.fail("Usage: history verify <tx_id>")
            return self._verify(args[1])
        elif subcmd == "receipt":
            if "--help" in args or "-h" in args:
                return CommandResult.ok("""history receipt - Get AP2-formatted receipt

Usage: history receipt <tx_id>

Returns the receipt in AP2 JSON format.""")
            if len(args) < 2:
                return CommandResult.fail("Usage: history receipt <tx_id>")
            return self._receipt(args[1])
        else:
            # Try to parse as limit
            try:
                limit = int(subcmd)
                return self._list(limit)
            except ValueError:
                return CommandResult.fail("Usage: history [limit] | history show <id> | history clear | history export | history verify <id> | history receipt <id>")

    def _help(self) -> CommandResult:
        """Show history command help."""
        help_text = """history - View transaction history

Subcommands:
  history [limit]        - List recent transactions (default: 20)
  history list [limit]   - Same as above
  history show <id>      - Show transaction details
  history export [file]  - Export transactions to CSV
  history verify <id>    - Verify transaction on-chain
  history receipt <id>   - Get AP2-formatted receipt
  history clear          - Clear all history"""
        return CommandResult.ok(help_text)

    def _list(self, limit: int) -> CommandResult:
        """List recent transactions."""
        txs = self.core.get_recent_transactions(limit)
        if not txs:
            return CommandResult.ok("No transactions.")

        lines = ["Recent Transactions:"]
        for tx in txs:
            amount = tx.amount_micro / 1_000_000
            lines.append(f"  {tx.id[:8]}  {tx.agent_name or 'unknown'}  ${amount:.6f}  [{tx.status}]")

        return CommandResult.ok("\n".join(lines), data={"transactions": [
            {
                "id": tx.id,
                "agent_name": tx.agent_name,
                "amount": tx.amount_micro / 1_000_000,
                "status": tx.status,
            }
            for tx in txs
        ]})

    def _show(self, tx_id: str) -> CommandResult:
        """Show transaction details."""
        txs = self.core.get_recent_transactions(1000)
        match = None
        for tx in txs:
            if tx.id.startswith(tx_id):
                match = tx
                break

        if not match:
            return CommandResult.fail(f"Transaction not found: {tx_id}")

        amount = match.amount_micro / 1_000_000
        lines = [
            f"Transaction: {match.id}",
            f"  Agent:      {match.agent_name or 'unknown'}",
            f"  Amount:     ${amount:.6f}",
            f"  Status:     {match.status}",
            f"  Recipient:  {match.recipient or 'unknown'}",
            f"  Network:    {match.network}",
            f"  Created:    {match.timestamp[:19] if match.timestamp else 'Unknown'}",
        ]
        return CommandResult.ok("\n".join(lines), data={
            "transaction": {
                "id": match.id,
                "agent_name": match.agent_name,
                "amount": amount,
                "status": match.status,
                "recipient": match.recipient,
                "network": match.network,
            }
        })

    def _clear(self, inputs: dict = None, force: bool = False) -> CommandResult:
        """Clear history with confirmation."""
        if force or (inputs and inputs.get("confirm") == "YES"):
            count = self.core.clear_transactions()
            return CommandResult.ok(f"Cleared {count} transaction(s).")

        # Need confirmation
        self.handler._set_pending(
            lambda inp, **ctx: self._clear(inp),
        )
        return CommandResult.need_input(
            "confirm",
            "Clear all transaction history? This cannot be undone.\nType YES to confirm:",
        )

    def _export_help(self) -> CommandResult:
        """Help for history export."""
        return CommandResult.ok("""history export - Export transactions to CSV

Usage: history export [filename]

Arguments:
  [filename]  Output file path. Defaults to transactions.csv

Example:
  history export
  history export ~/payments.csv""")

    def _export(self, filename: str = None) -> CommandResult:
        """Export transactions to CSV file."""
        import csv
        from pathlib import Path
        from datetime import datetime

        txs = self.core.get_recent_transactions(10000)  # Get all
        if not txs:
            return CommandResult.ok("No transactions to export.")

        # Default to cwd. resolve() ensures the output message always shows the absolute path
        # so the user knows exactly where the file landed regardless of caller context.
        if not filename:
            filename = f"transactions_{datetime.now().strftime('%Y%m%d_%H%M%S')}.csv"
        filepath = Path(filename).expanduser().resolve()

        try:
            with open(filepath, 'w', newline='', encoding='utf-8') as f:
                writer = csv.writer(f)
                # Header
                writer.writerow([
                    'ID', 'Agent', 'Amount (USD)', 'Status', 'Recipient',
                    'Network', 'Timestamp', 'Resource URL'
                ])
                # Data
                for tx in txs:
                    # Use request_url (full URL) if available, otherwise fall back to resource
                    # Use getattr for compatibility with both Transaction and TransactionProxy
                    resource_url = (
                        getattr(tx, 'request_url', None) or
                        getattr(tx, 'resource', None) or
                        getattr(tx, 'resource_url', None) or
                        ''
                    )
                    writer.writerow([
                        tx.id,
                        getattr(tx, 'agent_name', '') or '',
                        f"{tx.amount_micro / 1_000_000:.6f}",
                        tx.status,
                        getattr(tx, 'recipient', '') or '',
                        getattr(tx, 'network', '') or '',
                        getattr(tx, 'timestamp', '') or '',
                        resource_url
                    ])

            return CommandResult.ok(
                f"Exported {len(txs)} transaction(s) to {filepath.resolve()}",
                data={"filename": str(filepath.resolve()), "count": len(txs)}
            )
        except Exception as e:
            return CommandResult.fail(f"Export failed: {e}")

    def _find_transaction(self, tx_id: str):
        """Find transaction by ID prefix."""
        txs = self.core.get_recent_transactions(10000)
        for tx in txs:
            if tx.id.startswith(tx_id):
                return tx
        return None

    def _verify(self, tx_id: str) -> CommandResult:
        """Verify a transaction on-chain."""
        tx = self._find_transaction(tx_id)
        if not tx:
            return CommandResult.fail(f"Transaction not found: {tx_id}")

        try:
            self.core.verify_transaction(tx)
            return CommandResult.ok(
                f"Verification started for {tx.id[:16]}...\n"
                "Check history show to see the verification status."
            )
        except Exception as e:
            return CommandResult.fail(f"Verification failed: {e}")

    def _receipt(self, tx_id: str) -> CommandResult:
        """Get AP2-formatted receipt for a transaction."""
        import json

        tx = self._find_transaction(tx_id)
        if not tx:
            return CommandResult.fail(f"Transaction not found: {tx_id}")

        receipt = self.core.get_receipt(tx.id)

        if receipt.get("error"):
            return CommandResult.fail(f"Receipt error: {receipt['error']}")

        # Format receipt as pretty JSON
        receipt_json = json.dumps(receipt, indent=2)

        return CommandResult.ok(
            f"Receipt for {tx.id[:16]}...:\n\n{receipt_json}",
            data={"receipt": receipt}
        )
