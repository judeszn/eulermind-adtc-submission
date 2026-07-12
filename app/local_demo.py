# VENDORED verbatim from the EulerMind research repo (github.com/judeszn/EulerMind)
# at commit 4ab0ddf - only import paths adapted. Canonical source + full
# experiment history live there. Do not edit here.
"""EulerMind local demo — the judge-facing entry point.

Single file, Python stdlib only (no pip installs, no cloud, no network
calls). Serves a browser UI at http://localhost:7860 that runs the REAL
certified pipeline: parser-first Formalizer -> exact Solver -> certifying
Verifier -> independently-written Checker, across the three validated
domains (LP, CSP, edge-AI deployment).

This is a demonstration interface, not a product (no Electron, no
installers, no deployment). It exists so a judge can disconnect Wi-Fi,
paste a problem, and watch a certified answer appear with every pipeline
stage visible.

    python3 -m app.local_demo
"""

from __future__ import annotations

import hashlib
import json
import time
from http.server import BaseHTTPRequestHandler, HTTPServer

from .state import ExecutionState

from .lp_formalizer import try_parse as lp_try_parse
from .lp_solver import (make_certificate as lp_make_cert,
                              recheck_certificate as lp_recheck,
                              solve_optimal as lp_solve)
from .lp_independent_checker import (
    independent_recheck as lp_independent)

from .csp_formalizer import CSPFormalizer
from .csp_solver import (make_certificate as csp_make_cert,
                               recheck_certificate as csp_recheck,
                               solve as csp_solve)
from .csp_independent_checker import (
    independent_recheck as csp_independent)

from .edge_ai_formalizer_1b import StructuredFormalizer
from .edge_ai_solver import (make_certificate as edge_make_cert,
                                   recheck_certificate as edge_recheck,
                                   solve_optimal as edge_solve)
from .edge_independent_checker import (
    independent_recheck as edge_independent)

PORT = 7860


def _cert_id(cert: dict) -> str:
    """Display-only identifier derived from the certificate's own content —
    never fabricated. Same certificate always yields the same ID."""
    digest = hashlib.sha256(
        json.dumps(cert, sort_keys=True, default=str).encode()
    ).hexdigest()
    return digest[:12].upper()


class _StubFallback:
    def formalize(self, state):
        return {"kind": "knapsack", "spec": None, "formalizer_tokens": 0}


def _solve_lp(spec: dict) -> dict:
    sol = lp_solve(spec)
    if sol["status"] != "optimal":
        return {"answer": f"LP status: {sol['status']}", "label": "Verified",
                "certificate": True, "independent": True}
    cert = lp_make_cert(spec, sol)
    rc = lp_recheck(cert)["accepted"]
    ind = lp_independent(cert)
    names = spec.get("var_names", {"x": "x", "y": "y"})
    answer = (f"{sol['x']:g} × {names['x']}, {sol['y']:g} × {names['y']} — "
              f"maximum profit {sol['profit']:g}")
    return {"answer": answer, "certificate": rc, "independent": ind["accepted"],
            "independent_note": ind["reason"], "cert_id": _cert_id(cert),
            "label": "Verified" if rc and ind["accepted"] else "Derived"}


def _solve_csp(spec: dict) -> dict:
    sol = csp_solve(spec)
    cert = csp_make_cert(spec, sol)
    rc = csp_recheck(cert)["accepted"]
    ind = csp_independent(cert)
    if sol["satisfiable"]:
        pairs = ", ".join(f"{e} → {p}" for e, p in sol["assignment"].items())
        answer = f"Valid assignment: {pairs}"
    else:
        answer = ("No valid assignment exists. Minimal conflicting constraint "
                  f"set has {len(sol['minimal_conflict'])} constraints — "
                  "refusing to fabricate an answer (Law 1).")
    return {"answer": answer, "certificate": rc, "independent": ind["accepted"],
            "independent_note": ind["reason"], "cert_id": _cert_id(cert),
            "label": "Verified" if rc and ind["accepted"] else "Derived"}


def _solve_edge(spec: dict) -> dict:
    sol = edge_solve(spec)
    if not sol["feasible"]:
        return {"answer": "No feasible deployment exists under these budgets.",
                "label": "Verified", "certificate": True, "independent": True}
    cert = edge_make_cert(spec, sol["counts"], sol["score"])
    rc = edge_recheck(cert)["accepted"]
    ind = edge_independent(cert)
    plan = ", ".join(f"{n} ×{c}" for n, c in sol["counts"].items() if c > 0)
    return {"answer": f"Deploy {plan} — score {sol['score']}",
            "certificate": rc, "independent": ind["accepted"],
            "independent_note": ind["reason"], "cert_id": _cert_id(cert),
            "label": "Verified" if rc and ind["accepted"] else "Derived"}


def solve(text: str) -> dict:
    t0 = time.perf_counter()
    stages = []

    spec = lp_try_parse(text)
    domain, result = None, None
    if spec is not None:
        domain = "Linear programming (theorem-backed: LP duality)"
        stages.append({"stage": "Formalized", "ok": True,
                       "note": "deterministic parser, 0 LLM calls"})
        result = _solve_lp(spec)
    else:
        st = ExecutionState(problem_id="demo", problem_text=text)
        csp_spec = CSPFormalizer().formalize(st).get("spec")
        if csp_spec is not None:
            domain = "Constraint satisfaction (enumeration-backed)"
            stages.append({"stage": "Formalized", "ok": True,
                           "note": "deterministic parser, 0 LLM calls"})
            result = _solve_csp(csp_spec)
        else:
            st2 = ExecutionState(problem_id="demo", problem_text=text)
            edge_spec = StructuredFormalizer(
                fallback_formalizer=_StubFallback()).formalize(st2).get("spec")
            if edge_spec is not None:
                domain = "Edge-AI deployment (enumeration-backed)"
                stages.append({"stage": "Formalized", "ok": True,
                               "note": "deterministic parser, 0 LLM calls"})
                result = _solve_edge(edge_spec)

    if result is None:
        return {"domain": None, "label": "Open", "tutor_eligible": True,
                "stages": [
                    {"stage": "Certified lane", "ok": False,
                     "note": "not a certified-domain problem — handing to the tutor lane"}],
                "answer": "",
                "ms": round((time.perf_counter() - t0) * 1000, 1)}

    stages.append({"stage": "Solved", "ok": True, "note": "exact deterministic solver"})
    stages.append({"stage": "Verified", "ok": result["certificate"],
                   "note": "re-checkable certificate"})
    stages.append({"stage": "Independently checked", "ok": result["independent"],
                   "note": result.get("independent_note", "")})
    return {"domain": domain, "label": result["label"], "stages": stages,
            "answer": result["answer"], "cert_id": result.get("cert_id"),
            "ms": round((time.perf_counter() - t0) * 1000, 1)}


# The two shipped ADTC test prompts (verbatim from the submission repo's
# metadata.json). They MUST work here - regression-tested in
# research/D5_prompt_compat/.
_LAGOS = ("A furniture workshop in Lagos makes two products: chairs and "
          "tables. Each chair needs 3 hours of carpentry and 2 hours of "
          "finishing; each table needs 5 hours of carpentry and 3 hours of "
          "finishing. The workshop has 240 carpentry hours and 150 "
          "finishing hours available this month. Each chair earns N4,500 "
          "profit and each table N7,000. How many chairs and tables should "
          "the workshop make to maximize profit, and what is the maximum "
          "profit? Show your reasoning and verify that your plan stays "
          "within both labour limits.")
_NAIROBI = ("A community health programme in Nairobi must assign four "
            "volunteers - Amina, Baraka, Chausiku, and David - to four "
            "clinics: Kibera, Kasarani, Embakasi, and Westlands, with "
            "exactly one volunteer per clinic. Amina cannot be assigned to "
            "Kibera. Baraka must be assigned to either Kasarani or "
            "Embakasi. If Chausiku is assigned to Kasarani, then David "
            "must be assigned to Westlands. David cannot be assigned to "
            "Embakasi. Find a valid assignment of volunteers to clinics, "
            "or explain clearly why none exists, and check your answer "
            "against every constraint.")


def _examples() -> list[dict]:
    # Four buttons only: three tutor-lane maths examples + one certified
    # example. Nairobi (test prompt 2) and the pinned Edge-AI instance still
    # work when pasted — the router is unchanged; only discovery is curated.
    return [{"name": "Quadratic equation (WAEC)",
             "text": "Solve 2x^2 + 7x + 3 = 0. Show your working."},
            {"name": "Simultaneous equations (WAEC)",
             "text": "Solve the simultaneous equations 3x + 2y = 16 and x - y = 3."},
            {"name": "Differentiation (WAEC)",
             "text": "Differentiate x^2 sin(x) with respect to x."},
            {"name": "Lagos workshop (certified)", "text": _LAGOS}]


PAGE = """<!doctype html><html><head><meta charset="utf-8">
<title>EulerMind</title><style>
body{font-family:-apple-system,system-ui,sans-serif;max-width:760px;margin:2rem auto;padding:0 1rem;color:#1a1a18;background:#faf9f5}
h1{font-size:1.5rem;margin-bottom:.2rem} .sub{color:#666;margin-top:0}
.sub2{color:#8a8372;margin-top:.15rem;font-size:.88rem}
.badges span{display:inline-block;background:#e1f5ee;color:#085041;border-radius:6px;padding:2px 10px;font-size:.8rem;margin-right:6px}
.trustkey{font-size:.76rem;color:#555;margin:.7rem 0 .2rem;line-height:2}
.trustkey b{font-weight:600;color:#333}
.k{display:inline-block;border-radius:6px;padding:1px 8px;font-weight:600;font-size:.72rem;margin-right:2px}
textarea{width:100%;height:170px;font-family:ui-monospace,monospace;font-size:.85rem;padding:.6rem;border:1px solid #ccc;border-radius:8px;box-sizing:border-box}
button{background:#1a1a18;color:#fff;border:0;border-radius:8px;padding:.55rem 1.4rem;font-size:.95rem;cursor:pointer;margin-top:.5rem}
button.ex{background:#fff;color:#1a1a18;border:1px solid #ccc;font-size:.8rem;padding:.3rem .8rem;margin-right:.4rem}
.stage{margin:.25rem 0;font-size:.92rem}.ok{color:#0f6e56}.fail{color:#a32d2d}
.label{display:inline-block;border-radius:6px;padding:3px 12px;font-weight:600;margin:.6rem 0}
.Verified{background:#e1f5ee;color:#085041}.Open{background:#faeeda;color:#633806}.Derived{background:#e6f1fb;color:#0c447c}.Heuristic{background:#faeeda;color:#633806}
.answer{background:#fff;border:1px solid #ddd;border-radius:8px;padding:.8rem 1rem;font-size:.95rem}
.legend{color:#8a8372;font-size:.78rem;margin:.3rem 0 .7rem}
.zonelabel{font-size:.68rem;text-transform:uppercase;letter-spacing:.05em;color:#8a8372;margin:.1rem 0 .45rem;font-weight:600}
.modelzone{border:1px dashed #d8d3c6;border-radius:10px;padding:.5rem .7rem;margin:.5rem 0}
.step{background:#fff;border:1px solid #e6e3db;border-left:3px solid #cfc9bd;border-radius:8px;padding:.45rem .8rem;margin:.35rem 0}
.stepchip{display:inline-block;background:#f0ede4;color:#6b6455;border-radius:5px;padding:1px 8px;font-size:.7rem;font-weight:600;text-transform:uppercase;letter-spacing:.03em;margin-bottom:.3rem}
.stepbody{white-space:pre-wrap;font-size:.92rem;line-height:1.45}
.answerbox{background:#fff;border:2px solid #c9a94b;border-radius:10px;padding:.6rem 1rem;margin:.6rem 0}
.answerval{font-size:1.5rem;font-weight:700;white-space:pre-wrap;color:#1a1a18}
.checkzone{border:1px solid #b9d9cc;background:#f5fbf8;border-radius:10px;padding:.5rem .7rem;margin:.5rem 0;font-family:ui-monospace,monospace}
.checkline{white-space:pre-wrap;font-size:.9rem}
.checkline.ok{color:#0f6e56}.checkline.fail{color:#a32d2d}
.why{font-size:.82rem;color:#555;margin-top:.45rem;font-family:-apple-system,system-ui,sans-serif}
.trusted{border:1px solid #b9d9cc;background:#f2fbf7;border-radius:10px;padding:.5rem .8rem;margin:.5rem 0}
.tline{font-size:.88rem;color:#0f6e56;line-height:1.75;font-family:-apple-system,system-ui,sans-serif}
.meta{color:#888;font-size:.8rem}</style></head><body>
<h1>EulerMind</h1>
<p class="sub">The offline maths tutor that knows the difference between what it has proved and what it has only inferred</p>
<p class="sub2">Every answer clearly tells you whether it was mathematically verified or is an AI explanation.</p>
<div class="badges"><span>✓ Works without internet</span><span>✓ Runs on ordinary school laptops</span><span>✓ Checks its answers — and says when it can't</span></div>
<div class="trustkey">
<span class="k Verified">Verified</span> independently certified ·
<span class="k Derived">Derived</span> machine-checked ·
<span class="k Heuristic">Heuristic</span> AI explanation only ·
<span class="k Open">Open</span> could not answer — says so</div>
<p class="meta">Examples: <span id="exbtns"></span></p>
<textarea id="q" placeholder="Paste any secondary-school maths question (WAEC/SSCE) — equations, factorising, differentiation… or a resource-allocation problem for the certified lane"></textarea><br>
<button onclick="go()">Solve</button>
<div id="out"></div>
<script>
const EXAMPLES = __EXAMPLES__;
const exb = document.getElementById('exbtns');
EXAMPLES.forEach(e=>{const b=document.createElement('button');b.className='ex';b.textContent=e.name;
  b.onclick=()=>{document.getElementById('q').value=e.text;};exb.appendChild(b);});
function esc(s){const d=document.createElement('div');d.textContent=s;return d.innerHTML;}
async function go(){
  const q=document.getElementById('q').value;
  const out=document.getElementById('out'); out.innerHTML='<p class="meta">solving…</p>';
  const r=await fetch('/solve',{method:'POST',body:JSON.stringify({text:q})});
  const d=await r.json();
  if(d.tutor_eligible){ return tutor(q, out, d); }
  let h='';
  if(d.domain) h+='<p class="meta">certified lane · '+d.domain+'</p>';
  h+='<div>'+d.stages.map(s=>'<div class="stage '+(s.ok?'ok':'fail')+'">'+(s.ok?'✓':'✗')+' '+s.stage+' <span class="meta">'+s.note+'</span></div>').join('')+'</div>';
  h+='<div class="label '+d.label+'">'+d.label+'</div>';
  h+='<div class="answer">'+esc(d.answer)+'</div>';
  if(d.cert_id) h+='<p class="meta">Certificate ID <code>'+esc(d.cert_id)+'</code> — sha256 of the certificate content, first 12 hex digits</p>';
  h+='<p class="meta">'+d.ms+' ms, fully local</p>';
  out.innerHTML=h;
}
// Σ2 lock: the MODEL ZONE renders the model's own words. The model emits a
// tag contract (<UNDERSTANDING>…</TAKEAWAY>); EULERMIND owns presentation —
// section titles, order, and plain-text maths notation are decided here, not
// by the model. COSMETIC ONLY: the trust decision uses the server-side parser
// in answer_checker, never this. No box is a trust label; we do not certify
// anything the model said.

// Display-side maths normalizer: converts residual LaTeX to readable plain
// text. Presentation only — the checker receives the RAW model text and does
// its own normalization server-side. Unknown commands pass through
// untouched (see the generic word-command fallback at the end).
const SUP_MAP={'0':'⁰','1':'¹','2':'²','3':'³','4':'⁴','5':'⁵','6':'⁶','7':'⁷','8':'⁸','9':'⁹','+':'⁺','-':'⁻'};
const SUB_MAP={'0':'₀','1':'₁','2':'₂','3':'₃','4':'₄','5':'₅','6':'₆','7':'₇','8':'₈','9':'₉','+':'₊','-':'₋'};
function toSup(s){return s.split('').map(c=>SUP_MAP[c]||c).join('');}
function toSub(s){return s.split('').map(c=>SUB_MAP[c]||c).join('');}
const MATHBB_MAP={R:'ℝ',N:'ℕ',Z:'ℤ',Q:'ℚ',C:'ℂ'};
// Known LaTeX word-commands only — anything not in this map is left as-is.
const SYM_MAP={theta:'θ',Theta:'Θ',alpha:'α',beta:'β',gamma:'γ',Gamma:'Γ',delta:'δ',Delta:'Δ',
  epsilon:'ε',varepsilon:'ε',pi:'π',Pi:'Π',mu:'μ',sigma:'σ',Sigma:'Σ',lambda:'λ',Lambda:'Λ',
  phi:'φ',Phi:'Φ',omega:'ω',Omega:'Ω',rho:'ρ',tau:'τ',nu:'ν',chi:'χ',psi:'ψ',Psi:'Ψ',
  eta:'η',zeta:'ζ',kappa:'κ',xi:'ξ',Xi:'Ξ',
  Rightarrow:'⇒',Leftarrow:'⇐',Leftrightarrow:'⇔',iff:'⇔',to:'→',
  leq:'≤',le:'≤',geq:'≥',ge:'≥',neq:'≠',ne:'≠',approx:'≈',sim:'∼',
  infty:'∞',in:'∈',notin:'∉',forall:'∀',exists:'∃',
  sum:'∑',prod:'∏',int:'∫',partial:'∂',nabla:'∇',
  emptyset:'∅',subset:'⊂',supset:'⊃',subseteq:'⊆',supseteq:'⊇',cup:'∪',cap:'∩',
  langle:'⟨',rangle:'⟩',circ:'∘',
  // named functions: LaTeX's \sin etc. only mean "set upright roman type,
  // don't italicize as three variables" — bare name is the correct reading.
  sin:'sin',cos:'cos',tan:'tan',cot:'cot',sec:'sec',csc:'csc',
  arcsin:'arcsin',arccos:'arccos',arctan:'arctan',
  sinh:'sinh',cosh:'cosh',tanh:'tanh',coth:'coth',
  log:'log',ln:'ln',exp:'exp',lim:'lim',
  max:'max',min:'min',sup:'sup',inf:'inf',
  gcd:'gcd',lcm:'lcm',det:'det',dim:'dim',ker:'ker',deg:'deg',mod:'mod'};
function deLatex(s){
  // inner, brace-free forms first, so \\frac's [^{}] match then succeeds on
  // nested content like \\frac{-7 \\pm \\sqrt{25}}{4}
  s=s.replace(/\\\\sqrt\\{([^{}]+)\\}/g,'√($1)')
     .replace(/\\\\text\\{([^{}]*)\\}/g,'$1')
     .replace(/\\\\mathrm\\{([^{}]*)\\}/g,'$1')
     .replace(/\\\\mathbb\\{([A-Za-z])\\}/g,(m,l)=>MATHBB_MAP[l]||l)
     .replace(/\\\\pmod\\{([^{}]+)\\}/g,'(mod $1)')
     .replace(/\\\\cdot/g,'·').replace(/\\\\times/g,'×').replace(/\\\\pm(?!od)/g,'±').replace(/\\\\mp/g,'∓')
     .replace(/\\\\(?:quad|qquad|,|;|!)/g,' ')
     .replace(/\\\\(?:left|right)/g,'');
  for(let i=0;i<3;i++) s=s.replace(/\\\\frac\\{([^{}]+)\\}\\{([^{}]+)\\}/g,'($1)/($2)');
  s=s.replace(/\\\\boxed\\{([^{}]+)\\}/g,'$1')
     .replace(/\\\\[\\[\\]()]/g,'')
     .replace(/\\$/g,'')
     .replace(/\\^\\{([-+0-9]+)\\}/g,(m,g)=>toSup(g))
     .replace(/\\^([-+]?[0-9])/g,(m,g)=>toSup(g))
     .replace(/_\\{([-+0-9]+)\\}/g,(m,g)=>toSub(g))
     .replace(/_([-+]?[0-9])/g,(m,g)=>toSub(g))
     .replace(/\\\\([A-Za-z]+)/g,(m,w)=>SYM_MAP[w]||m);
  return s;
}

// EulerMind decides the section names and order — the model only fills slots.
const TAG_LAYOUT=[['UNDERSTANDING','Understanding'],['METHOD','Method'],
                  ['CALCULATION','Calculation'],['MISTAKE','Common mistake'],
                  ['TAKEAWAY','Key takeaway']];
function parseTags(text){
  const grab=t=>{const m=text.match(new RegExp('<'+t+'>([\\\\s\\\\S]*?)(?:</'+t+'>|$)'));
                 return m?m[1].trim():null;};
  const secs=[];
  for(const [tag,title] of TAG_LAYOUT){
    const body=grab(tag);
    if(body) secs.push({title, body});
  }
  return {secs, answer: grab('ANSWER'), tagged: secs.length>0};
}
function segmentSections(text){
  const m=text.search(/FINAL ANSWER(?![a-z])/i);
  const working = m>=0 ? text.slice(0,m) : text;
  let answer  = m>=0 ? text.slice(m).replace(/FINAL ANSWER(?![a-z])\\s*:?\\s*/i,'').trim() : '';
  if(!answer){ // math models' native convention: last \\boxed{...} is the answer
    const boxed=[...text.matchAll(/\\\\boxed\\{([^{}]*)\\}/g)];
    if(boxed.length) answer=boxed[boxed.length-1][1].trim();
  }
  const secs=[]; let cur=null;
  for(const ln of working.split('\\n')){
    const hm=ln.match(/^\\s*#{1,3}\\s*(.+?)\\s*:?\\s*$/);
    if(hm){ cur={title:hm[1].trim(), body:''}; secs.push(cur); }
    else if(cur){ cur.body+=ln+'\\n'; }
    else if(ln.trim()){ cur={title:'', body:ln+'\\n'}; secs.push(cur); }
  }
  // Honest fallback: no headers emitted → generic Step N segmentation of the
  // same text. Structuring presentation, never inventing headers.
  if(!secs.some(s=>s.title)){
    let parts=working.split(/\\n(?=\\s*(?:step\\s*\\d+|[0-9]+\\s*[.)])\\b)/i);
    if(parts.length<2) parts=working.split(/\\n\\s*\\n/);
    parts=parts.map(s=>s.trim()).filter(Boolean);
    return {secs: parts.map((p,i)=>({title:'Step '+(i+1), body:p})), answer};
  }
  return {secs: secs.map(s=>({title:s.title, body:s.body.trim()}))
                    .filter(s=>s.title||s.body), answer};
}
function renderStream(el, text){
  // Prefer the tag contract; fail OPEN to the header/step segmenter on
  // untagged output (older models, contract misses). Never stall, never fake.
  let secs, answer;
  const tagged = parseTags(text);
  if(tagged.tagged){ secs=tagged.secs; answer=tagged.answer; }
  else { const f=segmentSections(text); secs=f.secs; answer=f.answer; }
  let h='<div class="modelzone"><div class="zonelabel">Model’s explanation</div>';
  secs.forEach(s=>{ h+='<div class="step"><span class="stepchip">'+esc(s.title||'Reasoning')
    +'</span><div class="stepbody">'+esc(deLatex(s.body))+'</div></div>'; });
  if(!secs.length) h+='<div class="step"><span class="stepchip">Thinking</span>'
    +'<div class="stepbody">'+esc(deLatex(text))+'</div></div>';
  h+='</div>';
  if(answer) h+='<div class="answerbox"><div class="zonelabel">Answer</div>'
    +'<div class="answerval">'+esc(deLatex(answer))+'</div></div>';
  el.innerHTML=h;
}
async function tutor(q, out, solved){
  out.innerHTML='<p class="meta">tutor lane · local model, streaming — fully offline</p>'
    +'<p class="legend">The sections below are the model\\'s explanation. '
    +'Only the final answer is machine-checked by EulerMind.</p>'
    +'<div id="steps"></div><div id="verdict"></div>';
  const stepsEl=document.getElementById('steps');
  const tGenStart=performance.now();
  const resp=await fetch('/tutor',{method:'POST',body:JSON.stringify({text:q})});
  if(resp.status===409){
    const e=await resp.json();
    stepsEl.innerHTML='<div class="checkzone"><div class="zonelabel">One question at a time</div>'
      +'<div class="checkline">'+esc(e.message)+'</div></div>';
    return;
  }
  if(resp.status===503){
    const e=await resp.json();
    stepsEl.innerHTML='<div class="checkzone"><div class="zonelabel">Tutor lane offline</div>'
      +'<div class="checkline fail">'+esc(e.error)+'</div>'
      +'<div class="why">The certified lane still works without it.</div></div>';
    return;
  }
  const reader=resp.body.getReader(); const dec=new TextDecoder(); let full='';
  const FIN=/\\n?⟪EULERMIND:FINISH=(\\w+)⟫/;
  while(true){ const {done,value}=await reader.read(); if(done)break;
    full+=dec.decode(value,{stream:true});
    renderStream(stepsEl, full.replace(FIN,'')); }
  const fm=full.match(FIN); const finish=fm?fm[1]:'stop';
  full=full.replace(FIN,'');
  renderStream(stepsEl, full);
  const tGenEnd=performance.now();
  const genMs=Math.round(tGenEnd-tGenStart);
  if(finish==='length'){
    // truncated generation: NEVER verify a clipped answer
    document.getElementById('verdict').innerHTML=
      '<div class="checkzone"><div class="zonelabel">EulerMind machine check</div>'
      +'<div class="checkline">Not checked — the generation stopped at the token limit.</div>'
      +'<div class="label Heuristic">Heuristic</div></div>'
      +'<div class="why"><b>The explanation ended before a complete answer was produced.</b> '
      +'Nothing was checked — ask the question again.</div>'
      +'<p class="meta">Generation '+genMs+' ms</p>';
    return;
  }
  document.getElementById('verdict').innerHTML='<p class="meta">EulerMind is running the deterministic machine check…</p>';
  // Adapter: if the tag contract produced an <ANSWER>, pass that exact string
  // (raw, un-normalized) to the checker via the marker it parses. Contents
  // are the model's verbatim answer — only the envelope changes.
  const tg=parseTags(full);
  const checkText = (tg.tagged && tg.answer) ? ('FINAL ANSWER: '+tg.answer) : full;
  const tCheckStart=performance.now();
  const c=await(await fetch('/check',{method:'POST',body:JSON.stringify({question:q,answer:checkText})})).json();
  const tCheckEnd=performance.now();
  const checkMs=Math.round(tCheckEnd-tCheckStart), totalMs=genMs+checkMs;
  const pass=c.checked&&c.passed, fail=c.checked&&c.passed===false;
  const unchecked_shape = !c.checked && c.note && c.note.indexOf('not in the checkable families')>=0;
  let v='<div class="checkzone"><div class="zonelabel">EulerMind machine check</div>';
  if(c.method) v+='<div class="checkline">Method: '+esc(c.method)+'</div>';
  v+='<div class="checkline '+(pass?'ok':(fail?'fail':''))+'">';
  if(pass) v+='Result: ✓ '+esc(c.note);
  else if(fail) v+='Result: ✗ verification FAILED — '+esc(c.note);
  else v+='Result: not verified — '+esc(c.note);
  v+='</div>';
  v+='<div class="label '+c.label+'">'+c.label+'</div>';
  v+='</div>';
  if(pass && c.rationale && c.rationale.length){
    v+='<div class="trusted"><div class="zonelabel">Why this answer is trusted</div>';
    c.rationale.forEach(b=>{ v+='<div class="tline">✓ '+esc(b)+'</div>'; });
    v+='</div>';
  } else if(fail){
    v+='<div class="why"><b>Do not trust this answer.</b> EulerMind checked it and it does not survive the check — the model\\'s working contains an error.</div>';
  } else if(unchecked_shape){
    v+='<div class="why"><b>AI explanation only.</b> This question is beyond what EulerMind can check by deterministic mathematics. The explanation above was generated by the AI model and has not been machine-checked — it may contain mistakes.'
      +(c.families&&c.families.length?'<br><br>EulerMind currently checks '+c.families.length
        +' question families: '+esc(c.families.join(', '))+'. This question matched none of them — '
        +'that is a routing fact, not a guess about the topic.':'')
      +'</div>';
  } else {
    v+='<div class="why"><b>Nothing was verified.</b> EulerMind found no machine-checkable final answer in the explanation.</div>';
  }
  v+='<p class="meta">Generation '+genMs+' ms · Verification '+checkMs+' ms · Total '+totalMs+' ms</p>';
  document.getElementById('verdict').innerHTML=v;
}
</script></body></html>"""


class Handler(BaseHTTPRequestHandler):
    def log_message(self, *a):
        pass

    def do_GET(self):
        page = PAGE.replace("__EXAMPLES__", json.dumps(_examples()))
        body = page.encode()
        self.send_response(200)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def _json(self, obj, status=200):
        body = json.dumps(obj).encode()
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def do_POST(self):
        n = int(self.headers.get("Content-Length", 0))
        try:
            payload = json.loads(self.rfile.read(n)) if n else {}
        except json.JSONDecodeError:
            self._json({"error": "bad request"}, 400)
            return
        text = payload.get("text", "")

        if self.path == "/solve":
            try:
                result = solve(text)
            except Exception as e:
                result = {"domain": None, "label": "Open", "stages": [],
                          "answer": f"Pipeline error (reported, not hidden): {e}",
                          "ms": 0}
            self._json(result)
            return

        if self.path == "/tutor":
            from .tutor import (MULTI_QUESTION_MESSAGE,
                                detect_multiple_questions, discover_server,
                                stream_tutor_answer)
            if detect_multiple_questions(text):
                # deterministic gate: no model call, no check, no guessing
                self._json({"multi_question": True,
                            "message": MULTI_QUESTION_MESSAGE}, 409)
                return
            server = discover_server()
            if server is None:
                self._json({"error": "no local model server. Start one with: "
                            "llama-server -m model/<model>.gguf --port 8080"}, 503)
                return
            base, model = server
            self.send_response(200)
            self.send_header("Content-Type", "text/plain; charset=utf-8")
            self.send_header("Cache-Control", "no-cache")
            self.end_headers()
            status: dict = {}
            try:
                for chunk in stream_tutor_answer(text, base, model, status):
                    self.wfile.write(chunk.encode("utf-8"))
                    self.wfile.flush()
                # end-of-stream sentinel: completion status for the client
                # (⟪⟫ delimiters cannot occur in model output)
                reason = status.get("finish_reason", "stop")
                self.wfile.write(f"\n⟪EULERMIND:FINISH={reason}⟫".encode("utf-8"))
                self.wfile.flush()
            except (BrokenPipeError, ConnectionError, OSError):
                pass
            return

        if self.path == "/check":
            from .answer_checker import _CHECKERS, check_answer, trust_rationale
            # Introspected from the real checker registry, never hand-copied,
            # so this list can't drift from what the checker actually covers.
            families = sorted(fn.__name__.replace("_check_", "").replace("_", " ")
                              for fn in _CHECKERS)
            try:
                result = check_answer(payload.get("question", ""),
                                      payload.get("answer", ""))
                result["rationale"] = trust_rationale(result)
            except Exception as e:
                result = {"label": "Heuristic", "checked": False,
                          "passed": None, "method": None, "rationale": [],
                          "note": f"checker error (reported, not hidden): {e}"}
            result["families"] = families
            self._json(result)
            return

        self.send_response(404)
        self.end_headers()


def main() -> None:
    print(f"EulerMind local demo → http://localhost:{PORT}  (Ctrl-C to stop)")
    HTTPServer(("127.0.0.1", PORT), Handler).serve_forever()


if __name__ == "__main__":
    main()
