#!/usr/bin/env python3
"""
TinyIntent Release Notes Generator

Reads recent git commits and produces a markdown snippet summarizing 
changes since the last tag. No tagging logic - just text generation.

M9.1: Final Polish & Release Prep
"""

import subprocess
import sys
import re
from datetime import datetime, timedelta
from pathlib import Path
from typing import List, Dict, Optional, Tuple


class ReleaseNotesGenerator:
    """Generates release notes from git history."""
    
    def __init__(self, project_root: Optional[Path] = None):
        """Initialize generator with project root."""
        if project_root is None:
            self.project_root = Path(__file__).parent.parent
        else:
            self.project_root = project_root
    
    def run_git_command(self, args: List[str]) -> Tuple[int, str, str]:
        """Run a git command and return exit code, stdout, stderr."""
        try:
            result = subprocess.run(
                ["git"] + args,
                cwd=self.project_root,
                capture_output=True,
                text=True,
                timeout=30
            )
            return result.returncode, result.stdout.strip(), result.stderr.strip()
        except subprocess.TimeoutExpired:
            return 1, "", "Git command timed out"
        except Exception as e:
            return 1, "", f"Git command failed: {e}"
    
    def get_last_tag(self) -> Optional[str]:
        """Get the most recent git tag."""
        exit_code, stdout, stderr = self.run_git_command(["describe", "--tags", "--abbrev=0"])
        
        if exit_code == 0 and stdout:
            return stdout
        return None
    
    def get_commits_since_tag(self, tag: Optional[str] = None) -> List[Dict[str, str]]:
        """Get commits since the specified tag (or all commits if no tag)."""
        if tag:
            # Get commits since the tag
            git_args = ["log", f"{tag}..HEAD", "--oneline", "--no-merges"]
        else:
            # Get last 50 commits if no tag exists
            git_args = ["log", "-50", "--oneline", "--no-merges"]
        
        exit_code, stdout, stderr = self.run_git_command(git_args)
        
        if exit_code != 0:
            return []
        
        commits = []
        for line in stdout.split('\n'):
            if line.strip():
                # Parse commit line: hash subject
                parts = line.split(' ', 1)
                if len(parts) >= 2:
                    commit_hash = parts[0]
                    subject = parts[1]
                    commits.append({
                        "hash": commit_hash,
                        "subject": subject
                    })
        
        return commits
    
    def get_detailed_commits_since_tag(self, tag: Optional[str] = None) -> List[Dict[str, str]]:
        """Get detailed commit information since the specified tag."""
        if tag:
            git_args = ["log", f"{tag}..HEAD", "--no-merges", "--format=%H|%an|%ad|%s", "--date=short"]
        else:
            git_args = ["log", "-50", "--no-merges", "--format=%H|%an|%ad|%s", "--date=short"]
        
        exit_code, stdout, stderr = self.run_git_command(git_args)
        
        if exit_code != 0:
            return []
        
        commits = []
        for line in stdout.split('\n'):
            if line.strip():
                parts = line.split('|', 3)
                if len(parts) == 4:
                    commits.append({
                        "hash": parts[0][:8],  # Short hash
                        "author": parts[1],
                        "date": parts[2],
                        "subject": parts[3]
                    })
        
        return commits
    
    def categorize_commits(self, commits: List[Dict[str, str]]) -> Dict[str, List[Dict[str, str]]]:
        """Categorize commits by type based on conventional commit patterns."""
        categories = {
            "Features": [],
            "Bug Fixes": [],
            "Improvements": [],
            "Security": [],
            "Documentation": [],
            "Tests": [],
            "Build & CI": [],
            "Refactoring": [],
            "Other": []
        }
        
        # Patterns for categorization
        patterns = {
            "Features": [r"^feat", r"^add", r"implement", r"new feature", r"M\d+\.\d+"],
            "Bug Fixes": [r"^fix", r"^bug", r"resolve", r"correct", r"patch"],
            "Improvements": [r"^improve", r"^enhance", r"^optimize", r"^update", r"^upgrade"],
            "Security": [r"^security", r"^sec", r"audit", r"sanitiz", r"auth", r"rate.?limit"],
            "Documentation": [r"^docs?", r"^readme", r"^comment", r"docstring"],
            "Tests": [r"^test", r"^spec", r"coverage", r"smoke"],
            "Build & CI": [r"^build", r"^ci", r"^deploy", r"makefile", r"pip", r"pyproject"],
            "Refactoring": [r"^refactor", r"^clean", r"^reorganize", r"^restructure"]
        }
        
        for commit in commits:
            subject_lower = commit["subject"].lower()
            categorized = False
            
            for category, category_patterns in patterns.items():
                for pattern in category_patterns:
                    if re.search(pattern, subject_lower):
                        categories[category].append(commit)
                        categorized = True
                        break
                if categorized:
                    break
            
            if not categorized:
                categories["Other"].append(commit)
        
        return categories
    
    def generate_release_notes(self, tag: Optional[str] = None, detailed: bool = True) -> str:
        """Generate release notes markdown."""
        # Get repository info
        exit_code, repo_name, _ = self.run_git_command(["config", "--get", "remote.origin.url"])
        if exit_code == 0 and repo_name:
            # Extract repo name from URL
            repo_name = repo_name.split('/')[-1].replace('.git', '')
        else:
            repo_name = "TinyIntent"
        
        # Get commits
        if detailed:
            commits = self.get_detailed_commits_since_tag(tag)
        else:
            commits = self.get_commits_since_tag(tag)
        
        if not commits:
            return "No commits found since last tag."
        
        # Generate header
        current_date = datetime.now().strftime("%Y-%m-%d")
        if tag:
            title = f"# Release Notes - Changes since {tag}"
        else:
            title = f"# Release Notes - Recent Changes"
        
        notes = [title]
        notes.append(f"*Generated on {current_date}*")
        notes.append("")
        
        if detailed:
            # Categorized release notes
            categorized = self.categorize_commits(commits)
            
            notes.append(f"## Summary")
            notes.append(f"- **Total Changes**: {len(commits)} commits")
            if tag:
                notes.append(f"- **Since**: {tag}")
            notes.append("")
            
            # Add each category
            for category, category_commits in categorized.items():
                if category_commits:
                    notes.append(f"## {category}")
                    notes.append("")
                    for commit in category_commits:
                        # Format: - Subject (hash by author on date)
                        notes.append(f"- {commit['subject']} (`{commit['hash']}` by {commit['author']} on {commit['date']})")
                    notes.append("")
        else:
            # Simple list
            notes.append(f"## Changes ({len(commits)} commits)")
            notes.append("")
            for commit in commits:
                notes.append(f"- {commit['subject']} (`{commit['hash']}`)")
            notes.append("")
        
        # Add footer
        notes.append("---")
        notes.append("")
        notes.append("*Generated by TinyIntent Release Notes Generator*")
        
        return "\n".join(notes)
    
    def get_milestone_summary(self) -> str:
        """Generate a milestone-focused summary of recent changes."""
        commits = self.get_detailed_commits_since_tag()
        
        if not commits:
            return "No recent commits found."
        
        # Look for milestone mentions (M8.x, M9.x pattern)
        milestone_pattern = r"M(\d+)\.(\d+)"
        milestones = {}
        
        for commit in commits:
            matches = re.findall(milestone_pattern, commit["subject"])
            for major, minor in matches:
                milestone = f"M{major}.{minor}"
                if milestone not in milestones:
                    milestones[milestone] = []
                milestones[milestone].append(commit)
        
        if not milestones:
            return "No milestone-tagged commits found in recent history."
        
        # Generate milestone summary
        summary = ["# TinyIntent Milestone Summary"]
        summary.append("")
        
        for milestone in sorted(milestones.keys(), reverse=True):
            milestone_commits = milestones[milestone]
            summary.append(f"## {milestone}")
            summary.append(f"*{len(milestone_commits)} commits*")
            summary.append("")
            
            for commit in milestone_commits:
                # Extract the main change description (remove milestone prefix)
                subject = re.sub(r"^M\d+\.\d+:?\s*", "", commit["subject"])
                summary.append(f"- {subject}")
            summary.append("")
        
        return "\n".join(summary)


def main():
    """Main entry point."""
    import argparse
    
    parser = argparse.ArgumentParser(description="Generate TinyIntent release notes")
    parser.add_argument("--tag", help="Generate notes since this tag (default: last tag)")
    parser.add_argument("--simple", action="store_true", help="Generate simple list instead of categorized")
    parser.add_argument("--milestones", action="store_true", help="Generate milestone-focused summary")
    parser.add_argument("--output", help="Output file (default: stdout)")
    
    args = parser.parse_args()
    
    # Change to project root
    project_root = Path(__file__).parent.parent
    
    generator = ReleaseNotesGenerator(project_root)
    
    if args.milestones:
        notes = generator.get_milestone_summary()
    else:
        # Determine tag to use
        tag = args.tag
        if tag is None:
            tag = generator.get_last_tag()
            if tag:
                print(f"Using last tag: {tag}", file=sys.stderr)
            else:
                print("No tags found, showing recent commits", file=sys.stderr)
        
        notes = generator.generate_release_notes(tag, detailed=not args.simple)
    
    # Output
    if args.output:
        output_path = Path(args.output)
        with open(output_path, 'w') as f:
            f.write(notes)
        print(f"Release notes written to: {output_path}", file=sys.stderr)
    else:
        print(notes)


if __name__ == "__main__":
    main()