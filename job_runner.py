from __future__ import annotations
import time
from concurrent.futures import ThreadPoolExecutor
from core import db
from core.provision import run_job

POOL=ThreadPoolExecutor(max_workers=2, thread_name_prefix='omega-provision')
INFLIGHT=set()

def pump():
    for job in db.list_active_jobs(20):
        if job['status']!='queued' or job['id'] in INFLIGHT: continue
        INFLIGHT.add(job['id'])
        fut=POOL.submit(run_job,job['id'])
        fut.add_done_callback(lambda _f,jid=job['id']: INFLIGHT.discard(jid))

def main():
    db.init_db(); db.reset_stale_jobs()
    while True:
        try: pump()
        except Exception as exc: print(f'[Omega jobs] {exc}',flush=True)
        time.sleep(2)

if __name__=='__main__': main()
