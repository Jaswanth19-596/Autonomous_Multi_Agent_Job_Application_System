"""Structured one-scan / one-repair browser programs for application forms."""

import os

from src.application.workday_controls import CONTROL_ENGINE_JS

FORM_INSPECTION_CODE = r"""
async (page) => {
  const result = await page.evaluate(async () => {
    const isUsableControl = el => {
      const style = getComputedStyle(el);
      const rect = el.getBoundingClientRect();
      return style.visibility !== 'hidden' && style.display !== 'none' && Number(style.opacity) !== 0
        && rect.width > 0 && rect.height > 0 && !el.disabled && el.getAttribute('aria-disabled') !== 'true'
        && !el.closest('[aria-hidden="true"]')
        && !el.closest('[data-simplify-extension], [data-simplify-overlay], [class*="simplify" i], [id*="simplify" i]');
    };
    const clean = value => String(value || '').trim().replace(/\s+/g, ' ');
    const labelFor = el => {
      const aria = el.getAttribute('aria-label');
      if (aria) return clean(aria);
      if (el.labels?.length) return clean(Array.from(el.labels).map(x => x.innerText).join(' '));
      const labelledBy = el.getAttribute('aria-labelledby');
      if (labelledBy) {
        const text = labelledBy.split(/\s+/).map(id => document.getElementById(id)?.innerText).filter(Boolean).join(' ');
        if (text) return clean(text);
      }
      const container = el.closest('[role="group"], .field, .form-group, [class*="field" i]');
      return clean(container?.querySelector('label, legend, [class*="label" i]')?.innerText
        || el.getAttribute('placeholder') || el.name || el.id);
    };
    const keyFor = (el, index) => clean(el.id || el.name || el.getAttribute('aria-label')
      || `${el.tagName.toLowerCase()}-${index}`);
    const controls = Array.from(document.querySelectorAll(
      'input:not([type="hidden"]), textarea, select, [role="combobox"]'
    )).filter(isUsableControl);
    const seen = new Set();
    const output = [];

    for (let index = 0; index < controls.length; index++) {
      const el = controls[index];
      if (seen.has(el)) continue;
      seen.add(el);
      const tag = el.tagName.toLowerCase();
      const role = el.getAttribute('role') || '';
      const type = tag === 'select' ? 'select'
        : role === 'combobox' ? 'combobox'
        : tag === 'textarea' ? 'textarea'
        : (el.type || 'text');
      const item = {
        key: keyFor(el, index),
        label: labelFor(el),
        type,
        required: el.required || el.getAttribute('aria-required') === 'true',
        disabled: el.disabled || el.getAttribute('aria-disabled') === 'true',
        value: type === 'checkbox' || type === 'radio'
          ? Boolean(el.checked || el.getAttribute('aria-checked') === 'true')
          : clean(el.value || el.getAttribute('aria-valuetext') || el.innerText),
        options: []
      };

      if (tag === 'select') {
        item.options = Array.from(el.options).map(option => clean(option.textContent)).filter(Boolean);
      } else if (role === 'combobox' || el.getAttribute('aria-haspopup') === 'listbox') {
        try {
          el.click();
          await new Promise(resolve => setTimeout(resolve, 250));
          item.options = Array.from(document.querySelectorAll('[role="option"]'))
            .filter(isUsableControl).map(option => clean(option.innerText || option.textContent)).filter(Boolean);
          document.dispatchEvent(new KeyboardEvent('keydown', { key: 'Escape', bubbles: true }));
          el.dispatchEvent(new KeyboardEvent('keydown', { key: 'Escape', bubbles: true }));
          await new Promise(resolve => setTimeout(resolve, 75));
        } catch (_) {}
      }
      output.push(item);
    }
    return output;
  });
  return JSON.stringify({ fingerprint: await page.evaluate(() => location.href), controls: result });
}
"""


CLICK_NEXT_CONTROL_CODE = r"""
async (page) => {
  const result = await page.evaluate(() => {
    const visible = el => {
      const style = getComputedStyle(el);
      const rect = el.getBoundingClientRect();
      return style.visibility !== 'hidden' && style.display !== 'none'
        && rect.width > 0 && rect.height > 0;
    };
    const clean = value => String(value || '').trim().replace(/\s+/g, ' ');
    const clickableAncestor = el => el?.closest(
      'button, [role="button"], a, input[type="submit"], input[type="button"], .dijitButton, [widgetid]'
    );
    const candidates = new Set(Array.from(document.querySelectorAll(
      'button, [role="button"], a, input[type="submit"], input[type="button"], .dijitButton, [widgetid]'
    )));
    for (const icon of document.querySelectorAll(
      'svg, path, i, [class*="arrow" i], [class*="chevron" i], [class*="next" i], [class*="forward" i]'
    )) {
      const clickable = clickableAncestor(icon);
      if (clickable) candidates.add(clickable);
    }

    const scored = Array.from(candidates).filter(visible).map(el => {
      const rect = el.getBoundingClientRect();
      const identity = clean([
        el.innerText, el.value, el.getAttribute('aria-label'), el.getAttribute('title'),
        el.id, el.getAttribute('widgetid'), el.className,
        el.querySelector('[class*="arrow" i], [class*="chevron" i], [class*="next" i], [class*="forward" i]')?.className
      ].filter(Boolean).join(' '));
      let score = 0;
      if (/\b(next|continue|forward|proceed)\b|appgo/i.test(identity)) score += 100;
      if (/arrow[^ ]*right|chevron[^ ]*right|right[^ ]*(arrow|chevron)/i.test(identity)) score += 80;
      if (/\b(back|previous|prev)\b|arrow[^ ]*left|chevron[^ ]*left/i.test(identity)) score -= 200;
      if (rect.top > innerHeight * 0.55) score += 15;
      if (rect.width >= 35 && rect.height >= 35) score += 5;
      if (getComputedStyle(el).cursor === 'pointer') score += 5;
      return { el, score, identity: identity.slice(0, 180), rect };
    }).filter(item => item.score > 0).sort((a, b) =>
      b.score - a.score || b.rect.left - a.rect.left || b.rect.top - a.rect.top
    );

    if (!scored.length) {
      return { clicked: false, reason: 'No visible Next/Continue/right-arrow control found' };
    }
    const selected = scored[0];
    selected.el.scrollIntoView({ block: 'center', inline: 'center' });
    selected.el.click();
    return {
      clicked: true,
      identity: selected.identity,
      score: selected.score,
      candidates: scored.slice(0, 5).map(x => ({ identity: x.identity, score: x.score }))
    };
  });
  await page.waitForTimeout(750);
  return JSON.stringify({ fingerprint: await page.evaluate(() => location.href), ...result });
}
"""


def _legacy_build_batch_repair_code(repairs_json: str) -> str:
    """Build a Playwright-native, verified repair program."""
    return r"""
async (page) => {
  const repairs = REPAIRS_JSON;
  const results = [];
  const clean = value => String(value || '').trim().replace(/\s+/g, ' ');
  const norm = value => clean(value).toLowerCase();
  const byKey = key => page.locator(`[id=${JSON.stringify(String(key))}], [name=${JSON.stringify(String(key))}]`).first();
  const findControl = async repair => {
    if (repair.key) {
      const keyed = byKey(repair.key);
      if (await keyed.count()) return keyed;
    }
    if (repair.label) {
      const exact = page.getByLabel(repair.label, { exact: true }).first();
      if (await exact.count()) return exact;
      const aria = page.locator(`[aria-label=${JSON.stringify(String(repair.label))}]`).first();
      if (await aria.count()) return aria;
      const fuzzy = page.getByLabel(repair.label, { exact: false }).first();
      if (await fuzzy.count()) return fuzzy;
    }
    return null;
  };

  for (const repair of repairs) {
    const control = await findControl(repair);
    if (!control) {
      results.push({ key: repair.key || repair.label, status: 'unresolved', reason: 'control not found' });
      continue;
    }
    try {
      const tag = await control.evaluate(el => el.tagName.toLowerCase());
      const actualType = await control.getAttribute('type') || await control.getAttribute('role') || '';
      const kind = repair.type || (tag === 'select' ? 'select' : actualType || (tag === 'textarea' ? 'textarea' : 'text'));
      if (kind === 'checkbox' || kind === 'radio') {
        const desired = repair.value === true || /^(true|yes|checked)$/i.test(String(repair.value));
        if (desired) await control.check(); else await control.uncheck();
        if ((await control.isChecked()) !== desired) throw new Error('checked state was not accepted');
      } else if (tag === 'select' || kind === 'select') {
        let selected;
        try {
          selected = await control.selectOption({ label: String(repair.value) });
        } catch (_) {
          selected = await control.selectOption({ value: String(repair.value) });
        }
        if (!selected.length) throw new Error('matching native option not found');
        const selectedText = await control.locator('option:checked').textContent();
        if (norm(selectedText) !== norm(repair.value) && !norm(selectedText).includes(norm(repair.value))) {
          throw new Error(`selected option did not persist: ${clean(selectedText)}`);
        }
      } else if (actualType === 'combobox' || kind === 'combobox') {
        await control.click();
        let option = page.getByRole('option', { name: String(repair.value), exact: true }).first();
        if (!await option.count()) {
          await control.fill(String(repair.value));
          option = page.getByRole('option', { name: String(repair.value), exact: false }).first();
        }
        if (!await option.count()) throw new Error('matching custom option not found');
        await option.click();
        const accepted = clean(await control.inputValue().catch(async () => await control.textContent()));
        if (norm(accepted) !== norm(repair.value) && !norm(accepted).includes(norm(repair.value))) {
          throw new Error(`custom option did not persist: ${accepted}`);
        }
      } else {
        await control.fill(String(repair.value));
        await control.blur();
        const accepted = await control.inputValue();
        if (String(accepted) !== String(repair.value)) {
          throw new Error(`value was not accepted: ${accepted}`);
        }
      }
      results.push({ key: repair.key || repair.label, status: 'filled_and_verified' });
    } catch (error) {
      results.push({ key: repair.key || repair.label, status: 'unresolved', reason: String(error.message || error) });
    }
  }
  return JSON.stringify({ fingerprint: await page.evaluate(() => location.href), results });
}
""".replace("REPAIRS_JSON", repairs_json)


def build_batch_repair_code(repairs_json: str) -> str:
    """Build a shared-locator repair program with bounded, structured failures."""
    return (r"""
async (page) => {
  const repairs=REPAIRS_JSON, results=[]; let browserActions=0;
""" + CONTROL_ENGINE_JS + r"""
  for (const repair of repairs) {
    const key=repair.key||repair.label;
    if(browserActions>=12){results.push({key, status: 'unresolved',failure_code:'action_budget_exhausted',field:repair.label||key,attempts:0,retryable:true});continue;}
    const found=await locateControl(repair);
    if(found.error){results.push({key,status:'unresolved',failure_code:found.error,field:repair.label||key,attempts:0,retryable:true,...found});continue;}
    const control=found.control, tag=await control.evaluate(el=>el.tagName.toLowerCase());
    const actualType=((await control.getAttribute('type'))||(await control.getAttribute('role'))||'').toLowerCase();
    const type=(repair.type||actualType||(tag==='textarea'?'textarea':'text')).toLowerCase(), kind=type;
    try {
      browserActions++;
      if(kind === 'checkbox' || kind === 'radio') { const desired=repair.value===true||/^(true|yes|checked)$/i.test(String(repair.value)); if(desired) await control.check({timeout:5000}); else await control.uncheck({timeout:5000}); if(await control.isChecked()!==desired) throw Object.assign(new Error(),{code:'state_not_persisted'}); }
      else if(tag === 'select'||type==='select') { let selected=await control.selectOption({label:String(repair.value)},{timeout:4000}).catch(()=>[]); if(!selected.length)selected=await control.selectOption({value:String(repair.value)},{timeout:4000}).catch(()=>[]);if(!selected.length)throw Object.assign(new Error(),{code:'option_not_found'}); }
      else if(actualType === 'combobox'||type === 'combobox'||await control.getAttribute('aria-haspopup')==='listbox') { const chosen=await chooseCustomOption(control,repair.value); if(chosen.error)throw Object.assign(new Error(),{code:chosen.error}); }
      else { await control.fill(String(repair.value),{timeout:4000});await control.blur();if(String(await control.inputValue())!==String(repair.value))throw Object.assign(new Error('value was not accepted'),{code:'state_not_persisted'}); }
      results.push({key,status:'filled_and_verified',attempts:1,retryable:false});
    } catch(error) { results.push({key,status:'unresolved',failure_code:error.code||(/Timeout/.test(String(error))?'interaction_timeout':'state_not_persisted'),field:repair.label||key,attempts:actualType==='combobox'?2:1,retryable:true}); }
  }
  return JSON.stringify({fingerprint:page.url(),results});
}
""").replace("REPAIRS_JSON", repairs_json)
