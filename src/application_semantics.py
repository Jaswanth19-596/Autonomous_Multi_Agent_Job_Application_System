"""Semantic, verified browser programs for job application workflows.

The LLM deals in stable field labels and candidate-profile keys.  This module
keeps DOM discovery, control mechanics, validation, and verification inside a
small number of deterministic Playwright executions.
"""

from __future__ import annotations

import json
import os
import re
from pathlib import Path
from typing import Any
from src.workday_controls import CONTROL_ENGINE_JS


def _embed(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False).replace("</", "<\\/")


RADIO_GROUPS_CODE = r"""
async (page) => JSON.stringify(await page.evaluate(() => {
  const clean = v => String(v ?? '').trim().replace(/\s+/g, ' ');
  const isUsableControl = el => { const s=getComputedStyle(el),r=el.getBoundingClientRect(); return s.display!=='none'&&s.visibility!=='hidden'&&Number(s.opacity)!==0&&r.width>0&&r.height>0&&!el.disabled&&el.getAttribute('aria-disabled')!=='true'&&!el.closest('[aria-hidden="true"]')&&!el.closest('[data-simplify-extension], [data-simplify-overlay], [class*="simplify" i], [id*="simplify" i]'); };
  const labelled = el => clean((el.getAttribute('aria-labelledby') || '').split(/\s+/).map(id=>document.getElementById(id)?.innerText).filter(Boolean).join(' '));
  const optionLabel = el => clean(el.getAttribute('aria-label') || labelled(el) || (el.labels&&Array.from(el.labels).map(x=>x.innerText).join(' ')) || el.closest('label')?.innerText || el.value);
  const questionOf = el => {
    const fieldset=el.closest('fieldset'), group=el.closest('[role=radiogroup]');
    if (fieldset?.querySelector('legend')) return clean(fieldset.querySelector('legend').innerText);
    if (group) return clean(group.getAttribute('aria-label') || labelled(group) || group.querySelector('legend, h1, h2, h3, h4, [class*="question" i], [class*="label" i]')?.innerText);
    const box=el.closest('.field, .form-group, [class*="question" i], [class*="field" i]');
    return clean(box?.querySelector('legend, h1, h2, h3, h4, [class*="question" i], label')?.innerText || el.name || el.id);
  };
  const radios=Array.from(document.querySelectorAll('input[type=radio], [role=radio]')).filter(isUsableControl), groups=new Map();
  radios.forEach((el,i) => {
    const owner=el.closest('[role=radiogroup], fieldset');
    const raw=el.name || owner?.id || owner?.getAttribute('aria-label') || questionOf(el) || `radio_${el.id || i}`;
    const key=clean(raw);
    let group=groups.get(key);
    if (!group) { group={key, question:questionOf(el), required:Boolean(el.required||owner?.getAttribute('aria-required')==='true'), options:[]}; groups.set(key,group); }
    group.options.push({label:optionLabel(el), value:clean(el.value || optionLabel(el)), selected:el.matches(':checked') || el.getAttribute('aria-checked')==='true', disabled:Boolean(el.disabled||el.getAttribute('aria-disabled')==='true')});
  });
  return {radio_groups:Array.from(groups.values())};
}))
"""


DROPDOWNS_CODE = r"""
async (page) => {
  const clean = v => String(v ?? '').trim().replace(/\s+/g, ' ');
  const isUsableControl = async el => { try { return await el.isVisible() && await el.isEnabled() && !await el.evaluate(n=>Boolean(n.closest('[aria-hidden="true"], [data-simplify-extension], [data-simplify-overlay], [class*="simplify" i], [id*="simplify" i]'))); } catch { return false; } };
  const labelOf = async el => clean(await el.evaluate(node => node.getAttribute('aria-label') || (node.labels&&Array.from(node.labels).map(x=>x.innerText).join(' ')) || (node.getAttribute('aria-labelledby')||'').split(/\s+/).map(id=>document.getElementById(id)?.innerText).filter(Boolean).join(' ') || node.closest('fieldset')?.querySelector('legend')?.innerText || node.closest('.field,.form-group,[class*="field" i]')?.querySelector('label,[class*="label" i]')?.innerText || node.name || node.id));
  const controls=page.locator('select, [role=combobox]'), dropdowns=[];
  for (let i=0;i<await controls.count();i++) {
    const el=controls.nth(i); if (!await isUsableControl(el)) continue;
    const tag=await el.evaluate(n=>n.tagName.toLowerCase()), label=await labelOf(el);
    const key=clean((await el.getAttribute('name')) || (await el.getAttribute('id')) || label || `dropdown_${i}`);
    let options=[];
    if (tag==='select') options=await el.locator('option').evaluateAll(xs=>xs.map(o=>({label:(o.textContent||'').trim().replace(/\s+/g,' '),value:o.value,selected:o.selected,disabled:o.disabled})));
    else {
      await el.click().catch(()=>{}); await page.waitForTimeout(100);
      let list=page.locator('[role=option]:visible');
      const owns=(await el.getAttribute('aria-controls')) || (await el.getAttribute('aria-owns'));
      if (owns) list=page.locator(`[id=${JSON.stringify(owns)}] [role=option]:visible`);
      options=await list.evaluateAll(xs=>xs.map(o=>({label:(o.innerText||o.textContent||'').trim().replace(/\s+/g,' '),value:o.getAttribute('data-value')||o.getAttribute('value')||(o.innerText||o.textContent||'').trim(),selected:o.getAttribute('aria-selected')==='true',disabled:o.getAttribute('aria-disabled')==='true'})));
      await page.keyboard.press('Escape').catch(()=>{});
    }
    dropdowns.push({key,label,type:tag==='select'?'select':'combobox',required:Boolean(await el.getAttribute('required')!==null || await el.getAttribute('aria-required')==='true'),value:clean(await el.inputValue().catch(()=>'')),options});
  }
  return JSON.stringify({dropdowns});
}
"""


def build_fill_radio_groups_code(selections: list[dict[str, Any]]) -> str:
    return r"""
async (page) => {
  const requests=SELECTIONS, clean=v=>String(v??'').trim().replace(/\s+/g,' '), norm=v=>clean(v).toLowerCase(); const results=[];
  const labelOf=async el=>clean(await el.evaluate(n=>n.getAttribute('aria-label')||(n.labels&&Array.from(n.labels).map(x=>x.innerText).join(' '))||n.closest('label')?.innerText||n.value));
  for (const req of requests) {
    const wanted=req.option ?? req.value, key=req.key ?? req.question; let radios=page.locator('input[type=radio], [role=radio]'), candidates=[];
    for(let i=0;i<await radios.count();i++){const r=radios.nth(i),name=await r.getAttribute('name'),group=await r.evaluate(n=>n.closest('[role=radiogroup],fieldset')?.getAttribute('id')||n.closest('[role=radiogroup]')?.getAttribute('aria-label')||n.closest('fieldset')?.querySelector('legend')?.innerText||''); if(norm(name)===norm(key)||norm(group)===norm(key)) candidates.push(r);}
    let chosen=null; for(const r of candidates){if(norm(await labelOf(r))===norm(wanted)||norm(await r.getAttribute('value'))===norm(wanted)){chosen=r;break;}}
    if(!chosen){results.push({key,option:wanted,status:'unresolved',reason:'radio group or option not found'});continue;}
    try{if((await chosen.getAttribute('type'))==='radio') await chosen.check(); else await chosen.click(); const selected=(await chosen.getAttribute('type'))==='radio'?await chosen.isChecked():await chosen.getAttribute('aria-checked')==='true'; results.push({key,option:wanted,status:selected?'filled_and_verified':'unresolved',reason:selected?undefined:'radio state did not persist'});}catch(e){results.push({key,option:wanted,status:'unresolved',reason:String(e.message||e)});}
  } return JSON.stringify({results});
}
""".replace("SELECTIONS", _embed(selections))


def build_fill_dropdowns_code(selections: list[dict[str, Any]]) -> str:
    return r"""
async (page) => {
  const requests=SELECTIONS, clean=v=>String(v??'').trim().replace(/\s+/g,' '), norm=v=>clean(v).toLowerCase(); const results=[];
  for(const req of requests){const key=req.key??req.label,wanted=req.option??req.value; let controls=page.locator('select,[role=combobox]'),target=null;
    for(let i=0;i<await controls.count();i++){const e=controls.nth(i),id=await e.getAttribute('id'),name=await e.getAttribute('name'),label=await e.getAttribute('aria-label')||await e.evaluate(n=>(n.labels&&Array.from(n.labels).map(x=>x.innerText).join(' '))||''); if([id,name,label].some(x=>norm(x)===norm(key))){target=e;break;}}
    if(!target){results.push({key,option:wanted,status:'unresolved',reason:'dropdown not found'});continue;}
    try{const tag=await target.evaluate(n=>n.tagName.toLowerCase()); if(tag==='select'){let s=await target.selectOption({label:String(wanted)}).catch(()=>[]);if(!s.length)s=await target.selectOption({value:String(wanted)}).catch(()=>[]);if(!s.length)throw Error('option not found');const selected=await target.locator('option:checked').evaluate(o=>({label:(o.textContent||'').trim(),value:o.value}));if(norm(selected.label)!==norm(wanted)&&norm(selected.value)!==norm(wanted))throw Error('dropdown state did not persist');}
      else{await target.click();let option=page.getByRole('option',{name:String(wanted),exact:true}).first();if(!await option.count())option=page.getByRole('option',{name:String(wanted),exact:false}).first();if(!await option.count())throw Error('option not found');await option.click();await page.waitForTimeout(50);const state=clean(await target.inputValue().catch(async()=>await target.getAttribute('aria-valuetext')||await target.textContent()));if(!norm(state).includes(norm(wanted)))throw Error('dropdown state did not persist');}
      results.push({key,option:wanted,status:'filled_and_verified'});
    }catch(e){results.push({key,option:wanted,status:'unresolved',reason:String(e.message||e)});}
  } return JSON.stringify({results});
}
""".replace("SELECTIONS", _embed(selections))


PAGE_SCHEMA_CODE = r"""
async (page) => {
  return JSON.stringify(await page.evaluate(() => {
    const clean = v => String(v ?? '').trim().replace(/\s+/g, ' ');
    const isUsableControl = el => {
      const s = getComputedStyle(el), r = el.getBoundingClientRect();
      return s.display !== 'none' && s.visibility !== 'hidden' && Number(s.opacity) !== 0
        && r.width > 0 && r.height > 0 && !el.disabled && el.getAttribute('aria-disabled') !== 'true'
        && !el.closest('[aria-hidden="true"]')
        && !el.closest('[data-simplify-extension], [data-simplify-overlay], [class*="simplify" i], [id*="simplify" i]');
    };
    const label = el => clean(
      el.getAttribute('aria-label') ||
      (el.labels && Array.from(el.labels).map(x => x.innerText).join(' ')) ||
      (el.getAttribute('aria-labelledby') || '').split(/\s+/).map(id => document.getElementById(id)?.innerText).filter(Boolean).join(' ') ||
      el.closest('fieldset')?.querySelector('legend')?.innerText ||
      el.closest('.field, .form-group, [class*="field" i]')?.querySelector('label, [class*="label" i]')?.innerText ||
      el.placeholder || el.name || el.id
    );
    const controls = Array.from(document.querySelectorAll(
      'input:not([type=hidden]), textarea, select, [role=combobox]'
    )).filter(isUsableControl);
    const fields = controls.map((el, i) => {
      const tag = el.tagName.toLowerCase(), role = el.getAttribute('role') || '';
      const type = tag === 'select' ? 'select' : role === 'combobox' ? 'combobox' :
        tag === 'textarea' ? 'textarea' : (el.type || 'text');
      const isChoice = type === 'radio' || type === 'checkbox';
      const options = tag === 'select'
        ? Array.from(el.options).map(o => ({label: clean(o.textContent), value: o.value, selected: o.selected}))
        : type === 'radio'
          ? (() => {
              const owner = el.closest('fieldset, [role="radiogroup"]');
              const radios = el.name
                ? document.querySelectorAll(`input[type=radio][name="${CSS.escape(el.name)}"]`)
                : owner ? owner.querySelectorAll('input[type=radio], [role=radio]') : [el];
              return Array.from(radios).filter(isUsableControl)
                .map(o => ({label: label(o), value: o.value, selected: o.checked || o.getAttribute('aria-checked') === 'true'}));
            })()
          : [];
      const error = clean(el.getAttribute('aria-errormessage') && document.getElementById(el.getAttribute('aria-errormessage'))?.innerText)
        || clean(el.closest('.field, .form-group, [class*="field" i]')?.querySelector('[role=alert], .error, [class*="error" i]')?.innerText);
      return {
        id: clean(el.id || el.name || `control_${i}`), label: label(el), type,
        required: Boolean(el.required || el.getAttribute('aria-required') === 'true'),
        disabled: Boolean(el.disabled || el.getAttribute('aria-disabled') === 'true'),
        value: isChoice ? Boolean(el.checked || el.getAttribute('aria-checked') === 'true') : clean(el.value || el.innerText),
        options, error: error || null
      };
    });
    const host = location.hostname.toLowerCase();
    const ats = host.includes('myworkdayjobs') ? 'workday' : host.includes('greenhouse') ? 'greenhouse' :
      host.includes('lever.co') ? 'lever' : host.includes('clearcompany') ? 'clearcompany' :
      host.includes('icims') ? 'icims' : host.includes('jobvite') ? 'jobvite' : 'unknown';
    const progress = clean(document.body.innerText.match(/(?:page|step)\s+\d+\s+(?:of|\/)\s+\d+/i)?.[0]);
    const nums = progress.match(/\d+/g) || [];
    const buttons = Array.from(document.querySelectorAll('button, input[type=submit], [role=button]'))
      .filter(isUsableControl).map(el => clean(el.innerText || el.value || el.getAttribute('aria-label'))).filter(Boolean);
    return {
      url: location.href, ats, page: nums[0] ? Number(nums[0]) : null,
      total_pages: nums[1] ? Number(nums[1]) : null, fields, buttons,
      validation_errors: fields.filter(f => f.error).map(f => ({field: f.label, error: f.error})),
      upload_fields: fields.filter(f => f.type === 'file').map(f => f.label),
      captcha_present: Boolean(document.querySelector('iframe[src*="captcha" i], .g-recaptcha, [data-sitekey]'))
    };
  }));
}
"""


def build_fill_page_code(answers: dict[str, Any]) -> str:
    return r"""
async (page) => {
  const answers = ANSWERS;
  const clean = v => String(v ?? '').trim().replace(/\s+/g, ' ');
  const norm = v => clean(v).toLowerCase().replace(/[^a-z0-9]+/g, ' ').trim();
  const results = [];
  const controls = page.locator('input:not([type=hidden]), textarea, select, [role=combobox]');
  const labelOf = async el => el.evaluate(node => {
    const clean = v => String(v ?? '').trim().replace(/\s+/g, ' ');
    return clean(node.getAttribute('aria-label') || (node.labels && Array.from(node.labels).map(x => x.innerText).join(' ')) ||
      node.closest('fieldset')?.querySelector('legend')?.innerText || node.placeholder || node.name || node.id);
  });
  for (const [requested, value] of Object.entries(answers)) {
    let match = null, matchedLabel = '', best = -1;
    for (let i = 0; i < await controls.count(); i++) {
      const el = controls.nth(i), label = await labelOf(el);
      const identity = clean([label, await el.getAttribute('name'), await el.getAttribute('id')].filter(Boolean).join(' '));
      const a = norm(requested), b = norm(identity);
      const score = a === b ? 100 : b.includes(a) || a.includes(b) ? 80 : a.split(' ').filter(x => b.includes(x)).length;
      if (score > best) { best = score; match = el; matchedLabel = label; }
    }
    if (!match || best < 1) { results.push({field: requested, status: 'unresolved', reason: 'no semantic match'}); continue; }
    try {
      const tag = await match.evaluate(el => el.tagName.toLowerCase());
      const type = (await match.getAttribute('type') || await match.getAttribute('role') || '').toLowerCase();
      if (type === 'radio') {
        const group = await match.getAttribute('name');
        const radios = page.locator(`input[type=radio][name=${JSON.stringify(group)}]`);
        let chosen = null;
        for (let i = 0; i < await radios.count(); i++) {
          const radio = radios.nth(i), radioLabel = await labelOf(radio);
          if (norm(radioLabel) === norm(value) || norm(await radio.getAttribute('value')) === norm(value)) { chosen = radio; break; }
        }
        if (!chosen) throw new Error('radio option not found');
        await chosen.check();
        if (!await chosen.isChecked()) throw new Error('radio state did not persist');
      } else if (type === 'checkbox') {
        const desired = value === true || /^(yes|true|checked)$/i.test(String(value));
        await match.setChecked(desired);
        if (await match.isChecked() !== desired) throw new Error('checkbox state did not persist');
      } else if (tag === 'select') {
        let selected = await match.selectOption({label: String(value)}).catch(() => []);
        if (!selected.length) selected = await match.selectOption({value: String(value)}).catch(() => []);
        if (!selected.length) throw new Error('select option not found');
      } else if (type === 'combobox') {
        await match.click();
        let option = page.getByRole('option', {name: String(value), exact: true}).first();
        if (!await option.count()) option = page.getByRole('option', {name: String(value), exact: false}).first();
        if (!await option.count()) throw new Error('combobox option not found');
        await option.click();
      } else {
        await match.fill(String(value)); await match.blur();
        if (clean(await match.inputValue()) !== clean(value)) throw new Error('value did not persist');
      }
      results.push({field: requested, matched_label: matchedLabel, status: 'filled_and_verified'});
    } catch (error) { results.push({field: requested, matched_label: matchedLabel, status: 'unresolved', reason: String(error.message || error)}); }
  }
  return JSON.stringify({results});
}
""".replace("ANSWERS", _embed(answers))


AUDIT_PAGE_CODE = r"""
async (page) => JSON.stringify(await page.evaluate(() => {
  const clean = v => String(v ?? '').trim().replace(/\s+/g, ' ');
  const isUsableControl = el => { const s=getComputedStyle(el),r=el.getBoundingClientRect(); return s.display!=='none'&&s.visibility!=='hidden'&&Number(s.opacity)!==0&&r.width>0&&r.height>0&&!el.disabled&&el.getAttribute('aria-disabled')!=='true'&&!el.closest('[aria-hidden="true"]')&&!el.closest('[data-simplify-extension], [data-simplify-overlay], [class*="simplify" i], [id*="simplify" i]'); };
  const label = el => clean(el.getAttribute('aria-label') || (el.labels && Array.from(el.labels).map(x=>x.innerText).join(' ')) || el.name || el.id);
  const controls = Array.from(document.querySelectorAll('input:not([type=hidden]), textarea, select, [role=combobox]')).filter(isUsableControl);
  const missing_required = [], invalid = [];
  for (const el of controls) {
    const required = el.required || el.getAttribute('aria-required') === 'true';
    const type = el.type || '';
    const radioOwner = type === 'radio' ? el.closest('fieldset, [role="radiogroup"]') : null;
    const radioMembers = type !== 'radio' ? [] : el.name
      ? Array.from(document.querySelectorAll(`input[type=radio][name="${CSS.escape(el.name)}"]`))
      : radioOwner ? Array.from(radioOwner.querySelectorAll('input[type=radio], [role=radio]')) : [el];
    const empty = type === 'radio' ? !radioMembers.some(r => r.checked || r.getAttribute('aria-checked') === 'true')
      : type === 'checkbox' ? !el.checked : !clean(el.value || el.innerText);
    if (required && empty && !missing_required.includes(label(el))) missing_required.push(label(el));
    if (el.validity && !el.validity.valid) invalid.push({field: label(el), reason: el.validationMessage || 'invalid value'});
  }
  const alerts = Array.from(document.querySelectorAll('[role=alert], .error, [class*="error" i]')).filter(el=>{const s=getComputedStyle(el),r=el.getBoundingClientRect();return s.display!=='none'&&s.visibility!=='hidden'&&r.width>0&&r.height>0&&!el.closest('[aria-hidden="true"]');}).map(x=>clean(x.innerText)).filter(Boolean);
  return {ready_to_continue: !missing_required.length && !invalid.length && !alerts.length,
    missing_required, invalid, page_errors: [...new Set(alerts)], filled_count: controls.length - missing_required.length};
}))
"""


def build_upload_code(path: str, document_type: str) -> str:
    return r"""
async (page) => {
  const filePath = FILE_PATH, kind = DOC_TYPE.toLowerCase();
  const fileName = filePath.split(/[\\/]/).pop();

  // LinkedIn and several ATSs retain uploaded documents as selectable cards
  // and do not render a file input until the user asks to add another file.
  // Reuse the exact requested filename instead of opening the upload flow.
  const existing = page.getByText(fileName, {exact: true});
  for (let i=0; i<await existing.count(); i++) {
    const text = existing.nth(i);
    let container = text.locator('xpath=ancestor::*[.//input[@type="radio"] or @role="radio"][1]');
    let radio = container.locator('input[type=radio], [role=radio]').first();
    if (!await radio.count()) {
      container = text.locator('xpath=ancestor::*[self::label or self::button or @role="button"][1]');
      radio = container.locator('input[type=radio], [role=radio]').first();
    }
    if (await radio.count()) {
      const native = await radio.getAttribute('type') === 'radio';
      const selected = native ? await radio.isChecked() : await radio.getAttribute('aria-checked') === 'true';
      if (!selected) {
        if (native) await radio.check(); else await container.click();
      }
      const verified = native ? await radio.isChecked() : await radio.getAttribute('aria-checked') === 'true';
      if (verified) return JSON.stringify({uploaded:true, already_present:true, selected:true, document_type:kind, files:[fileName]});
    }
  }

  const inputs = page.locator('input[type=file]');
  let target = null;
  for (let i=0; i<await inputs.count(); i++) {
    const el=inputs.nth(i);
    const identity=((await el.getAttribute('name')) || '')+' '+((await el.getAttribute('id')) || '')+' '+((await el.getAttribute('aria-label')) || '');
    if (identity.toLowerCase().includes(kind)) { target=el; break; }
  }
  if (!target && await inputs.count() === 1) target=inputs.first();
  if (!target) return JSON.stringify({uploaded:false, already_present:false, reason:'matching file input not found'});
  await target.setInputFiles(filePath);
  await page.waitForTimeout(500);
  const files = await target.evaluate(el => Array.from(el.files || []).map(f => f.name));
  return JSON.stringify({uploaded:files.length>0, document_type:kind, files});
}
""".replace("FILE_PATH", _embed(path)).replace("DOC_TYPE", _embed(document_type))


def build_advance_code(action: str) -> str:
    return r"""
async (page) => {
  const wanted = ACTION;
  const before = page.url();
  const names = wanted === 'submit' ? /^(submit|apply|finish)$/i : /^(next|continue|save and continue|proceed)$/i;
  let button = page.getByRole('button', {name:names}).first();
  if (!await button.count()) button = page.locator('input[type=submit]').first();
  if (!await button.count()) return JSON.stringify({advanced:false, reason:'action control not found', before_url:before});
  await button.click();
  await page.waitForTimeout(900);
  const errors = await page.locator('[role=alert], .error, [class*="error" i]').allTextContents();
  return JSON.stringify({advanced:page.url()!==before || errors.length===0, action:wanted, before_url:before, after_url:page.url(), validation_errors:errors.map(x=>x.trim()).filter(Boolean)});
}
""".replace("ACTION", _embed(action))


SENSITIVE_PROFILE_KEYS = {"date_of_birth", "ssn", "disability", "race", "gender", "veteran_status"}


def resolve_answers(fields: list[dict[str, Any]], profile: dict[str, Any]) -> dict[str, Any]:
    """Resolve normalized fields from a profile without guessing."""
    resolved, needs_user, policy_blocked = {}, [], []
    flattened = {re.sub(r"[^a-z0-9]+", "_", str(k).lower()).strip("_"): v for k, v in profile.items()}
    aliases = {"first_name": ("first_name",), "last_name": ("last_name",), "email": ("email",),
               "phone": ("phone", "mobile_phone"), "city": ("city",), "state": ("state",),
               "street_address": ("street_address", "address"), "linkedin": ("linkedin", "linkedin_profile")}
    field_aliases = {
        "email_address": "email", "mobile_phone": "phone", "phone_number": "phone",
        "address": "street_address", "linkedin_profile": "linkedin",
    }
    for field in fields:
        label = str(field.get("label") or field.get("id") or "")
        key = re.sub(r"[^a-z0-9]+", "_", label.lower()).strip("_")
        # Exact aliases are intentional: substring matching would incorrectly
        # answer "professional reference email" with the candidate's email.
        semantic = field_aliases.get(key, key if key in aliases else key)
        if semantic in SENSITIVE_PROFILE_KEYS:
            policy_blocked.append({"field": label, "reason": "candidate must explicitly authorize this sensitive answer"})
            continue
        candidates = aliases.get(semantic, (semantic,))
        value = next((flattened[c] for c in candidates if c in flattened and flattened[c] not in (None, "")), None)
        if value is not None:
            resolved[label] = {"value": value, "source": f"candidate_profile.{next(c for c in candidates if c in flattened)}", "confidence": 1.0}
        elif field.get("required"):
            needs_user.append({"field": label, "reason": "required value is absent from candidate profile"})
    return {"resolved": resolved, "needs_user": needs_user, "policy_blocked": policy_blocked}


class CandidateProfileStore:
    def __init__(self, path: Path): self.path = path
    def load(self) -> dict[str, Any]:
        if not self.path.exists(): return {"version": 1, "values": {}}
        return json.loads(self.path.read_text(encoding="utf-8"))
    def update(self, values: dict[str, Any], source: str = "user", reusable: bool = True) -> dict[str, Any]:
        data = self.load(); bucket = data.setdefault("values", {})
        for key, value in values.items():
            bucket[key] = {"value": value, "source": source, "reusable": reusable}
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.path.write_text(json.dumps(data, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
        return data
    def plain_values(self) -> dict[str, Any]:
        return {key: item.get("value") for key, item in self.load().get("values", {}).items() if item.get("reusable", True)}


# These final definitions intentionally supersede the original implementations;
# both semantic and batch filling now share the same eligibility and ranking rules.
def build_fill_dropdowns_code(selections: list[dict[str, Any]]) -> str:
    return (r"""
async (page) => {
  const requests=SELECTIONS, results=[];
""" + CONTROL_ENGINE_JS + r"""
  for(const req of requests) {
    const key=req.key??req.label, wanted=req.option??req.value, found=await locateControl(req);
    if(found.error){results.push({key,option:wanted,status:'unresolved',failure_code:found.error,...found});continue;}
    const target=found.control, tag=await target.evaluate(el=>el.tagName.toLowerCase());
    try {
      if(tag==='select') {
        let selected=await target.selectOption({label:String(wanted)},{timeout:4000}).catch(()=>[]);
        if(!selected.length) selected=await target.selectOption({value:String(wanted)},{timeout:4000}).catch(()=>[]);
        if(!selected.length) throw Object.assign(new Error('option_not_found'),{code:'option_not_found'});
        if(norm(await selectedText(target))!==norm(wanted)) throw Object.assign(new Error('state_not_persisted'),{code:'state_not_persisted'});
      } else { const chosen=await chooseCustomOption(target,wanted); if(chosen.error) throw Object.assign(new Error(chosen.error),{code:chosen.error}); }
      results.push({key,option:wanted,status:'filled_and_verified',strategies_attempted:tag==='select'?1:2});
    } catch(error) { results.push({key,option:wanted,status:'unresolved',failure_code:error.code||(/Timeout/.test(String(error))?'interaction_timeout':'state_not_persisted')}); }
  }
  return JSON.stringify({results});
}
""").replace("SELECTIONS", _embed(selections))


def build_fill_page_code(answers: dict[str, Any]) -> str:
    return (r"""
async (page) => {
  const answers=ANSWERS, results=[];
""" + CONTROL_ENGINE_JS + r"""
  for(const [requested,value] of Object.entries(answers)) {
    const found=await locateControl({key:requested});
    if(found.error){results.push({field:requested,status:'unresolved',failure_code:found.error,...found});continue;}
    const control=found.control, tag=await control.evaluate(el=>el.tagName.toLowerCase());
    const type=((await control.getAttribute('type'))||(await control.getAttribute('role'))||'').toLowerCase();
    try {
      if(type==='checkbox') { const desired=value===true||/^(yes|true|checked)$/i.test(String(value)); await control.setChecked(desired,{timeout:4000}); if(await control.isChecked()!==desired) throw Object.assign(new Error(),{code:'state_not_persisted'}); }
      else if(type==='radio') { await control.check({timeout:4000}); if(!await control.isChecked()) throw Object.assign(new Error(),{code:'state_not_persisted'}); }
      else if(tag==='select') { const selected=await control.selectOption({label:String(value)},{timeout:4000}).catch(()=>[]); if(!selected.length) throw Object.assign(new Error(),{code:'option_not_found'}); }
      else if(type==='combobox'||await control.getAttribute('aria-haspopup')==='listbox') { const chosen=await chooseCustomOption(control,value); if(chosen.error) throw Object.assign(new Error(),{code:chosen.error}); }
      else { await control.fill(String(value),{timeout:4000}); await control.blur(); if(clean(await control.inputValue())!==clean(value)) throw Object.assign(new Error(),{code:'state_not_persisted'}); }
      results.push({field:requested,matched_label:found.label,status:'filled_and_verified'});
    } catch(error) { results.push({field:requested,matched_label:found.label,status:'unresolved',failure_code:error.code||(/Timeout/.test(String(error))?'interaction_timeout':'state_not_persisted')}); }
  }
  return JSON.stringify({results});
}
""").replace("ANSWERS", _embed(answers))


def build_upload_code(path: str, document_type: str) -> str:
    return r"""
async (page) => {
  const filePath=FILE_PATH, kind=DOC_TYPE.toLowerCase(), fileName=filePath.split(/[\\/]/).pop();
  const clean=v=>String(v??'').trim().replace(/\s+/g,' '), norm=v=>clean(v).toLowerCase();
  const visible=locator=>locator.isVisible().catch(()=>false);
  const inspectUploaded=async()=>{
    const filename=page.getByText(fileName, {exact: true});
    for(let i=0;i<await filename.count();i++) if(await visible(filename.nth(i))) {
      const box=filename.nth(i).locator('xpath=ancestor::*[self::li or self::div or self::section][1]');
      const status=clean(await box.textContent().catch(()=>''));
      const radio=box.locator('input[type=radio]').first();
      if(await radio.count() && !await radio.isChecked()) await radio.check();
      if(norm(status).includes(norm(fileName)) && (/successfully uploaded|uploaded|complete/i.test(status)||await filename.nth(i).isVisible()))
        return {uploaded:true,already_present:true,status:'Successfully Uploaded',files:[fileName]};
    }
    return null;
  };
  const present=await inspectUploaded(); if(present)return JSON.stringify(present);
  const inputs=page.locator('input[type=file]'); let target=null;
  for(let i=0;i<await inputs.count();i++) { const el=inputs.nth(i), identity=clean(`${await el.getAttribute('name')||''} ${await el.getAttribute('id')||''} ${await el.getAttribute('aria-label')||''}`); if(norm(identity).includes(norm(kind))){target=el;break;} }
  if(!target&&await inputs.count()===1)target=inputs.first();
  if(!target)return JSON.stringify({uploaded:false,already_present:false,failure_code:'control_not_found'});
  try { await target.setInputFiles(filePath,{timeout:5000}); }
  catch(error) { const afterTimeout=await inspectUploaded(); if(afterTimeout)return JSON.stringify(afterTimeout); return JSON.stringify({uploaded:false,already_present:false,failure_code:/Timeout/.test(String(error))?'interaction_timeout':'click_obstructed'}); }
  await page.waitForTimeout(250);
  const files=await target.evaluate(el=>Array.from(el.files||[]).map(f=>f.name));
  const visibleState=await inspectUploaded();
  const verified=files.includes(fileName)&&Boolean(visibleState);
  return JSON.stringify({uploaded:verified,already_present:false,files,visible_status:Boolean(visibleState),failure_code:verified?null:'state_not_persisted'});
}
""".replace("FILE_PATH", _embed(path)).replace("DOC_TYPE", _embed(document_type))
