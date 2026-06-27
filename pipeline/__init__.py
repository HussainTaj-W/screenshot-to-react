"""Screenshot-to-React pipeline.

An agentic pipeline that takes an instructions file plus a reference landing-page
screenshot and produces a deployed, responsive React landing page.

The pipeline runs three stages in a fixed, deterministic order:

1. Analyst        -- vision+text analysis of the screenshot/instructions into an
                     auditable requirements set (with an assumption ledger).
2. Builder/Verify -- a ``pydantic_graph`` state machine that scaffolds a
                     Vite+React+Tailwind app, enforces a build-success contract,
                     and iterates on visual fidelity via a vision judge.
3. Deployer       -- builds a fresh ``dist/`` and deploys to Netlify.
"""

__version__ = "0.1.0"
