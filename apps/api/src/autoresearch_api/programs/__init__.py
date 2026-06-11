"""Program import, the hypothesis DAG API, and research.yaml specs.

Submodules are imported directly (``programs.spec``, ``programs.service``,
``programs.router``) to avoid an import cycle: ``dependencies`` imports
``programs.service`` while ``programs.router`` imports ``dependencies``, so this
package must not eagerly import the router at package-init time.
"""
