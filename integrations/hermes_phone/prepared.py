"""One fully specified action through the native guards and receipt ledger."""
import json
import time
from . import performance,operations,messaging


def run(job,settings,perf,invoke=None):
    plan=json.loads(job.get('plan') or '{}') if isinstance(job.get('plan'),str) else job.get('plan',{})
    if plan.get('operation')=='find_send_article':
        from .articles import run as article
        return article(job,settings,perf)
    if plan.get('operation')=='calendar_invitation':
        from .calendar_invites import run as calendar
        return calendar(job,settings,perf)
    kind=plan.get('atomic_kind')
    if plan.get('operation')!='send_message' or kind not in {'email','imessage','whatsapp'}:
        raise ValueError('Unsupported prepared action')
    args=plan['message'];fresh=job.get('transcript','').rsplit('New caller speech: ',1)[-1]
    if not all(isinstance(args.get(k),str) and args[k] for k in ['recipient','message','approval_quote']):
        raise ValueError('Incomplete action payload')
    if args['approval_quote'] not in fresh or args['message'] not in args['approval_quote']:
        raise ValueError('Action payload lacks caller evidence')
    name='eli_phone_send_'+kind
    blocked=performance.before_tool(settings,tool_name=name,args=args)
    if blocked and blocked.get('block'):
        return {'success':False,'state':'blocked','error':blocked['message']}
    began=time.monotonic()
    if invoke:result=invoke(name,args)
    elif kind=='email':result=operations.send_email(args,settings)
    else:result=messaging.send_message(args,settings,channel=kind)
    performance.after_tool(settings,tool_name=name,args=args,result=result,duration_ms=round((time.monotonic()-began)*1000))
    return result


def execute(job,settings,perf):
    from gateway.session_context import set_session_vars,clear_session_vars
    identity=job['identity']
    tokens=set_session_vars(platform='eli_phone',chat_type='dm',chat_id='phone:'+identity['user_id'],
        user_id=identity['user_id'],user_name=identity['name'],message_id=job['id'],session_id='phone-action-'+job['id'])
    try:return run(job,settings,perf)
    finally:clear_session_vars(tokens)
