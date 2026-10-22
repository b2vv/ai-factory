import subprocess
import tempfile
from pathlib import Path
import unittest

LIB=Path(__file__).resolve().parents[2]/'runtime/scanners/container_control.sh'

class ControlTests(unittest.TestCase):
    def test_syntax(self):
        self.assertEqual(subprocess.run(['sh','-n',str(LIB)],capture_output=True).returncode,0)

    def test_paths(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp).resolve();(root/'a b').write_text('x');(root/'link').symlink_to(root/'a b')
            for path,code in [(str(root/'a b'),0),(str(root/'link'),3),(str(root/'missing'),3),('/a/../b',3),('/a\tb',3),('/a\rb',3)]:
                with self.subTest(path=path):
                    r=subprocess.run(['sh','-c','. "$1"; host_path_check "$2"','sh',str(LIB),path],capture_output=True,timeout=5)
                    self.assertEqual(r.returncode,code)

    def test_nonzero_separate_receipts(self):
        with tempfile.TemporaryDirectory() as tmp:
            r=subprocess.run(['sh','-c','. "$1"; CONTROL_WORK=$2; CONTROL_SEQUENCE=0; CONTROL_EXPIRED=0; control_call sh -c "echo out; echo err >&2; exit 7"','sh',str(LIB),tmp],capture_output=True,timeout=5)
            self.assertEqual(r.returncode,7)
            self.assertEqual((Path(tmp)/'command-1.stdout').read_text(),'out\n')
            self.assertEqual((Path(tmp)/'command-1.stderr').read_text(),'err\n')
            self.assertEqual((Path(tmp)/'command-1.exit').read_text(),'7\n')

    def test_output_cap(self):
        with tempfile.TemporaryDirectory() as tmp:
            r=subprocess.run(['sh','-c','. "$1"; CONTROL_WORK=$2; CONTROL_SEQUENCE=0; CONTROL_EXPIRED=0; control_call sh -c "while :; do printf 012345678901234567890123456789; done"','sh',str(LIB),tmp],capture_output=True,timeout=10)
            self.assertNotEqual(r.returncode,0)
            self.assertLessEqual((Path(tmp)/'command-1.stdout').stat().st_size,1024*1024)

if __name__=='__main__':unittest.main()

class LifecycleTests(unittest.TestCase):
    def run_script(self, script, tmp, timeout=12):
        return subprocess.run(['sh','-c','. "$1"; '+script,'sh',str(LIB),tmp],capture_output=True,timeout=timeout)

    def test_cleanup_success_and_failure(self):
        for fail in [False,True]:
            with tempfile.TemporaryDirectory() as tmp:
                script='cleanup_exact_intents() { echo called > "$2/unused"; }; '
                script='cleanup_exact_intents() { printf called > "$CONTROL_WORK/cleanup-called"; return '+('1' if fail else '0')+'; }; control_init "$2"; control_shutdown'
                r=self.run_script(script,tmp)
                self.assertEqual(r.returncode!=0,fail)
                self.assertEqual((Path(tmp)/'cleanup-state').read_text(),('UNKNOWN' if fail else 'CONFIRMED')+'\n')

    def test_parent_only_term_stops_flow_and_runs_cleanup(self):
        import os,signal,time
        with tempfile.TemporaryDirectory() as tmp:
            script='cleanup_exact_intents() { printf called > "$CONTROL_WORK/cleanup-called"; }; control_init "$2"; printf ready > "$2/ready"; control_call sleep 30; printf UNSAFE > "$2/continued"'
            p=subprocess.Popen(['sh','-c','. "$1"; '+script,'sh',str(LIB),tmp],stdout=subprocess.PIPE,stderr=subprocess.PIPE)
            try:
                limit=time.monotonic()+3
                while not (Path(tmp)/'ready').exists() and time.monotonic()<limit:time.sleep(.01)
                self.assertTrue((Path(tmp)/'ready').exists());os.kill(p.pid,signal.SIGTERM)
                p.communicate(timeout=8);self.assertEqual(p.returncode,2)
                self.assertTrue((Path(tmp)/'cleanup-called').exists());self.assertFalse((Path(tmp)/'continued').exists())
            finally:
                if p.poll() is None:p.kill();p.communicate()

    def test_deadline_during_uncertain_create(self):
        with tempfile.TemporaryDirectory() as tmp:
            script='cleanup_exact_intents() { cp "$CONTROL_WORK/container-intents" "$CONTROL_WORK/reconciled"; }; control_init "$2"; printf factory-test > "$2/container-intents"; control_stop_timer "$CONTROL_TIMER"; control_start_timer 2; CONTROL_TIMER=$CONTROL_NEW_TIMER; control_call sleep 30; printf UNSAFE > "$2/continued"'
            r=self.run_script(script,tmp)
            self.assertEqual(r.returncode,2);self.assertEqual((Path(tmp)/'reconciled').read_text(),'factory-test');self.assertFalse((Path(tmp)/'continued').exists())

    def test_timer_cancel_healthy(self):
        with tempfile.TemporaryDirectory() as tmp:
            script='cleanup_exact_intents() { return 0; }; control_init "$2"; control_stop_timer "$CONTROL_TIMER"; control_start_timer 5; CONTROL_TIMER=$CONTROL_NEW_TIMER; control_shutdown; sleep 2; printf healthy > "$2/healthy"'
            r=self.run_script(script,tmp);self.assertEqual(r.returncode,0);self.assertTrue((Path(tmp)/'healthy').exists())

    def test_expired_cleanup_can_still_call_commands(self):
        with tempfile.TemporaryDirectory() as tmp:
            r=self.run_script('cleanup_exact_intents() { control_call sh -c "exit 0"; }; control_init "$2"; CONTROL_EXPIRED=1; control_shutdown',tmp)
            self.assertNotEqual(r.returncode,0);self.assertEqual((Path(tmp)/'cleanup-state').read_text(),'CONFIRMED\n')

class EntrypointTests(unittest.TestCase):
    def test_bootstrap_bad_image_never_creates_or_starts(self):
        import os
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp).resolve();binpath=root/'bin';binpath.mkdir()
            docker=binpath/'docker';docker.write_text('#!/bin/sh\nprintf "%s\\n" "$*" >> "$MOCK_LOG"\ncase "$1" in image) echo "wrong|linux/amd64|10";; esac\n');docker.chmod(0o700)
            for name in ['config','socket','compose']:(root/name).write_text('fixture')
            env=dict(os.environ,PATH=str(binpath)+':'+os.environ['PATH'],MOCK_LOG=str(root/'docker.log'))
            script=LIB.with_name('scan.sh')
            r=subprocess.run(['sh',str(script),'scan',str(root/'config'),str(root/'run'),str(root/'socket'),str(root/'compose'),'a'*64],env=env,capture_output=True,timeout=12)
            self.assertEqual(r.returncode,3,r.stderr.decode());calls=(root/'docker.log').read_text()
            self.assertNotIn('create',calls);self.assertNotIn('start',calls)

    def test_receipt_write_failure_nonzero(self):
        with tempfile.TemporaryDirectory() as tmp:
            Path(tmp,'command-1.exit').mkdir()
            r=subprocess.run(['sh','-c','. "$1"; CONTROL_WORK=$2;CONTROL_SEQUENCE=0;CONTROL_EXPIRED=0;control_call sh -c "exit 0"','sh',str(LIB),tmp],capture_output=True,timeout=5)
            self.assertNotEqual(r.returncode,0)

class CleanupDeadlineTest(unittest.TestCase):
    def test_single_cleanup_deadline_no_false_pass(self):
        import time
        with tempfile.TemporaryDirectory() as tmp:
            script='cleanup_exact_intents() { control_call sleep 30; }; control_init "$2"; control_shutdown; printf UNSAFE > "$2/continued"'
            start=time.monotonic()
            r=subprocess.run(['sh','-c','. "$1"; '+script,'sh',str(LIB),tmp],capture_output=True,timeout=22)
            self.assertEqual(r.returncode,2);self.assertLess(time.monotonic()-start,21)
            self.assertEqual((Path(tmp)/'cleanup-state').read_text(),'UNKNOWN\n');self.assertFalse((Path(tmp)/'continued').exists())
