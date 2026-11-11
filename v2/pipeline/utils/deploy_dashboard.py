"""
Best-effort auto-deploy of the visualizer (which now includes the static
/extraction-status/ dashboard) to Netlify, so the live site never drifts from the data
backlog_report.py just regenerated.

No-ops silently until the site has been linked once:
    cd v2/visualizer && npx netlify login   # one-time, opens a browser
    cd v2/visualizer && npx netlify link    # or `netlify init` for a new site

Once visualizer/.netlify/state.json exists, every call to main() here will
rebuild the SvelteKit app and push it to the linked Netlify site.

Usage:
    python3 utils/deploy_dashboard.py
"""

from __future__ import annotations

import logging
import subprocess
from pathlib import Path

log = logging.getLogger("kvizzing")

V2_DIR = Path(__file__).parent.parent.parent
VISUALIZER_DIR = V2_DIR / "visualizer"
NETLIFY_STATE = VISUALIZER_DIR / ".netlify" / "state.json"


def main() -> bool:
    """Returns True if a deploy was attempted (regardless of success)."""
    if not NETLIFY_STATE.exists():
        log.debug("Dashboard auto-deploy skipped — Netlify site not linked yet "
                   "(run `npx netlify link` in v2/visualizer/ to enable).")
        return False

    log.info("Rebuilding visualizer for deploy…")
    build = subprocess.run(
        ["npm", "run", "build"], cwd=VISUALIZER_DIR,
        capture_output=True, text=True,
    )
    if build.returncode != 0:
        log.warning("Dashboard auto-deploy: build failed — %s", build.stderr[-1000:])
        return True

    log.info("Deploying to Netlify…")
    deploy = subprocess.run(
        ["npx", "netlify", "deploy", "--prod", "--dir=build", "--no-build"],
        cwd=VISUALIZER_DIR, capture_output=True, text=True,
    )
    if deploy.returncode != 0:
        log.warning("Dashboard auto-deploy: netlify deploy failed — %s", deploy.stderr[-1000:])
    else:
        log.info("Dashboard deployed.")
    return True


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(message)s")
    main()
