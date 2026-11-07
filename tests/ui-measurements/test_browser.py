"""Synthetic rendered DOM fixtures; no product, native agent or visual-QA claim."""
import hashlib,html,json,os,re,shutil,subprocess,tempfile,unittest
from pathlib import Path
ROOT=Path(__file__).resolve().parents[2]
HELPER=ROOT/'skills/ui-measurements/scripts/measure-ui.cjs'
BODY='<div id="clip" style="width:60px;white-space:nowrap;overflow:hidden">A deliberately long label that must fit</div><div id="fit" style="width:300px">Fits</div><div id="scroll" style="width:60px;overflow-x:auto"><div style="width:300px">Intentional table scroll</div></div>'
class BrowserMeasurements(unittest.TestCase):
 @classmethod
 def setUpClass(cls):
  cls.chrome=os.environ.get('CHROME_BIN') or shutil.which('chromium') or shutil.which('google-chrome')
  if not cls.chrome:
   if os.environ.get('AI_FACTORY_REQUIRE_UI_BROWSER')=='1':raise RuntimeError('Required Chrome/Chromium unavailable; set CHROME_BIN')
   raise unittest.SkipTest('NOT_TESTED real browser: no existing Chrome/Chromium configured')
 def observe(self,checks,width=390,body=BODY,extra=''):
  config={'context':{'revision':'synthetic-r1','state':'ready','fixture':'layout-v1','evidence':'fixture:rendered','route':'','settled':True},'checks':checks}
  with tempfile.TemporaryDirectory() as tmp:
   p=Path(tmp).resolve();script=HELPER.read_text();fixture='<!doctype html><meta charset=utf-8><style>body{margin:0}</style>'+body
   driver="""const frame=document.createElement('iframe');frame.style.cssText='border:0;width:WIDTHpx;height:844px';document.body.append(frame);frame.onload=async()=>{await frame.contentDocument.fonts.ready;const w=frame.contentWindow;const config=w.JSON.parse(CONFIG);config.context.route=w.location.pathname;const measure=w.Function(SOURCE+';return measureUI;')();EXTRA;try{const before=w.document.documentElement.outerHTML;const report=measure(config);report.fixtureDomUnchanged=before===w.document.documentElement.outerHTML;document.getElementById('result').textContent=JSON.stringify(report);}catch(e){document.getElementById('result').textContent=JSON.stringify({error:e.message});}};frame.srcdoc=FIXTURE;""".replace('WIDTH',str(width)).replace('CONFIG',json.dumps(json.dumps(config))).replace('SOURCE',json.dumps(script)).replace('FIXTURE',json.dumps(fixture)).replace('EXTRA',extra)
   f=p/'fixture.html';f.write_text('<!doctype html><pre id="result"></pre><script>'+driver.replace('</script',r'<\/script')+'</script>')
   r=subprocess.run([self.chrome,'--headless=new','--disable-gpu','--no-first-run','--no-default-browser-check','--disable-background-networking','--user-data-dir='+str(p/'profile'),'--virtual-time-budget=2000','--window-size=1600,1000','--dump-dom',f.as_uri()],capture_output=True,text=True,timeout=25)
   self.assertEqual(r.returncode,0,r.stderr[-1000:]);match=re.search(r'<pre id="result">(.*?)</pre>',r.stdout,re.S);self.assertIsNotNone(match,r.stdout[-1000:]);result=json.loads(html.unescape(match[1]));self.assertNotIn('error',result);self.assertTrue(result['fixtureDomUnchanged']);artifact=os.environ.get('AI_FACTORY_UI_EVIDENCE_DIR')
   if artifact:
    out=Path(artifact);self.assertTrue(out.is_absolute() and out.is_dir());(out/(self.id().split('.')[-1]+'-'+str(width)+'.json')).write_text(json.dumps({'helper_sha256':hashlib.sha256(script.encode()).hexdigest(),'browser':'configured Chrome headless, synthetic child frame','result':result},indent=2)+'\n')
   return result
 def test_clip_is_a_defect_but_fitting_label_and_local_scroll_are_valid(self):
  checks=[{'id':'clip','kind':'fit','selector':'#clip'},{'id':'fit','kind':'fit','selector':'#fit'},{'id':'scroll','kind':'fit','selector':'#scroll','scrollX':{'reason':'table requires columns','evidence':'fixture:table-contract'}}]
  result=self.observe(checks);self.assertEqual([x['status'] for x in result['checks']],['FAIL','PASS','PASS']);self.assertEqual(result['actual']['viewport']['width'],390);self.assertEqual(result['actual']['frame'],'child')
 def test_solid_contrast_is_measured_but_gradient_is_unknown(self):
  body='<p id="low" style="background:rgb(255,255,255);color:rgb(200,200,200)">Low</p><p id="good" style="background:white;color:black">Good</p><p id="gradient" style="background:white linear-gradient(black,white);color:black">Unknown</p>'
  checks=[{'id':n,'kind':'contrast','selector':'#'+n,'minimum':4.5,'source':'WCAG 1.4.3 AA normal text'} for n in ['low','good','gradient']]
  r=self.observe(checks,body=body);self.assertEqual([x['status'] for x in r['checks']],['FAIL','PASS','NOT_TESTED']);self.assertEqual(r['checks'][1]['actual']['ratio'],21)
 def test_only_declared_stable_fixture_values_are_invariants(self):
  body='<p id="stable">42</p><p id="changed">43</p><p id="live">44</p><p id="clock">999</p>'
  checks=[{'id':n,'kind':'text','selector':'#'+n,'expected':'42','fixture':{'id':'layout-v1','source':'seed:revision1','stable':n!='live'}} for n in ['stable','changed','live']]
  r=self.observe(checks,body=body);self.assertEqual([x['status'] for x in r['checks']],['PASS','FAIL','NOT_TESTED']);self.assertEqual(r['checks'][1]['actual']['value'],'43')
 def test_real_geometry_at_four_baseline_class_widths(self):
  for width in [390,768,1024,1440]:
   r=self.observe([{'id':'clip','kind':'fit','selector':'#clip'}],width=width)
   self.assertEqual(r['actual']['viewport']['width'],width);self.assertEqual(r['checks'][0]['status'],'FAIL')
 def test_vertical_page_scroll_is_not_horizontal_overflow(self):
  body='<div style="height:1200px;width:100%">Tall page</div>'
  r=self.observe([{'id':'page','kind':'fit','selector':':root','axis':'x'}],body=body)
  self.assertEqual(r['checks'][0]['status'],'PASS');self.assertGreater(r['checks'][0]['actual']['scrollHeight'],r['checks'][0]['actual']['clientHeight'])
  r=self.observe([{'id':'page','kind':'fit','selector':':root','axis':'x'}],body='<div style="width:1200px">Unintended page overflow</div>');self.assertEqual(r['checks'][0]['status'],'FAIL')
 def test_unknown_render_states_and_unsupported_paint_are_not_pass(self):
  styles=['opacity:.5','filter:blur(1px)','backdrop-filter:blur(1px)','mix-blend-mode:multiply','transform:translateX(1px)','perspective:1px','clip-path:inset(1px)','mask-image:linear-gradient(black,transparent)','text-shadow:1px 1px black','background-clip:text','-webkit-text-fill-color:red','-webkit-text-stroke:1px red','background-color:rgba(255,255,255,.5)','content-visibility:hidden','content-visibility:auto','visibility:hidden','box-shadow:inset 0 0 100px black','text-indent:-20px','background-clip:content-box','width:20px;white-space:nowrap']
  body=''.join('<p id="c'+str(i)+'" style="background:white;color:black;'+css+'">Text</p>' for i,css in enumerate(styles))
  checks=[{'id':'c'+str(i),'kind':'contrast','selector':'#c'+str(i),'minimum':4.5,'source':'agreed fixture threshold'} for i in range(len(styles))]
  r=self.observe(checks,body=body);self.assertEqual([x['status'] for x in r['checks']],['NOT_TESTED']*len(styles))
 def test_actual_running_animation_blocks_a_fit_claim(self):
  r=self.observe([{'id':'fit','kind':'fit','selector':'#fit'}],extra="w.document.getElementById('fit').animate([{opacity:1},{opacity:.5}],{duration:100000,iterations:Infinity})")
  self.assertEqual(r['checks'][0]['status'],'NOT_TESTED');self.assertEqual(r['checks'][0]['reason'],'active-animation')
 def test_missing_ambiguous_hidden_and_wrong_route_are_unknown(self):
  r=self.observe([{'id':'missing','kind':'fit','selector':'#absent'},{'id':'ambiguous','kind':'fit','selector':'div'},{'id':'hidden','kind':'fit','selector':'#hidden'}],body=BODY+'<div style="display:none"><div id="hidden">Hidden</div></div>')
  self.assertEqual([x['status'] for x in r['checks']],['NOT_TESTED']*3)
  r=self.observe([{'id':'fit','kind':'fit','selector':'#fit'}],extra="config.context.route='/wrong-state'");self.assertEqual(r['checks'][0]['reason'],'route-mismatch')
 def test_first_letter_and_first_line_paint_override_are_unknown(self):
  body='<style>#letter::first-letter{color:white}#line::first-line{color:white}</style><p id="letter" style="background:white;color:black">W</p><p id="line" style="background:white;color:black">White text</p>'
  checks=[{'id':n,'kind':'contrast','selector':'#'+n,'minimum':4.5,'source':'agreed normal text'} for n in ['letter','line']]
  r=self.observe(checks,body=body);self.assertEqual([x['status'] for x in r['checks']],['NOT_TESTED','NOT_TESTED'])
 def test_generated_before_and_after_text_remain_unsupported(self):
  body='<style>#before::before{content:"prefix";color:white}#after::after{content:"suffix";color:white}</style><p id="before" style="background:white;color:black">Text</p><p id="after" style="background:white;color:black">Text</p>'
  checks=[{'id':n,'kind':'contrast','selector':'#'+n,'minimum':4.5,'source':'agreed threshold'} for n in ['before','after']]
  r=self.observe(checks,body=body);self.assertEqual([x['status'] for x in r['checks']],['NOT_TESTED','NOT_TESTED'])
if __name__=='__main__':unittest.main(verbosity=2)
