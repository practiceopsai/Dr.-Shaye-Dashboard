"""Durable questions and caller-bound answers in the existing phone agent."""
import json
import re
import time

from .performance import current


def question_for(perf, identifier):
    with perf.db() as db:
        db.execute('CREATE TABLE IF NOT EXISTS clarification_questions(job_id TEXT PRIMARY KEY,question TEXT NOT NULL,created REAL NOT NULL)')
        row=db.execute('SELECT question FROM clarification_questions WHERE job_id=?',(identifier,)).fetchone()
    return row['question'] if row else ''


def save_question(perf, identifier, question):
    question=question.strip()
    if not 4<=len(question)<=1000 or re.search(r'\bMRN\b|patient\s+\w+\s+\w+|\bBearer\s+|sk-[a-zA-Z0-9]{12}',question,re.I):
        raise ValueError('Use one brief question without patient information or secrets')
    question_for(perf,identifier)
    with perf.db() as db:
        db.execute('INSERT OR IGNORE INTO clarification_questions VALUES (?,?,?)',(identifier,question,time.time()))
    perf.record(identifier,'timing','clarification','waiting_for_input')
    return question_for(perf,identifier)


def clarify(args, settings, *, home=None, session=None):
    active=current(settings,home=home,session=session)
    if not active:
        return {'success':False,'error':'An active phone request is required.'}
    perf,job,_=active
    try:
        question=save_question(perf,job['id'],str(args.get('question','')))
    except ValueError as exc:
        return {'success':False,'error':str(exc)}
    return {'success':True,'state':'waiting_for_input','question':question,
            'instruction':'The task is durably paused. Return only this question; do not execute further tools. It will be asked at a conversational break or followed up after hangup.'}


def answer_clarification(args, settings, *, home=None, session=None, api=None):
    active=current(settings,home=home,session=session)
    if not active:
        return {'success':False,'error':'An active phone request is required.'}
    perf,job,fresh=active
    identifier=str(args.get('request_id',''))
    quote=str(args.get('answer_quote','')).strip()
    if identifier not in {q['id'] for q in job.get('open_questions',[])} or not quote or ' '.join(quote.casefold().split()) not in ' '.join(fresh.casefold().split()):
        return {'success':False,'error':'Select an actual open question and the current caller answer. If the target is ambiguous, clarify first.'}
    if api is None:
        from . import api_request
        api=api_request
    result=api('/internal/phone/jobs/'+job['id']+'/answer',{'claim':job['claim'],'request_id':identifier,'answer':quote})
    perf.record(job['id'],'timing','clarification_answer','resumed')
    return {**result,'success':True,'instruction':'The original task has a durable continuation. Do not execute that task again in this answering turn. Handle any independent new request separately.'}


def possible_question(answer):
    # Recovery when the model returns a needed question without calling the
    # structured tool. Do not misclassify a friendly "anything else?" as a task.
    return bool('?' in answer and len(answer)<=1000 and re.search(
        r"\b(which|what (?:message|text|time|date|address|number|account)|could you|can you|should I|do you want|please (?:confirm|provide|specify))\b",answer,re.I))


SCHEMAS=[
    {'name':'eli_phone_clarify','description':'Pause this task durably when an essential detail, recipient, message, account, date or approval is missing. Ask one concise question. The caller can keep speaking; the question is delivered at a break and survives hangup.',
     'parameters':{'type':'object','properties':{'question':{'type':'string'}},'required':['question']}},
    {'name':'eli_phone_answer_clarification','description':'Resume exactly one open phone task using the current caller answer. Use only when the answer clearly addresses that question; otherwise clarify. This queues the continuation; never execute it again in this turn.',
     'parameters':{'type':'object','properties':{'request_id':{'type':'string'},'answer_quote':{'type':'string'}},'required':['request_id','answer_quote']}}
]
