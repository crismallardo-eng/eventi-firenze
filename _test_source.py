"""Quick standalone smoke test for one source. Throwaway."""
import sys
import importlib

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

if len(sys.argv) < 2:
    print("Usage: python _test_source.py <module_path>")
    sys.exit(1)

mod = importlib.import_module(sys.argv[1])
events = mod.fetch()
print(f"Source: {getattr(mod, 'SOURCE_NAME', '?')}")
print(f"Got {len(events)} events\n")
for e in events:
    when = e.start.strftime("%Y-%m-%d %H:%M")
    venue = e.venue or "-"
    print(f"  {when} | {e.title[:70]}")
    print(f"     venue: {venue}")
    print(f"     url:   {e.url}")
