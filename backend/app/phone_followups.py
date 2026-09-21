"""One outbound attempt only after an explicit callback request."""
import secrets
import time

from . import phone
from .security import payload_hash


def prepare_callback():
    if not phone.settings().phone_outbound_enabled:
        return
    now=time.time()
    with phone.store().db() as db:
        db.execute('BEGIN IMMEDIATE')
        # Retire historical implicit follow-ups. Keep their unique receipts forever.
        db.execute("""UPDATE phone_outbound SET state='cancelled' WHERE state IN ('approved','preparing')
            AND id IN (SELECT followup_id FROM phone_notices)
            AND callback_job IN (SELECT id FROM phone_jobs WHERE callback_requested=0)""")
        db.execute("""UPDATE phone_outbound SET state='cancelled' WHERE state IN ('approved','preparing')
            AND id IN (SELECT n.followup_id FROM phone_notices n JOIN phone_jobs j ON j.id=n.job_id WHERE j.state='resumed')""")
        row=db.execute("""SELECT j.* FROM phone_jobs j JOIN phone_calls c ON c.id=j.call_id
            WHERE j.callback_requested=1 AND j.state IN ('completed','failed','uncertain','waiting_for_input')
            AND j.updated<? AND (c.ended<? OR c.created<?)
            AND NOT EXISTS (SELECT 1 FROM phone_outbound o WHERE o.callback_job=COALESCE(j.root_id,j.id))
            AND NOT EXISTS (SELECT 1 FROM phone_live_streams s JOIN phone_calls a ON a.id=s.call_id
                WHERE a.actor=j.actor AND ((s.state='active' AND s.last_seen>?) OR (s.state='pending' AND s.created>?)))
            ORDER BY j.created LIMIT 1""",(now-15,now-30,now-1230,now-45,now-60)).fetchone()
        if not row:
            return
        entry=phone.callers().get(row['actor'])
        if not entry:
            return
        identifier=secrets.token_hex(16)
        payload={'recipient':entry['phone'],'message':'Your requested Eli update is ready.',
                 'purpose':'One explicitly requested callback for phone request '+row['id']}
        db.execute("""INSERT OR IGNORE INTO phone_outbound(id,actor,recipient,message,purpose,payload_hash,state,created,expires,approved,callback_job)
            VALUES (?,?,?,?,?,?,'approved',?,?,?,?)""",
            (identifier,row['actor'],payload['recipient'],payload['message'],payload['purpose'],payload_hash(payload),now,now+3600,now,row['root_id'] or row['id']))
        db.execute('UPDATE phone_notices SET followup_id=? WHERE job_id=?',(identifier,row['id']))


def close_stale_streams():
    now=time.time()
    with phone.store().db() as db:
        db.execute("""UPDATE phone_calls SET ended=COALESCE(ended,?) WHERE id IN
            (SELECT call_id FROM phone_live_streams WHERE state='active' AND COALESCE(last_seen,created)<?)""",(now,now-45))
        db.execute("""UPDATE phone_live_streams SET state='closed',closed=?,reason='connection_lost'
            WHERE state='active' AND COALESCE(last_seen,created)<?""",(now,now-45))
