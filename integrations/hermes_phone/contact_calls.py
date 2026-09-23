"""Submit the current validated call job once; never invent a call recipient."""
import time


def run(job,settings,perf,api=None,timeout=35):
    if api is None:
        from . import api_request
        api=api_request
    name='eli_phone_call_contact';began=time.monotonic()
    perf.record(job['id'],'progress',name,'running',content='Submitting the explicitly requested call.')
    while True:
        try:result=api('/internal/phone/jobs/'+job['id']+'/contact-call',{'claim':job['claim']})
        except Exception as exc:
            return {'success':False,'state':'uncertain','error':'The call submission could not be confirmed ('+type(exc).__name__+'). It will not be repeated automatically.'}
        if result.get('terminal') and result['state']!='completed':
            return {'success':False,'state':'uncertain' if result['state']=='uncertain' else 'failed','error':result['content']}
        if result.get('call_sid'):
            perf.record(job['id'],'action',name,'sent',content='The provider accepted one call. This does not confirm the recipient heard the message.')
            perf.record(job['id'],'timing',name,'ok',int((time.monotonic()-began)*1000))
            return {'success':True,'state':'sent','message_id':result['call_sid'],'source_verified':True,'result':result['content']}
        if time.monotonic()-began>=timeout:
            return {'success':False,'state':'uncertain','error':'The call is saved but dialing is not yet confirmed. Check its existing status; do not request a duplicate.'}
        time.sleep(.5)
