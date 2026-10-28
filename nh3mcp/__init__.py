"""
NH3Ops-Bench as an MCP environment server.

The twin in ``nh3twin`` is not touched: this package turns its episode loop
inside out, so that a harness connected over MCP drives the plant one tool
call at a time while the clock keeps the benchmark's pseudo-real-time rule.

    instance.py   what one run is: scenario, seed, task language, clock
    env.py        the stateful environment (agent calls + hidden control)
    texts.py      the task prompt and the protocol's own replies, ru / en
    server.py     the agent surface as an MCP server (stdio or HTTP)
    oracle.py     hidden truth and the verdict, by the benchmark's own score
    reference.py  scripted solvers driven through the MCP surface
    templates.py  scenario templates for the DMCP-IH stand (draft schema)
"""
