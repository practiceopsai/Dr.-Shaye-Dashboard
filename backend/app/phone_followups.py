"""Durable, batched callbacks for accepted phone tasks; never retries a send.

Only requests accepted under the follow-up policy opt in. Historical jobs are
not backfilled. A provider timeout never causes a second call submission.
"""
import secrets
import time

from . import phone
from .security import payload_hash


def prepare_callback():
    cfg=phone.settings()
    if not cfg.phone_outbound_enabled or getattr(cfg,'phone_followup_mode','callback')!='callback':
        return
    now=time.time()
    with phone.store().db() as db:
        db.execute('BEGIN IMMEDIATE')
        # A new inbound conversation supersedes a callback that has not dialed.
        db.execute("""UPDATE phone_outbound SET state='cancelled' WHERE state IN ('approved','preparing')
            AND id IN (SELECT followup_id FROM phone_notices)
            AND EXISTS (SELECT 1 FROM phone_live_streams s JOIN phone_calls c ON c.id=s.call_id
                WHERE c.actor=phone_outbound.actor AND s.state='active' AND s.last_seen>?)""",(now-30,))
        db.execute("""UPDATE phone_outbound SET state='cancelled' WHERE state IN ('approved','preparing')
            AND id IN (SELECT followup_id FROM phone_notices)
            AND NOT EXISTS (SELECT 1 FROM phone_notices n JOIN phone_jobs j ON j.id=n.job_id
                WHERE n.followup_id=phone_outbound.id AND (j.state='waiting_for_input'
                    OR (n.heard_at IS NULL AND j.state IN ('completed','failed','uncertain'))))""")
        db.execute("""UPDATE phone_outbound SET callback_job=NULL WHERE state='cancelled'
            AND id IN (SELECT followup_id FROM phone_notices)""")
        db.execute("""UPDATE phone_notices SET followup_id=NULL WHERE followup_id IN
            (SELECT id FROM phone_outbound WHERE state='cancelled')""")
        rows=db.execute("""SELECT n.*,j.call_id FROM phone_notices n JOIN phone_jobs j ON j.id=n.job_id
            JOIN phone_calls c ON c.id=j.call_id
            WHERE j.followup_allowed=1 AND n.followup_id IS NULL
              AND (n.heard_at IS NULL OR j.state='waiting_for_input')
              AND j.state IN ('completed','failed','uncertain','waiting_for_input')
              AND n.created<? AND (c.ended<? OR c.created<?)
              AND NOT EXISTS (SELECT 1 FROM phone_live_streams s JOIN phone_calls a ON a.id=s.call_id
                  WHERE a.actor=n.actor AND ((s.state='active' AND s.last_seen>?) OR (s.state='pending' AND s.created>?)))
              AND NOT EXISTS (SELECT 1 FROM phone_outbound o WHERE o.actor=n.actor AND o.callback_job IS NOT NULL
                  AND (o.created>? OR o.state IN ('calling','queued','ringing','in-progress','preparing')))
            ORDER BY n.created LIMIT 32""",(now-15,now-30,now-1230,now-30,now-60,now-120)).fetchall()
        if not rows:
            return
        actor=rows[0]['actor']
        entry=phone.callers().get(actor)
        if not entry:
            return
        batch=[r for r in rows if r['actor']==actor][:10]
        identifier=secrets.token_hex(16)
        payload={'recipient':entry['phone'],'message':'Your Eli phone task update is ready.',
                 'purpose':'Follow up on accepted phone requests after the conversation ended.'}
        db.execute("""INSERT INTO phone_outbound(id,actor,recipient,message,purpose,payload_hash,state,created,expires,approved,callback_job)
            VALUES (?,?,?,?,?,?,'approved',?,?,?,?)""",
            (identifier,actor,payload['recipient'],payload['message'],payload['purpose'],payload_hash(payload),now,now+3600,now,batch[0]['job_id']))
        db.executemany('UPDATE phone_notices SET followup_id=? WHERE job_id=?',[(identifier,r['job_id']) for r in batch])


def close_stale_streams():
    now=time.time()
    with phone.store().db() as db:
        db.execute("""UPDATE phone_calls SET ended=COALESCE(ended,?) WHERE id IN
            (SELECT call_id FROM phone_live_streams WHERE state='active' AND COALESCE(last_seen,created)<?)""",(now,now-45))
        db.execute("""UPDATE phone_live_streams SET state='closed',closed=?,reason='connection_lost'
            WHERE state='active' AND COALESCE(last_seen,created)<?""",(now,now-45))
