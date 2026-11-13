"""Input package loader (generator side): manifest, source, target and matches only. It never opens a reference folder."""
import csv, json
from dataclasses import dataclass
from pathlib import Path


def _j(p):
    with open(p, encoding="utf-8") as f: return json.load(f)

@dataclass(frozen=True)
class Source:
    root: Path
    tables: list
    links: list
    def profile(self, table):
        p = self.root / "profiles" / f"{table}.json"
        return _j(p) if p.exists() else None
    def dependencies(self):
        p = self.root / "dependencies.json"
        return _j(p) if p.exists() else []
    def rows(self, table):
        with open(self.root / "data" / f"{table}.csv", newline="", encoding="utf-8") as f:
            return list(csv.DictReader(f))
    def data_path(self, table): return self.root / "data" / f"{table}.csv"

@dataclass(frozen=True)
class Target:
    tables: list
    def table(self, name): return next(t for t in self.tables if t["name"] == name)

@dataclass(frozen=True)
class Package:
    manifest: dict
    source: Source
    target: Target
    _matches_dir: Path
    def matches(self, setting=None):
        """The matched source columns per target field (matches/matches.json). `setting` is ignored (kept for the callers)."""
        return _j(self._matches_dir / "matches.json")

def load_package(path):
    r = Path(path)
    return Package(_j(r / "manifest.json"), Source(r / "source", _j(r / "source" / "tables.json"), _j(r / "source" / "links.json")),
                   Target(_j(r / "target" / "tables.json")), r / "matches")
