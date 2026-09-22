"""Worker-side fences for the canonical task ledger. No independent task queue."""
import hashlib
import json
import asyncio
import time


class Held(RuntimeError):pass


def check(job):
    if not job.get('ledger_version'):return {}  # Compatible with pre-upgrade jobs.
    from . import api_control
    state=api_control(job)
    if state.get('superseded') or state.get('cancel_requested') or state.get('state')=='cancelled':
        raise RuntimeError('The task was changed or cancelled. No further step may start.')
    if state.get('held'):raise Held('A possible task correction is being clarified. Execution is paused.')
    if state.get('version')!=job['ledger_version']:raise RuntimeError('The task version changed. Stop this execution.')
    return state


async def ready(job):
    while True:
        try:return await asyncio.to_thread(check,job)
        except Held:await asyncio.sleep(.5)


def wait_ready(job, seconds=120):
    """Used in the background native tool thread, never the voice event loop."""
    deadline=time.monotonic()+seconds
    while True:
        try:return check(job)
        except Held:
            if time.monotonic()>=deadline:raise
            time.sleep(.5)


def effect(job, key, state='reserved', receipt=None):
    if not job.get('ledger_version'):return None
    from . import api_request
    return api_request('/internal/phone/jobs/'+job['id']+'/effect',
        {'claim':job['claim'],'version':job['ledger_version'],'key':key,
         'state':state,'receipt':receipt or {}})


def prepared_key(job, channel, args):
    return hashlib.sha256((channel+':'+json.dumps(args,sort_keys=True)).encode()).hexdigest()
