"""Run with the installed Hermes Python and source on PYTHONPATH; no real sends.

This complements unit tests with the real gateway source/auth contract that a
permissive Mock did not exercise during the original rollout.
"""
import asyncio
import importlib.util
import json
import os
from pathlib import Path
import tempfile
from types import SimpleNamespace


def main():
    with tempfile.TemporaryDirectory(prefix='eli-text-contract-') as tmp:
        os.environ['HERMES_HOME']=tmp
        os.environ['GATEWAY_ALLOWED_USERS']='contract-owner'
        from gateway.session import SessionSource
        from gateway.config import Platform
        from gateway.authz_mixin import GatewayAuthorizationMixin
        from gateway.platforms.base import SendResult
        spec=importlib.util.spec_from_file_location('_cross_contract',Path(__file__).with_name('cross_channel.py'))
        cross=importlib.util.module_from_spec(spec);spec.loader.exec_module(cross)

        class Gateway(GatewayAuthorizationMixin):
            adapters={}
            def _adapter_profile_for_source(self,source):return None
            def _adapter_authorization_is_upstream(self,*args,**kwargs):return False
            def _authorization_adapter(self,*args,**kwargs):return None
            def _adapter_for_source(self,source):return transport

        gateway=Gateway()
        saved={'platform':'photon','chat_id':'contract-chat','user_id':'contract-owner','chat_type':'dm'}
        # Historical serialized input never gets to assert relay authorization.
        source=cross.restore_source({**saved,'delivered_via_upstream_relay':True})
        assert isinstance(source,SessionSource) and source.delivered_via_upstream_relay is False
        assert gateway._is_user_authorized(source) is True
        assert gateway._is_user_authorized(cross.restore_source({**saved,'user_id':'stranger'})) is False
        try:
            gateway._is_user_authorized(SimpleNamespace(**{**saved,'platform':Platform('photon')}))
        except AttributeError as exc:
            assert 'delivered_via_upstream_relay' in str(exc)
        else:raise AssertionError('The observed legacy sender-contract failure did not reproduce')

        sent=[];submitted=[]
        class Transport:
            async def send(self,chat_id,content,**kwargs):
                sent.append((chat_id,content));return SendResult(success=True,message_id='simulated-receipt')
        transport=Transport()
        database=Path(tmp)/'journal.sqlite3';cross.path=lambda:database;cross._ready=True
        event=SimpleNamespace(source=source,text='Cancel the presentation task',message_id='message1')
        settings={'identities':{'owner@example.com':{'user_id':'contract-owner'}}}
        assert cross.hook(settings,event=event,gateway=gateway)['action']=='skip'
        adapter=SimpleNamespace(journal=SimpleNamespace(path=database))
        def api(path,payload):
            if path.endswith('/utterance'):
                submitted.append(payload);return {'intake_id':'intake1','call_id':'text:contract'}
            return {'notices':[{'id':'question1','state':'waiting_for_input','content':'Which presentation?'}],'settled':False}
        asyncio.run(cross.process_item(adapter,api,gateway,cross.ready(database)[0]))
        asyncio.run(cross.process_item(adapter,api,gateway,cross.ready(database)[0]))
        assert len(submitted)==len(sent)==1
        for text in ['Who are you?','Hello?','?']:
            event.text=text;assert cross.hook(settings,event=event,gateway=gateway) is None
        event.text='The quarterly review';event.message_id='answer1'
        assert cross.hook(settings,event=event,gateway=gateway)['action']=='skip'
        # Exercise the new call phrases with the installed gateway auth/source
        # classes; neither the planner nor a telephony provider is invoked here.
        for index,text in enumerate(['Call me','Can you give me a call?',
                                      'Call Dr. Shaye and tell him the report is ready']):
            event.text=text;event.message_id='call-'+str(index)
            assert cross.hook(settings,event=event,gateway=gateway)['action']=='skip'
        for text in ['What did I ask on our last call?','Can you call people?']:
            event.text=text;assert cross.hook(settings,event=event,gateway=gateway) is None
        print(json.dumps({'passed':True,'native_source_and_authorization':True,'legacy_error_reproduced':True,
                          'simulated_handoffs':len(submitted),'simulated_replies':len(sent),'call_intake_cases':3,'real_sends':0}))


if __name__=='__main__':main()
