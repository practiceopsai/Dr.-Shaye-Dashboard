"""Cheap lexical observations. They can hold work, never authorize an effect."""
import re

CONTROL = re.compile(r'^\s*(?:(?:okay|ok|please|no)[,.!\s]+)*(?:wait\b|actually\b|instead\b|never mind\b|forget\b|cancel\b|stop\s+(?:that|the task|sending)|(?:do not|don.t)\s+send\b|(?:change|modify|prioritize|reprioritize)\b)',re.I)


def control_hint(text):
    return bool(CONTROL.search(text[:2000]))


def hold(store, actor, source):
    from . import task_ledger as ledger
    with store.db() as db:ledger.hold(db,actor,source)


def release(store, actor, source):
    from . import task_ledger as ledger
    with store.db() as db:ledger.release(db,actor,source)
