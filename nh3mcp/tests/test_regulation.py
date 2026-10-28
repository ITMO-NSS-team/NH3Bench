# -*- coding: utf-8 -*-
"""
The written regulation is π_reg, checked against its source.

policies.RulePolicy and policies.RegulationPolicy are parsed (not run): every
sequence of actions they take and every threshold they compare against must
be a clause of nh3mcp.regulation, and every clause must be in the code. A
retune of π_reg that is not carried into the text -- or a clause that π_reg
does not follow -- fails here.
"""

from __future__ import annotations

import ast
import asyncio
import re
from collections import Counter
from pathlib import Path

import nh3twin.policies as policies
from nh3mcp import regulation
from nh3twin.actions import CATALOG_BY_ID

from conftest import call, make, text_of

_AID = re.compile(r"^[A-Z_]+:(?:[A-Z0-9_:\-]|\{ev\})+$")
CLASSES = ("RulePolicy", "RegulationPolicy")


def _classes():
    tree = ast.parse(Path(policies.__file__).read_text(encoding="utf-8"))
    return [n for n in tree.body if isinstance(n, ast.ClassDef) and n.name in CLASSES]


def _aid(node):
    """An action id literal: a string, or an f-string over the cooler."""
    if isinstance(node, ast.Constant) and isinstance(node.value, str):
        s = node.value
    elif isinstance(node, ast.JoinedStr):
        s = "".join(v.value if isinstance(v, ast.Constant) else "{ev}"
                    for v in node.values)
    else:
        return None
    return s if _AID.match(s) else None


def code_sequences() -> list:
    seqs = []
    for cls in _classes():
        parent = {}
        for n in ast.walk(cls):
            for ch in ast.iter_child_nodes(n):
                parent[ch] = n
        # action lists written as tuples
        for n in ast.walk(cls):
            if isinstance(n, ast.Tuple) and n.elts and all(_aid(e) for e in n.elts):
                seqs.append(tuple(_aid(e) for e in n.elts))
        # single _once(...) calls, grouped by the `if` they sit in
        groups = {}
        for n in ast.walk(cls):
            if (isinstance(n, ast.Call) and isinstance(n.func, ast.Attribute)
                    and n.func.attr == "_once" and len(n.args) == 2
                    and _aid(n.args[1])):
                p = parent[n]
                while not isinstance(p, ast.If):
                    p = parent[p]
                groups.setdefault(id(p), []).append((n.lineno, _aid(n.args[1])))
        seqs += [tuple(a for _, a in sorted(g)) for g in groups.values()]
    return seqs


def code_thresholds() -> set:
    out = set()
    for cls in _classes():
        for n in ast.walk(cls):
            if isinstance(n, ast.Assign) and any(
                    isinstance(t, ast.Name) and t.id == "STUCK_DEFROST_S" for t in n.targets):
                out.add(float(n.value.value))
            if isinstance(n, ast.Compare):
                for side in [n.left] + n.comparators:
                    out |= _limits(side)
    return out


def _limits(node) -> set:
    """Numbers compared against -- not a reading's default (T.get(.., 0)), not an index."""
    if isinstance(node, (ast.Call, ast.Subscript)):
        return set()
    if isinstance(node, ast.Constant):
        return {float(node.value)} if type(node.value) in (int, float) else set()
    out = set()
    for ch in ast.iter_child_nodes(node):
        out |= _limits(ch)
    return out


def test_every_action_sequence_of_pi_reg_is_a_clause_and_back():
    assert Counter(code_sequences()) == Counter(c.actions for c in regulation.CLAUSES)


def test_every_threshold_of_pi_reg_is_in_the_text_and_back():
    stated = {float(x) for c in regulation.CLAUSES for x in c.thresholds}
    assert stated == code_thresholds()
    for c in regulation.CLAUSES:                 # and the text says the number
        for x in c.thresholds:
            num = f"{x:g}"
            assert num in c.when["ru"] and num in c.when["en"], (c.cid, num)


def test_every_clause_action_exists():
    for c in regulation.CLAUSES:
        for aid in c.actions:
            assert aid.replace("{ev}", "EV-03") in CATALOG_BY_ID, aid


def test_pack_is_off_by_default_and_on_when_asked():
    _, app = make(clock={"mode": "fixed"})
    assert "read_regulation" not in {t.name for t in asyncio.run(app.list_tools())}
    for lang, head in (("ru", "ИНСТРУКЦИЯ ОПЕРАТОРА"), ("en", "OPERATING INSTRUCTION")):
        env, app = make(clock={"mode": "fixed"}, policy_pack=True, lang=lang)
        assert "read_regulation" in {t.name for t in asyncio.run(app.list_tools())}
        out = text_of(call(app, "read_regulation"))
        assert out.startswith(head) and env.calls["read_regulation"] == 1
        prompt = asyncio.run(app.get_prompt("task")).messages[0].content.text
        assert "read_regulation" in prompt
    assert not re.search("[А-Яа-яЁё]", regulation.text("en"))
