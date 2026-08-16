"""Shared deterministic browser logic for application control discovery."""

from __future__ import annotations

import json
from typing import Any


CONTROL_ENGINE_JS = r"""
  const clean = value => String(value ?? '').trim().replace(/\s+/g, ' ');
  const norm = value => clean(value).toLowerCase().replace(/[^a-z0-9]+/g, ' ').trim();
  const isUsableControl = async (locator, requestedType='') => {
    try {
      return await locator.evaluate((el, wantedType) => {
        const style=getComputedStyle(el), rect=el.getBoundingClientRect();
        const hiddenAncestor=el.closest('[aria-hidden="true"]');
        const simplify=el.closest('[data-simplify-extension], [data-simplify-overlay], [class*="simplify" i], [id*="simplify" i]');
        const identity=`${el.type||''} ${el.name||''} ${el.id||''} ${el.getAttribute('data-automation-id')||''}`;
        const helper=/token|csrf|xsrf|authenticity|session|wd-browser-id|workday.*helper/i.test(identity);
        const editable=!el.disabled && !el.readOnly && el.getAttribute('aria-disabled')!=='true' && el.getAttribute('aria-readonly')!=='true';
        const actual=(el.getAttribute('role')||el.type||el.tagName||'').toLowerCase();
        const wanted=String(wantedType||'').toLowerCase();
        const correct=!wanted || wanted==='text' || actual===wanted || (wanted==='combobox' && el.getAttribute('aria-haspopup')==='listbox');
        return !hiddenAncestor && !simplify && !helper && editable && correct
          && style.display!=='none' && style.visibility!=='hidden' && Number(style.opacity)!==0
          && rect.width>0 && rect.height>0;
      }, requestedType);
    } catch { return false; }
  };
  const labelOf = async locator => clean(await locator.evaluate(el =>
    el.labels?.length ? Array.from(el.labels).map(x=>x.innerText).join(' ') :
    (el.getAttribute('aria-labelledby')||'').split(/\s+/).map(id=>document.getElementById(id)?.innerText).filter(Boolean).join(' ') ||
    el.closest('fieldset')?.querySelector('legend')?.innerText ||
    el.closest('.field,.form-group,[data-automation-id*="formField"],[class*="field" i]')?.querySelector('label,[class*="label" i]')?.innerText || ''));
  const locateControl = async request => {
    const wanted=norm(request.key ?? request.label ?? request.field);
    const all=page.locator('input,textarea,select,[role="combobox"],[role="listbox"],[aria-haspopup="listbox"]');
    const candidates=[];
    for(let i=0;i<await all.count();i++) {
      const el=all.nth(i); if(!await isUsableControl(el, request.type||'')) continue;
      const id=clean(await el.getAttribute('id')), name=clean(await el.getAttribute('name'));
      const label=await labelOf(el), automation=clean(await el.getAttribute('data-automation-id'));
      const aria=clean(await el.getAttribute('aria-label'));
      const scores=[id,name].some(x=>norm(x)===wanted)?500:norm(label)===wanted?400:
        norm(automation)===wanted?300:norm(aria)===wanted?200:
        (norm(label).includes(wanted)||wanted.includes(norm(label)))?100:0;
      if(scores) candidates.push({el,score:scores,label,id,name,automation,aria});
    }
    candidates.sort((a,b)=>b.score-a.score);
    if(!candidates.length) return {error:'control_not_found'};
    if(candidates.length>1 && candidates[0].score===candidates[1].score) return {error:'ambiguous_control',candidates:candidates.slice(0,3).map(x=>x.label||x.id||x.name)};
    return {control:candidates[0].el,label:candidates[0].label};
  };
  const closeStaleListboxes = async ownedId => {
    const open=page.locator('[role="listbox"]:visible');
    for(let i=0;i<await open.count();i++) if(!ownedId || await open.nth(i).getAttribute('id')!==ownedId) await page.keyboard.press('Escape').catch(()=>{});
  };
  const selectedText = async control => clean(await control.evaluate(el =>
    el.getAttribute('aria-valuetext') || el.querySelector('[data-automation-id*="selected"], [class*="chip" i]')?.textContent ||
    el.closest('[data-automation-id*="formField"], [class*="field" i]')?.querySelector('[data-automation-id*="selected"], [class*="chip" i], button')?.textContent ||
    (el.tagName==='SELECT' ? el.selectedOptions?.[0]?.textContent : '') || el.textContent || el.value || ''));
  const chooseCustomOption = async (control,wanted) => {
    const owned=(await control.getAttribute('aria-controls')) || (await control.getAttribute('aria-owns'));
    await closeStaleListboxes(owned);
    const strategies=['pointer','keyboard'];
    const attempted=new Set();
    for(const strategy of strategies) {
      if(attempted.has(strategy)) continue; attempted.add(strategy);
      try {
        await control.click({timeout:5000});
        if(await control.isEditable().catch(()=>false)) {
          await control.fill('',{timeout:5000});
          await control.fill(String(wanted),{timeout:5000});
        }
        const popup=owned?page.locator(`[id=${JSON.stringify(owned)}]`):page.locator('[role="listbox"]:visible').last();
        const option=popup.getByRole('option',{name:String(wanted),exact:true});
        if(!await option.count()) throw Object.assign(new Error('option_not_found'),{code:'option_not_found'});
        if(strategy==='pointer') await option.click({timeout:5000});
        else { await option.focus(); await option.press('Enter',{timeout:5000}); }
        await page.waitForTimeout(250);
        const state=await selectedText(control);
        const selectedOption=page.getByRole('option',{name:String(wanted),exact:true}).first();
        const optionCommitted=await selectedOption.getAttribute('aria-selected').catch(()=>null)==='true';
        const invalid=await control.getAttribute('aria-invalid')==='true';
        if(invalid || (!optionCommitted && norm(state)!==norm(wanted) && !norm(state).includes(norm(wanted))))
          throw Object.assign(new Error('option_not_committed'),{code:'option_not_committed'});
        await closeStaleListboxes(); return {ok:true};
      } catch(error) {
        await closeStaleListboxes();
        if(strategy==='keyboard') return {error:error.code || (/Timeout/.test(String(error))?'interaction_timeout':'click_obstructed')};
      }
    }
    return {error:'click_obstructed'};
  };
"""


# Workday may turn the source question into a chain such as
# ``How did you hear about us? -> LinkedIn -> LinkedIn Job Search``.  This
# program deliberately follows only controls belonging to that chain.  It is
# kept as one browser round-trip so the model cannot get caught repeatedly
# opening and closing transient Workday menus.
WORKDAY_HEAR_ABOUT_US_CODE = r"""
async (page) => {
  const clean = value => String(value ?? '').trim().replace(/\s+/g, ' ');
  const steps = [];

  const host = await page.evaluate(() => location.hostname);
  if (!/(?:myworkdayjobs|workday)/i.test(host)) {
    return JSON.stringify({status: 'unresolved', reason: 'active page is not Workday', steps});
  }

  const sourceField = page.locator('[data-automation-id="formField-source"]').first();
  if (!await sourceField.count()) {
    return JSON.stringify({status: 'unresolved', reason: 'Workday source field was not found', steps});
  }

  const sourceInput = sourceField.locator('#source--source').first();
  if (!await sourceInput.isVisible().catch(() => false)) {
    return JSON.stringify({status: 'unresolved', reason: 'Workday source search input was not visible', steps});
  }

  const instruction = sourceField.locator('[data-automation-id="promptAriaInstruction"]').first();
  const waitForState = async (text, timeout = 4000) => {
    const start = Date.now();
    while (Date.now() - start < timeout) {
      const current = clean(await instruction.textContent().catch(() => ''));
      if (current === text) return true;
      await page.waitForTimeout(100);
    }
    return false;
  };

  // Open the picker.
  await sourceInput.click({timeout: 5000});
  if (!await waitForState('Expanded', 3000)) {
    const icon = sourceField.locator(
      '[data-automation-id="promptSearchButton"], [data-uxi-selectinputicon-type="promptIcon"]'
    ).first();
    if (await icon.isVisible().catch(() => false)) await icon.click({timeout: 5000});
    if (!await waitForState('Expanded', 3000)) {
      return JSON.stringify({status: 'unresolved', reason: 'Workday source picker never expanded', steps});
    }
  }

  // Options can render in a portal outside sourceField — resolve the real
  // popup via aria-owns/aria-controls on the input rather than assuming
  // it's a DOM descendant of the field wrapper.
  const owned = (await sourceInput.getAttribute('aria-owns')) || (await sourceInput.getAttribute('aria-controls'));
  const popupId = owned ? owned.split(/\s+/)[0] : null;
  const popup = popupId ? page.locator(`#${popupId}`) : page;

  const placeholderPattern = /^(?:select|choose|please select|search|--|none|n\/a)(?:\s|$)/i;

  for (let depth = 1; depth <= 8; depth++) {
    // Leaf level: real radios.
    const radios = popup.locator('input[type="radio"]:visible, [role="radio"]:visible');
    for (let index = 0; index < await radios.count(); index++) {
      const radio = radios.nth(index);
      const option = clean(await radio.evaluate(el =>
        el.getAttribute('aria-label') ||
        (el.labels && Array.from(el.labels).map(l => l.innerText).join(' ')) ||
        el.closest('label')?.innerText || el.parentElement?.innerText || el.textContent
      ));
      if (!option || placeholderPattern.test(option)) continue;
      const native = await radio.evaluate(el => el.matches('input[type="radio"]'));
      if (native) {
        await radio.check({timeout: 5000}).catch(async () => {
          await radio.evaluate(el => (el.closest('label') || el).click());
        });
        if (!await radio.isChecked().catch(() => false)) continue;
      } else {
        await radio.click({timeout: 5000});
        if (await radio.getAttribute('aria-checked') !== 'true') continue;
      }
      steps.push({depth, option, kind: 'radio_leaf'});
      await waitForState('Minimized', 3000);
      return JSON.stringify({status: 'selected', steps, depth});
    }

    // No leaf yet — this is a category row (chevron), not a radio. Click the
    // first real one instead of blindly pressing Enter.
    const rows = popup.locator('[role="option"]:visible, [data-automation-id="promptOption"]:visible, li:visible');
    let clicked = false;
    for (let index = 0; index < await rows.count(); index++) {
      const row = rows.nth(index);
      const text = clean(await row.innerText().catch(() => ''));
      if (!text || placeholderPattern.test(text)) continue;
      await row.click({timeout: 5000});
      steps.push({depth, option: text, kind: 'category'});
      clicked = true;
      break;
    }
    if (!clicked) {
      const debug = await popup.locator('[role="listbox"]:visible, [role="menu"]:visible').first()
        .evaluate(el => el.outerHTML.slice(0, 400)).catch(() => 'no popup found');
      return JSON.stringify({
        status: 'unresolved',
        reason: `no selectable category or leaf option found — popup snapshot: ${debug}`,
        steps,
      });
    }
    await page.waitForTimeout(400);
  }

  return JSON.stringify({status: 'unresolved', reason: 'source hierarchy exceeded max depth', steps});
}
"""


def build_select_workday_combobox_code(control_id: str, desired_option: str) -> str:
    """Select and verify a searchable Workday combobox by stable textbox id."""
    return (r"""
async (page) => {
""" + CONTROL_ENGINE_JS + r"""
  const control=page.locator(`[id=${JSON.stringify(CONTROL_ID)}]`).first();
  if(!await control.count() || !await isUsableControl(control,'combobox'))
    return JSON.stringify({status:'unresolved',failure_code:'control_not_found',field:DESIRED,attempts:0,retryable:true});
  const result=await chooseCustomOption(control,DESIRED);
  return JSON.stringify(result.error
    ? {status:'unresolved',failure_code:result.error,field:DESIRED,attempts:2,retryable:true}
    : {status:'filled_and_verified',field:DESIRED,attempts:1,retryable:false});
}
""").replace("CONTROL_ID", embed(control_id)).replace("DESIRED", embed(desired_option))


def embed(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False).replace("</", "<\\/")
