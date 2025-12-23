#!/usr/bin/env python3
"""
Git Commits Analyzer
Analyzes git commits with file filtering and generates data for Elasticsearch bulk upload.
Parallelized version with thread-safe operations.
Includes caching to skip re-analysis when repositories haven't changed.
"""

import argparse
import hashlib
import json
import os
import re
import subprocess
import sys
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import UTC, datetime
from pathlib import Path
from threading import Lock

import yaml


class GitCommitsAnalyzer:
    def __init__(self, config_file: str):
        """Initialize the analyzer with configuration."""
        self.config = self.load_config(config_file)
        self.repos_dir = Path(self.config["repositories"]["base_directory"])
        self.output_dir = Path(self.config["analysis"]["output_directory"])
        self.output_dir.mkdir(exist_ok=True, parents=True)

        # Cache directory for storing repository states
        self.cache_dir = self.output_dir / ".cache"
        self.cache_dir.mkdir(exist_ok=True, parents=True)
        self.cache_file = self.cache_dir / "commits_cache.json"

        # Load cache
        self.cache = self.load_cache()

        # Build email mapping
        self.email_mapping = self.build_email_mapping()

        # Get exclusion configuration
        self.include_all_repos = set(self.config["repositories"].get("include_all_files", []))
        self.exclusion_patterns = self.compile_patterns(self.config["exclusions"]["patterns"])
        self.inclusion_patterns = self.compile_patterns(self.config["exclusions"]["always_include"])
        self.repo_specific_exclusions = self.config["exclusions"].get("repository_specific", {})

        # Thread safety
        self.print_lock = Lock()
        self.cache_lock = Lock()

        # Get max workers from config or use default
        max_workers_config = self.config.get("parallelization", {}).get("max_workers")
        self.max_workers = max_workers_config if max_workers_config is not None else (os.cpu_count() or 4)

    def load_config(self, config_file: str) -> dict:
        """Load configuration from YAML file."""
        config_path = Path(config_file)
        if not config_path.exists():
            print(f"Error: Configuration file not found: {config_file}")
            sys.exit(1)

        with config_path.open("r", encoding="utf-8") as f:
            return yaml.safe_load(f)

    def load_cache(self) -> dict:
        """Load cache from file."""
        if not self.cache_file.exists():
            return {}

        try:
            with self.cache_file.open("r", encoding="utf-8") as f:
                return json.load(f)
        except (json.JSONDecodeError, OSError) as e:
            print(f"Warning: Could not load cache: {e}")
            return {}

    def save_cache(self):
        """Save cache to file."""
        try:
            with self.cache_file.open("w", encoding="utf-8") as f:
                json.dump(self.cache, f, indent=2)
        except OSError as e:
            print(f"Warning: Could not save cache: {e}")

    def get_repo_state(self, repo_path: Path) -> str:
        """Get current state of repository (all branch heads and tags)."""
        try:
            # Get all refs (branches and tags) with their commit hashes
            result = subprocess.run(
                ["git", "-C", str(repo_path), "show-ref"], capture_output=True, text=True, check=True, encoding="utf-8"
            )

            # Create a hash of all refs to detect any changes
            return hashlib.sha256(result.stdout.encode()).hexdigest()
        except subprocess.CalledProcessError:
            # If command fails, return empty state
            return ""

    def is_repo_changed(self, repo_path: Path) -> bool:
        """Check if repository has changed since last analysis."""
        repo_name = repo_path.name
        current_state = self.get_repo_state(repo_path)

        if not current_state:
            return True  # If we can't get state, assume changed

        cached_state = self.cache.get(repo_name, {}).get("state")

        if cached_state != current_state:
            return True

        # Also check if cached data file exists
        cached_data_file = self.cache_dir / f"{repo_name}_commits.json"
        return bool(not cached_data_file.exists())

    def load_cached_repo_data(self, repo_path: Path) -> list[dict] | None:
        """Load cached analysis data for a repository."""
        repo_name = repo_path.name
        cached_data_file = self.cache_dir / f"{repo_name}_commits.json"

        if not cached_data_file.exists():
            return None

        try:
            with cached_data_file.open("r", encoding="utf-8") as f:
                return json.load(f)
        except (json.JSONDecodeError, OSError) as e:
            print(f"Warning: Could not load cached data for {repo_name}: {e}")
            return None

    def save_repo_data_to_cache(self, repo_path: Path, commits_data: list[dict]):
        """Save repository analysis data to cache."""
        repo_name = repo_path.name
        current_state = self.get_repo_state(repo_path)
        cached_data_file = self.cache_dir / f"{repo_name}_commits.json"

        try:
            # Save the commits data
            with cached_data_file.open("w", encoding="utf-8") as f:
                json.dump(commits_data, f)

            # Update cache metadata
            with self.cache_lock:
                self.cache[repo_name] = {
                    "state": current_state,
                    "timestamp": datetime.now(UTC).isoformat(),
                    "commit_count": len(commits_data),
                }
        except OSError as e:
            print(f"Warning: Could not save cache for {repo_name}: {e}")

    def build_email_mapping(self) -> dict[str, str]:
        """Build email to person mapping from config."""
        email_mapping_config = self.config.get("email_mapping", {})
        email_to_person = {}

        for person, emails in email_mapping_config.items():
            for email in emails:
                email_to_person[email.lower()] = person

        return email_to_person

    def compile_patterns(self, pattern_list: list[dict]) -> list[tuple[re.Pattern, str]]:
        """Compile regex patterns from configuration."""
        compiled = []
        for item in pattern_list:
            pattern = item.get("pattern", "")
            description = item.get("description", "")
            try:
                compiled.append((re.compile(pattern), description))
            except re.error as e:
                print(f"Warning: Invalid regex pattern '{pattern}': {e}")
        return compiled

    def normalize_email(self, email: str) -> str:
        """Normalize email to person name using mapping."""
        email_lower = email.lower()
        return self.email_mapping.get(email_lower, email)

    def should_exclude_file(self, file_path: str, repo_name: str) -> bool:
        """Determine if a file should be excluded from analysis."""
        # If repository is in include_all list, don't exclude anything
        if repo_name in self.include_all_repos:
            return False

        # Check if file matches any inclusion pattern (these override exclusions)
        for pattern, _ in self.inclusion_patterns:
            if pattern.match(file_path):
                return False

        # Check repository-specific exclusions
        if repo_name in self.repo_specific_exclusions:
            repo_config = self.repo_specific_exclusions[repo_name]

            # Check repository-specific inclusions
            if "include_patterns" in repo_config:
                for item in repo_config["include_patterns"]:
                    pattern = re.compile(item["pattern"])
                    if pattern.match(file_path):
                        return False

            # Check repository-specific exclusions
            if "exclude_patterns" in repo_config:
                for item in repo_config["exclude_patterns"]:
                    pattern = re.compile(item["pattern"])
                    if pattern.match(file_path):
                        return True

        # Check global exclusion patterns
        return any(pattern.match(file_path) for pattern, _ in self.exclusion_patterns)

    def normalize_message(self, message: str) -> str:
        """Normalize commit message by removing line breaks."""
        if self.config.get("metrics", {}).get("commits", {}).get("normalize_message", True):
            # Replace line breaks with spaces and collapse multiple spaces
            return " ".join(message.split())
        return message

    def parse_git_log_line(self, line: str) -> dict | None:
        """Parse a git log line into commit information."""
        # Format: HASH|||EMAIL|||NAME|||TIMESTAMP|||MESSAGE
        parts = line.split("|||")
        if len(parts) < 5:
            return None

        return {
            "commit_id": parts[0].strip(),
            "author_email": parts[1].strip().lower(),
            "author_name": parts[2].strip(),
            "commit_timestamp": parts[3].strip(),
            "commit_message": self.normalize_message(parts[4].strip()) if len(parts) > 4 else "",
        }

    def get_commit_stats(self, repo_path: Path, commit_hash: str, repo_name: str) -> dict:
        """Get detailed statistics for a specific commit."""
        try:
            # Get file stats with numstat
            result = subprocess.run(
                ["git", "-C", str(repo_path), "show", "--numstat", "--format=", commit_hash],
                capture_output=True,
                text=True,
                check=True,
                encoding="utf-8",
            )

            insertions = 0
            deletions = 0
            files_changed = 0

            for line in result.stdout.strip().split("\n"):
                if not line:
                    continue

                parts = line.split("\t")
                if len(parts) < 3:
                    continue

                added = parts[0]
                removed = parts[1]
                file_path = parts[2]

                # Skip binary files
                if added == "-" or removed == "-":
                    continue

                try:
                    added_int = int(added)
                    removed_int = int(removed)
                except ValueError:
                    continue

                # Only count files that pass the exclusion filters
                if not self.should_exclude_file(file_path, repo_name):
                    insertions += added_int
                    deletions += removed_int
                    files_changed += 1

            return {
                "files_changed": files_changed,
                "insertions": insertions,
                "deletions": deletions,
                "lines_changed": insertions + deletions,
            }

        except subprocess.CalledProcessError as e:
            print(f"Error getting stats for commit {commit_hash}: {e}")
            return {"files_changed": 0, "insertions": 0, "deletions": 0, "lines_changed": 0}

    def analyze_repository(self, repo_path: Path) -> list[dict]:
        """Analyze a single repository and return commit data. Thread-safe."""
        repo_name = repo_path.name

        # Check if repository has changed
        if not self.is_repo_changed(repo_path):
            with self.print_lock:
                print(f"Repository unchanged (using cache): {repo_name}")
            cached_data = self.load_cached_repo_data(repo_path)
            if cached_data is not None:
                with self.print_lock:
                    print(f"  Loaded {len(cached_data)} commits from cache")
                return cached_data

        with self.print_lock:
            print(f"Analyzing repository: {repo_name}")

        # Build git log command
        cmd = ["git", "-C", str(repo_path), "log", "--format=%H|||%ae|||%an|||%cI|||%s"]

        # Add branch filter
        if self.config["analysis"]["all_branches"]:
            cmd.append("--all")

        # Add merge commit filter
        if self.config["analysis"]["exclude_merge_commits"]:
            cmd.append("--no-merges")

        # Add date range filters
        start_date = self.config["analysis"].get("start_date")
        end_date = self.config["analysis"].get("end_date")

        if start_date:
            cmd.append(f"--since={start_date}")
        if end_date:
            cmd.append(f"--until={end_date}")

        try:
            result = subprocess.run(cmd, capture_output=True, text=True, check=True, encoding="utf-8")
        except subprocess.CalledProcessError as e:
            with self.print_lock:
                print(f"Error running git log for {repo_name}: {e}")
            return []

        commits_data = []

        for line in result.stdout.strip().split("\n"):
            if not line:
                continue

            commit_info = self.parse_git_log_line(line)
            if not commit_info:
                continue

            # Get commit statistics
            stats = self.get_commit_stats(repo_path, commit_info["commit_id"], repo_name)

            # Normalize author name
            author_name = self.normalize_email(commit_info["author_email"])

            # Build commit document
            commit_doc = {
                "repository": repo_name,
                "commit_id": commit_info["commit_id"],
                "author_email": commit_info["author_email"],
                "author_name": author_name,
                "commit_timestamp": commit_info["commit_timestamp"],
                "files_changed": stats["files_changed"],
                "insertions": stats["insertions"],
                "deletions": stats["deletions"],
                "lines_changed": stats["lines_changed"],
            }

            commits_data.append(commit_doc)

        with self.print_lock:
            print(f"  Found {len(commits_data)} commits")

        # Save to cache
        self.save_repo_data_to_cache(repo_path, commits_data)

        return commits_data

    def generate_bulk_data(self, commits_data: list[dict], index_name: str) -> str:
        """Generate Elasticsearch bulk upload format."""
        bulk_lines = []

        for commit in commits_data:
            # Index action
            action = {"index": {"_index": index_name, "_id": f"{commit['repository']}_{commit['commit_id']}"}}
            bulk_lines.append(json.dumps(action))
            bulk_lines.append(json.dumps(commit))

        return "\n".join(bulk_lines) + "\n"

    def analyze_all_repositories(self):
        """Analyze all repositories in parallel and generate bulk upload files."""
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
            return

        print(f"Found {len(repo_paths)} repositories to analyze")
        print(f"Using {self.max_workers} parallel workers\n")

        all_commits = []

        # Parallelize repository analysis
        with ThreadPoolExecutor(max_workers=self.max_workers) as executor:
            # Submit all repository analysis tasks
            future_to_repo = {
                executor.submit(self.analyze_repository, repo_path): repo_path for repo_path in repo_paths
            }

            # Collect results as they complete
            for future in as_completed(future_to_repo):
                repo_path = future_to_repo[future]
                try:
                    commits = future.result()
                    all_commits.extend(commits)
                except Exception as e:
                    with self.print_lock:
                        print(f"Error analyzing {repo_path.name}: {e}")

        print(f"\nTotal commits analyzed: {len(all_commits)}")

        # Save cache metadata
        self.save_cache()

        # Generate bulk upload file
        index_name = self.config["elasticsearch"]["commit_index"]
        bulk_data = self.generate_bulk_data(all_commits, index_name)

        output_file = self.output_dir / "commits-bulk.json"
        with output_file.open("w", encoding="utf-8") as f:
            f.write(bulk_data)

        print(f"Bulk upload file generated: {output_file}")

        # Generate summary statistics
        self.generate_summary(all_commits)

    def generate_summary(self, commits_data: list[dict]):
        """Generate summary statistics."""
        summary = {
            "total_commits": len(commits_data),
            "insertions": sum(c["insertions"] for c in commits_data),
            "deletions": sum(c["deletions"] for c in commits_data),
            "lines_changed": sum(c["lines_changed"] for c in commits_data),
            "repositories": len({c["repository"] for c in commits_data}),
            "contributors": len({c["author_name"] for c in commits_data}),
        }

        summary_file = self.output_dir / "commits-summary.json"
        with summary_file.open("w", encoding="utf-8") as f:
            json.dump(summary, f, indent=2)

        print("\nSummary:")
        print(f"  Total commits: {summary['total_commits']:,}")
        print(f"  Total repositories: {summary['repositories']}")
        print(f"  Total contributors: {summary['contributors']}")
        print(f"  Total lines changed: {summary['lines_changed']:,}")


def main():
    """Main entry point."""
    parser = argparse.ArgumentParser(
        description="Analyze git commits and generate data for Elasticsearch bulk upload.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument(
        "config_file",
        help="Path to the YAML configuration file",
    )

    args = parser.parse_args()

    analyzer = GitCommitsAnalyzer(args.config_file)
    analyzer.analyze_all_repositories()


if __name__ == "__main__":
    main()
