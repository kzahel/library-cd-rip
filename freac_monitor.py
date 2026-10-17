"""Run fre:ac as a child process; success requires both exit status and MP3 validation."""
import hashlib
import os
from pathlib import Path
import re
import subprocess
import threading
import time

from monitor import Monitor, MP3
from storage import read_json, write_json


class FreacMonitor(Monitor):
    def __init__(self,state_dir,drive,exe=None,music_root=None,drive_index=0):
        super().__init__(state_dir,drive,music_root)
        self.drive_index=drive_index
        self.exe=Path(exe) if exe else state_dir/'freac/freac-1.1.7-x64/freaccmd.exe'
        if not self.exe.exists():
            raise FileNotFoundError('fre:ac is not installed in the helper data directory')
        self.process=None
        self.rip_signature=None
        self.index=0
        self.total_tracks=0
        self.track_progress=0
        self.rip_complete=False
        self.fault=None
        self.output=None
        self.lengths=[]
        self.transcript=''
        self.rip_started=time.time()
        self.lock=threading.Lock()
        self.receipts=read_json(self.state_dir/'verified-tracks.json',{})
        self.last_output_size=0
        self.last_output_change=time.time()

    def publish(self,**values):
        if values.get('phase')=='empty':
            values['phase']='ready'
        if values.get('phase')=='ripping' and self.rip_signature==self.signature:
            if self.process and self.lengths:
                # CBR output provides a direct byte-based indication of how
                # much audio has been written, including within long tracks.
                if self.output and self.output.exists():
                    encoded_seconds=max(0,self.output.stat().st_size-4096)/24000
                    self.track_progress=min(99.5,100*encoded_seconds/self.lengths[self.index-1])
                seconds=sum(self.lengths[:self.index-1])+self.lengths[self.index-1]*self.track_progress/100
                values['progress']=min(99,int(100*seconds/sum(self.lengths)))
                values['track']=self.index
                if seconds>0:
                    values['eta']=round((sum(self.lengths)-seconds)*(time.time()-self.rip_started)/seconds)
            values['detail']='Copying your CD with fre:ac. Keep the tray closed.'
        super().publish(**values)

    def completion_allowed(self):
        return self.rip_complete or any(r.get('signature')==self.signature for r in self.records)

    def abort(self):
        process=self.process
        if process and process.poll() is None:
            process.terminate()
            try: process.wait(timeout=5)
            except subprocess.TimeoutExpired:
                process.kill()
                process.wait(timeout=5)
        if self.process is process: self.process=None

    def capture(self,process,log_path):
        with log_path.open('ab') as log:
            buffer=''
            while True:
                chunk=process.stdout.read(1)
                if not chunk: break
                log.write(chunk)
                if chunk in [b'\r',b'\n']:
                    log.flush()
                    with self.lock:
                        self.transcript=(self.transcript+'\n'+buffer)[-12000:]
                        if self.process is process:
                            matches=re.findall(r'(\d+(?:\.\d+)?)\s*%',buffer)
                            if matches: self.track_progress=min(100,float(matches[-1]))
                    buffer=''
                else:
                    buffer+=chunk.decode('utf-8',errors='replace')
        process.stdout.close()

    def valid(self,path,index):
        if not path.exists() or not self.closed(path): return False
        try:
            info=MP3(path).info
            return abs(info.length-self.lengths[index-1])<2 and not info.sketchy
        except Exception:
            return False

    def start_next(self):
        self.index+=1
        while self.index<=self.total_tracks:
            self.output=self.folder/f'{self.index:02d} Track {self.index}.mp3'
            receipt=self.receipts.get(self.signature,{}).get(str(self.index))
            if receipt and self.valid(self.output,self.index) and hashlib.sha256(self.output.read_bytes()).hexdigest()==receipt:
                self.index+=1
                continue
            if self.output.exists():
                self.output.rename(self.output.with_suffix(f'.incomplete-{time.time_ns()}.mp3'))
            self.track_progress=0
            self.last_output_size=0
            self.last_output_change=time.time()
            command=[str(self.exe),f'--drive={self.drive_index}',f'--track={self.index}','--encoder=lame',
                     '--timeout=900','-o',str(self.output),'--','-m','CBR','-b','192']
            self.process=subprocess.Popen(command,cwd=str(self.exe.parent),stdout=subprocess.PIPE,
                                          stderr=subprocess.STDOUT,creationflags=subprocess.CREATE_NO_WINDOW)
            log=self.state_dir/f'freac-{hashlib.sha256(self.signature.encode()).hexdigest()[:12]}-{self.index:02d}.log'
            threading.Thread(target=self.capture,args=(self.process,log),daemon=True).start()
            return
        self.rip_complete=True
        self.process=None

    def tick(self):
        if getattr(self,'retry_requested',False):
            self.retry_requested=False; self.fault=None; self.rip_signature=None
            self.abort()
        if self.fault:
            self.publish(phase='error',album=self.config().get('title','Music CD'),
                         detail='Copying stopped. Leave the CD inside and ask a grown-up. '+self.fault)
            return
        # While fre:ac owns the drive, do not ask a second CD API to open or
        # interrogate it. Some USB drives report no media during exclusive reads.
        # The encoder's exit code and validated output govern active ripping.
        if self.process:
            code=self.process.poll()
            if code is None:
                size=self.output.stat().st_size if self.output and self.output.exists() else 0
                if size!=self.last_output_size:
                    self.last_output_size=size
                    self.last_output_change=time.time()
                if time.time()-self.last_output_change>300:
                    self.abort()
                    self.fault='The copier made no progress for five minutes.'
                    self.publish(phase='error',detail=self.fault+' Please ask a grown-up.')
                    return
                self.publish(phase='ripping',album=self.config().get('title','Music CD'),
                             tracks=self.total_tracks,track=self.index,saved=self.index-1)
                return
            if code!=0 or not self.valid(self.output,self.index):
                self.fault=f'fre:ac could not finish track {self.index} (exit {code}).'
                self.process=None
                self.publish(phase='error',detail='Copying stopped. Ask a grown-up. '+self.fault)
                return
            self.process=None
            self.receipts.setdefault(self.signature,{})[str(self.index)]=hashlib.sha256(self.output.read_bytes()).hexdigest()
            write_json(self.state_dir/'verified-tracks.json',self.receipts)
            (self.state_dir/'freac-verified').touch()
            self.start_next()
            if self.process:
                self.publish(phase='ripping',album=self.config().get('title','Music CD'),
                             tracks=self.total_tracks,track=self.index,saved=self.index-1)
                return
        super().tick()
        if (self.state_dir/'maintenance').exists(): return
        if not self.signature:
            self.abort(); self.rip_signature=None; self.rip_complete=False
            return
        if self.done: return
        if any(r.get('signature')==self.signature for r in self.records):
            # Give the base monitor time to revalidate an already saved album;
            # restarting the helper must not start another copy of that CD.
            return
        if self.signature!=self.rip_signature:
            self.abort()
            self.rip_signature=self.signature
            self.lengths=[int(x)/1000 for x in self.signature.split(',')]
            self.total_tracks=len(self.lengths)
            self.index=0; self.rip_complete=False
            self.rip_started=time.time()
            key=hashlib.sha256(self.signature.encode()).hexdigest()[:16]
            self.folder=self.music_root/'.library-cd-rip-staging'/self.state_dir.name/key
            self.folder.mkdir(parents=True,exist_ok=True)
            self.start_next()

    def run(self):
        try: super().run()
        finally: self.abort()

    def find_folder(self,lengths):
        # Never adopt some unrelated MP3 on the basis of its duration.
        record=next((r for r in self.records if r.get('signature')==self.signature),None)
        return Path(record['folder']) if record and record.get('folder') else None
