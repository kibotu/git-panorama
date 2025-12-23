#!/usr/bin/env python3
"""
Find Unmapped Email Addresses
Scans all repositories and identifies email addresses that are not mapped in the config.
"""

import argparse
import subprocess
import sys
from pathlib import Path

import yaml


class UnmappedEmailFinder:
    def __init__(self, config_file: str):
        """Initialize the finder with configuration."""
        self.config = self.load_config(config_file)
        self.repos_dir = Path(self.config["repositories"]["base_directory"])

        # Build email mapping
        self.email_mapping = self.build_email_mapping()

    def load_config(self, config_file: str) -> dict:
        """Load configuration from YAML file."""
        config_path = Path(config_file)
        if not config_path.exists():
            print(f"Error: Configuration file not found: {config_file}")
            sys.exit(1)

        with config_path.open() as f:
            return yaml.safe_load(f)

    def build_email_mapping(self) -> set[str]:
        """Build set of mapped emails from config (lowercase)."""
        email_mapping_config = self.config.get("email_mapping", {})
        mapped_emails = set()

        for _person, emails in email_mapping_config.items():
            for email in emails:
                mapped_emails.add(email.lower())

        return mapped_emails

    def get_all_emails_from_repo(self, repo_path: Path) -> set[str]:
        """Get all unique email addresses from a repository."""
        cmd = ["git", "-C", str(repo_path), "log", "--format=%ae", "--all"]

        try:
            result = subprocess.run(cmd, capture_output=True, text=True, check=True)
            emails = {line.strip().lower() for line in result.stdout.split("\n") if line.strip()}
            return emails
        except subprocess.CalledProcessError as e:
            print(f"Error getting emails from {repo_path.name}: {e}", file=sys.stderr)
            return set()

    def find_unmapped_emails(self) -> dict[str, set[str]]:
        """Find all unmapped email addresses across all repositories."""
        if not self.repos_dir.exists():
            print(f"Error: Repositories directory not found: {self.repos_dir}")
            sys.exit(1)

        # Get list of repositories to analyze
        repos_to_analyze = self.config["repositories"].get("repositories_to_analyze", [])

        if repos_to_analyze:
            # Analyze specific repositories
            repo_paths = [self.repos_dir / repo for repo in repos_to_analyze]
        else:
            # Analyze all subdirectories
            repo_paths = [p for p in self.repos_dir.iterdir() if p.is_dir() and (p / ".git").exists()]

        if not repo_paths:
            print("No repositories found to analyze")
            return {}

        all_emails = set()
        repo_email_map = {}

        for repo_path in repo_paths:
            emails = self.get_all_emails_from_repo(repo_path)
            repo_email_map[repo_path.name] = emails
            all_emails.update(emails)

        # Find unmapped emails
        unmapped_emails = all_emails - self.email_mapping

        # Build a map of unmapped emails to repositories they appear in
        unmapped_by_repo = {}
        for email in sorted(unmapped_emails):
            repos_with_email = [repo for repo, emails in repo_email_map.items() if email in emails]
            unmapped_by_repo[email] = repos_with_email

        return unmapped_by_repo

    def print_unmapped_emails(self):
        """Find and print unmapped email addresses."""
        unmapped = self.find_unmapped_emails()

        if not unmapped:
            print("✓ All email addresses are mapped!")
            return

        print(f"\n{'=' * 60}")
        print(f"Unmapped Email Addresses ({len(unmapped)} found)")
        print(f"{'=' * 60}")
        print("\nThe following email addresses are not mapped in config.yaml:")
        print("Consider adding them to the 'email_mapping' section.\n")

        for email in sorted(unmapped.keys()):
            repos = unmapped[email]
            print(f"  • {email}")
            if len(repos) <= 3:
                print(f"    Found in: {', '.join(repos)}")
            else:
                print(f"    Found in: {', '.join(repos[:3])} and {len(repos) - 3} more")

        print(f"\n{'=' * 60}")
        print(f"Total: {len(unmapped)} unmapped email address(es)")
        print(f"{'=' * 60}\n")


def main():
    """Main entry point."""
    parser = argparse.ArgumentParser(
        description="Find unmapped email addresses in git repositories.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument(
        "config_file",
        help="Path to the YAML configuration file",
    )

    args = parser.parse_args()

    finder = UnmappedEmailFinder(args.config_file)
    finder.print_unmapped_emails()


if __name__ == "__main__":
    main()
